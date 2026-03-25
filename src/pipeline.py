import argparse
import asyncio
import copy
import hashlib
import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

from database import (
    add_knowledges_from_json,
    are_all_knowledges_completed_for_folder,
    count_knowledges_by_folder,
    create_job,
    get_completed_jobs_by_stage,
    get_job_by_id,
    get_pending_jobs_by_stage,
    get_pending_knowledges,
    initialize_database,
    update_job_state,
    update_knowledge_status,
)
from generators_v2.adapta.claude_45_sonnet_generator import Claude45SonnetGenerator
from generators_v2.adapta.gemini_3_pro_preview_generator import Gemini3ProPreviewGenerator
from generators_v2.adapta.gpt_5_generator import GPT5Generator
from generators_v2.adapta.client import ToolExecutionError
from utils.logger import logger
from utils.response_validator import ResponseValidationError
from utils.session_guard import LogoutGuard
from prompt_manager import generate_docling_extraction_prompt, generate_knowledge_extraction_prompt
from utils.text_cleaner import remove_think_tags

INDEXES_PATH = 'indexes'
DOCS_PREFIX = 'docs_'
KNOWLEDGE_PROMPT_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_creation.txt')
KNOWLEDGE_PROMPT_DOCLING_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_creation_docling.txt')
MAX_WORDS_PER_UPLOAD = 400000
MAX_RETRIES = 10
INITIAL_RETRY_DELAY = 2.0
MIN_CALL_DELAY_SECONDS = 60.0
MAX_INDEX_CHUNK_SIZE = 300
UPLOAD_DELAY_SECONDS = 2.0
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE2_VALIDATION_RETRY_LIMIT = 3
DOC_TEXT_DEFAULT_MAX_CHARS = 60_000


class DoclingSupportUnavailable(RuntimeError):
    """Disparado quando o modo Docling e requisitado mas nao foi possivel carregar a dependencia."""


@dataclass(frozen=True)
class _DoclingSupport:
    converter: Callable[[Union[str, Path]], Any]
    error_cls: Type[BaseException]
    max_chars: int


_docling_support_cache: Optional[_DoclingSupport] = None


def _get_docling_support() -> _DoclingSupport:
    global _docling_support_cache
    if _docling_support_cache is not None:
        return _docling_support_cache
    try:
        from utils import docling_converter as docling_module
    except Exception as exc:
        raise DoclingSupportUnavailable(
            "Modo Docling requer a dependencia 'docling'. Certifique-se de instala-la antes de usar --mode docling."
        ) from exc

    converter = getattr(docling_module, "convert_pdf_to_text", None)
    error_cls = getattr(docling_module, "DoclingConversionError", RuntimeError)
    max_chars = getattr(docling_module, "MAX_TEXT_CHARS", DOC_TEXT_DEFAULT_MAX_CHARS)
    if converter is None:
        raise DoclingSupportUnavailable("Modulo utils.docling_converter nao expõe convert_pdf_to_text.")

    _docling_support_cache = _DoclingSupport(converter=converter, error_cls=error_cls, max_chars=max_chars)
    return _docling_support_cache
def _load_stage2_concurrency() -> int:
    raw = os.getenv("STAGE2_CONCURRENCY")
    if raw:
        try:
            value = max(1, int(raw))
            logger.info("STAGE2_CONCURRENCY ajustado via ambiente para %s", value)
            return value
        except ValueError:
            logger.warning("Valor invalido para STAGE2_CONCURRENCY=%s. Mantendo padrao.", raw)
    return 1


STAGE2_CONCURRENCY = _load_stage2_concurrency()

os.makedirs(INDEXES_PATH, exist_ok=True)


os.makedirs(INDEXES_PATH, exist_ok=True)

os.makedirs(INDEXES_PATH, exist_ok=True)

CHAT_LOG_PATH = Path(INDEXES_PATH) / 'chat.md'
MAX_PATCH_RETRIES = 6

SUPPORTED_INPUT_EXTENSIONS = {'.txt', '.pdf'}
DIRECT_UPLOAD_EXTENSIONS = SUPPORTED_INPUT_EXTENSIONS.copy()


def _is_supported_job_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_INPUT_EXTENSIONS
def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[\s_]+", '-', text)
    text = re.sub(r"[^a-z0-9-]", '', text)
    return text.strip('-')


def _folder_slug_parts(folder_path: str) -> List[str]:
    if not folder_path:
        return []

    normalized = os.path.normpath(folder_path)
    path = Path(normalized)
    try:
        base_path = Path(BASE_DIR).resolve()
        resolved_path = path.resolve()
        relative_path = resolved_path.relative_to(base_path)
    except (ValueError, OSError):
        relative_path = None
    else:
        relative_parts: List[str] = []
        for part in relative_path.parts:
            slug_part = slugify(part)
            if slug_part:
                relative_parts.append(slug_part)
        if relative_parts:
            return relative_parts

    parts: List[str] = []
    anchor = path.anchor

    if not path.drive and anchor and anchor not in (os.sep, ''):
        stripped_anchor = anchor.strip(os.sep)
        if stripped_anchor:
            for anchor_part in stripped_anchor.split(os.sep):
                slug = slugify(anchor_part)
                if slug and slug not in parts:
                    parts.append(slug)

    for part in path.parts:
        if part in ('', os.sep, '.', '..', anchor, path.drive):
            continue
        slug_part = slugify(part)
        if slug_part and slug_part not in parts:
            parts.append(slug_part)
    return parts


def _build_folder_slug(folder_path: str, fallback: str) -> str:
    parts = _folder_slug_parts(folder_path)
    if not parts:
        return fallback
    slug = '_'.join(parts)
    return slug or fallback


def _sanitize_temp_identifier(identifier: str) -> str:
    sanitized = re.sub(r'[^A-Za-z0-9_-]+', '-', identifier)
    sanitized = re.sub(r'-{2,}', '-', sanitized)
    sanitized = sanitized.strip('-_')
    return sanitized or 'arquivo'


WINDOWS_RESERVED_NAMES = {
    'CON',
    'PRN',
    'AUX',
    'NUL',
    *[f'COM{i}' for i in range(1, 10)],
    *[f'LPT{i}' for i in range(1, 10)],
}


def _sanitize_reference_name(name: str, fallback: str = 'Conhecimento') -> str:
    sanitized = re.sub(r'[<>:"/\\\\|?*]', ' ', str(name))
    sanitized = re.sub(r'\s+', ' ', sanitized)
    sanitized = sanitized.strip(' .')
    return sanitized or fallback


def _sanitize_windows_filename(name: str, fallback: str = 'arquivo') -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]', '', str(name))
    sanitized = re.sub(r'[\x00-\x1f]', '', sanitized)
    sanitized = sanitized.strip()
    sanitized = sanitized.rstrip('. ')
    if not sanitized:
        sanitized = fallback
    if sanitized.upper() in WINDOWS_RESERVED_NAMES:
        sanitized = f"{sanitized}_{uuid.uuid4().hex[:4]}"
    return sanitized


def _build_sanitized_index_json(folder_path: str) -> str:
    index_path = get_index_file_path(folder_path)
    index_data = load_index_data(index_path)
    entries: List[Dict[str, Any]] = index_data.get('knowledges') or []

    sanitized_entries: List[Dict[str, Any]] = []
    for idx, entry in enumerate(entries, start=1):
        sanitized_entry = dict(entry)
        sanitized_entry['name'] = _sanitize_reference_name(entry.get('name') or '', fallback=f"Conhecimento {idx}")
        sanitized_entries.append(sanitized_entry)

    return json.dumps({'knowledges': sanitized_entries}, ensure_ascii=False, indent=2)


def _sanitize_patch_text(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return (
        text
        .replace('\\\\\"', '\\"')
        .replace('//"', '/"')
    )


def _compute_temp_upload_name(prefix: str, name_hint: str, digest_key: Optional[str] = None) -> str:
    sanitized = _sanitize_temp_identifier(name_hint)
    key = digest_key or name_hint
    digest = hashlib.md5(key.encode('utf-8')).hexdigest()[:12]
    return f"{prefix}_{sanitized}_{digest}.txt"


def get_index_file_path(folder_path: str) -> str:
    slug = _build_folder_slug(folder_path, 'indice')
    return os.path.join(INDEXES_PATH, f"{slug}.json")


def _index_part_sort_key(path: Path) -> int:
    match = re.search(r'_part_(\d+)$', path.stem)
    if match:
        return int(match.group(1))
    return 0


def get_index_part_paths(index_path: str) -> List[str]:
    base_path = Path(index_path)
    directory = base_path.parent
    stem = base_path.stem
    part_paths = sorted(directory.glob(f"{stem}_part_*.json"), key=_index_part_sort_key)
    if part_paths:
        return [str(path) for path in part_paths if path.exists()]
    if base_path.exists():
        return [str(base_path)]
    return []


def _write_index_files(index_path: str, knowledges: List[Dict[str, Any]]) -> List[str]:
    base_path = Path(index_path)
    base_path.parent.mkdir(parents=True, exist_ok=True)

    stem = base_path.stem
    directory = base_path.parent
    for existing in directory.glob(f"{stem}_part_*.json"):
        try:
            existing.unlink()
        except FileNotFoundError:
            pass

    chunk_paths: List[str] = []
    if knowledges:
        for part_number, start in enumerate(range(0, len(knowledges), MAX_INDEX_CHUNK_SIZE), start=1):
            chunk = knowledges[start:start + MAX_INDEX_CHUNK_SIZE]
            part_path = directory / f"{stem}_part_{part_number:03d}.json"
            with part_path.open('w', encoding='utf-8') as f:
                json.dump({'knowledges': chunk}, f, ensure_ascii=False, indent=4)
            chunk_paths.append(str(part_path))

    with base_path.open('w', encoding='utf-8') as f:
        json.dump({'knowledges': knowledges}, f, ensure_ascii=False, indent=4)

    return chunk_paths


def get_docs_output_dir(folder_path: str) -> str:
    parts = _folder_slug_parts(folder_path)
    if not parts:
        return f"{DOCS_PREFIX}conteudo"

    root = f"{DOCS_PREFIX}{parts[0]}"
    if len(parts) == 1:
        return root

    return str(Path(root).joinpath(*parts[1:]))


def load_index_data(index_path: str) -> Dict:
    part_paths = get_index_part_paths(index_path)
    if not part_paths:
        return {'knowledges': []}

    entries: List[Dict[str, Any]] = []
    for part_path in part_paths:
        try:
            with open(part_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except Exception:
            continue

        if isinstance(raw, dict):
            if isinstance(raw.get('knowledges'), list):
                entries.extend(raw.get('knowledges') or [])
            elif isinstance(raw.get('sections'), list):
                entries.extend(_convert_sections_to_knowledges(raw.get('sections') or []))

    sanitized = [_sanitize_knowledge_entry(entry) for entry in entries]

    base_path = Path(index_path)
    if (
        sanitized
        and len(part_paths) == 1
        and Path(part_paths[0]) == base_path
        and len(sanitized) > MAX_INDEX_CHUNK_SIZE
    ):
        _write_index_files(index_path, sanitized)

    return {'knowledges': sanitized}


def save_index_data(index_path: str, index_data: Dict) -> None:
    sanitized = [_sanitize_knowledge_entry(entry) for entry in index_data.get('knowledges') or []]
    _write_index_files(index_path, sanitized)


def _count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _coerce_file_name(entry: Any) -> Optional[str]:
    if entry is None:
        return None
    if isinstance(entry, dict):
        if 'name' in entry and entry['name']:
            raw_value = entry['name']
        else:
            raw_value = None
            for key, value in entry.items():
                if value:
                    raw_value = value
                    break
            if raw_value is None:
                return None
    else:
        raw_value = entry
    if raw_value is None:
        return None
    return str(raw_value).strip()


def _sanitize_file_list(files: Optional[List], current_file_name: Optional[str] = None) -> List[str]:
    normalized: List[str] = []
    seen = set()

    raw_items: List[Any] = []
    if isinstance(files, list):
        raw_items.extend(files)
    elif isinstance(files, str):
        raw_items.append(files)

    for entry in raw_items:
        name = _coerce_file_name(entry)
        if not name:
            continue
        clean = name.strip()
        if clean and clean not in seen:
            seen.add(clean)
            normalized.append(clean)

    if current_file_name:
        clean_current = current_file_name.strip()
        if clean_current and clean_current not in seen:
            normalized.append(clean_current)
            seen.add(clean_current)

    return normalized[:5]


def _sanitize_knowledge_entry(entry: Dict[str, Any], current_file_name: Optional[str] = None) -> Dict[str, Any]:
    name = str(entry.get('name') or '').strip()
    description = str(entry.get('description') or '').strip()
    files = _sanitize_file_list(entry.get('files'), current_file_name)
    return {
        'name': name,
        'description': description,
        'files': files,
    }


def _convert_sections_to_knowledges(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    knowledges: List[Dict[str, Any]] = []
    for section in sections or []:
        for knowledge in section.get('knowledges', []) or []:
            knowledges.append({
                'name': knowledge.get('name'),
                'description': knowledge.get('description'),
                'files': knowledge.get('files'),
            })
    return knowledges


def _knowledge_entries_equal(lhs: Dict[str, Any], rhs: Dict[str, Any]) -> bool:
    return (
        (lhs.get('name') or '').strip().lower() == (rhs.get('name') or '').strip().lower()
        and (lhs.get('description') or '').strip() == (rhs.get('description') or '').strip()
    )


def _match_new_entries_to_indices(new_entries: List[Dict[str, Any]], all_entries: List[Dict[str, Any]]) -> List[int]:
    indices: List[int] = []
    used = set()
    for candidate in new_entries:
        match_idx = None
        for idx, entry in enumerate(all_entries):
            if idx in used:
                continue
            if _knowledge_entries_equal(candidate, entry):
                match_idx = idx
                break
        if match_idx is not None:
            used.add(match_idx)
            indices.append(match_idx)
    return indices


def _extract_added_knowledges_from_operations(operations: List[Dict[str, Any]], current_file_name: str) -> List[Dict[str, Any]]:
    added: List[Dict[str, Any]] = []
    for op in operations:
        if op.get('op') != 'add':
            continue
        path = op.get('path', '')
        if not path.startswith('/knowledges/'):
            continue
        value = op.get('value')
        if isinstance(value, dict) and value.get('name'):
            added.append(_sanitize_knowledge_entry(value, current_file_name))
    return added


def _extract_patch_operations(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        if 'patch' not in payload:
            raise ValueError("Estrutura JSON invalida: campo 'patch' nao encontrado.")
        operations = payload['patch']
    else:
        operations = payload
    if not isinstance(operations, list):
        raise ValueError("Campo 'patch' deve ser uma lista de operacoes.")
    return operations


def _strip_code_fences(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    stripped = text.strip()
    if not stripped:
        return stripped
    if stripped.startswith('```json') and stripped.endswith('```'):
        stripped = stripped[7:-3]
    elif stripped.startswith('```') and stripped.endswith('```'):
        stripped = stripped[3:-3]
    return stripped.strip()


def _extract_file_names(row: Dict[str, Any]) -> List[str]:
    raw = None
    if isinstance(row, dict):
        raw = row.get('file_names')
    if not raw:
        return []
    files: List[str] = []
    seen = set()
    for value in str(raw).split('||'):
        clean = value.strip()
        if clean and clean not in seen:
            seen.add(clean)
            files.append(clean)
        if len(files) >= 5:
            break
    return files


def _split_json_pointer(path: str) -> List[str]:
    if not path or path == '/':
        return []
    if not path.startswith('/'):
        raise ValueError(f"Caminho JSON Pointer invalido: {path}")
    tokens: List[str] = []
    for part in path.split('/')[1:]:
        tokens.append(part.replace('~1', '/').replace('~0', '~'))
    return tokens


def _coerce_list_index(token: str, sequence: List[Any], allow_end: bool) -> int:
    if token == '-' and allow_end:
        return len(sequence)
    try:
        index = int(token)
    except ValueError as exc:
        raise ValueError(f"Indice de lista invalido: {token}") from exc
    if index < 0 or index > len(sequence) or (index == len(sequence) and not allow_end):
        raise IndexError(f"Indice fora do intervalo: {token}")
    return index


def _resolve_parent_and_key(document: Any, tokens: List[str]):
    if not tokens:
        return None, None
    parent = document
    for token in tokens[:-1]:
        if isinstance(parent, list):
            idx = _coerce_list_index(token, parent, allow_end=False)
            parent = parent[idx]
        elif isinstance(parent, dict):
            if token not in parent:
                raise KeyError(f"Caminho inexistente: {token}")
            parent = parent[token]
        else:
            raise TypeError("Estrutura JSON inesperada.")
    return parent, tokens[-1]


def _apply_json_patch(document: Dict[str, Any], operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    patched = copy.deepcopy(document)
    for op in operations:
        operator = op.get('op')
        path = op.get('path', '')
        tokens = _split_json_pointer(path)

        if operator != 'add':
            raise ValueError(f"Operacao JSON Patch nao suportada: {operator}")

        value = op.get('value')
        if not tokens:
            patched = value
            continue

        parent, key = _resolve_parent_and_key(patched, tokens)
        if isinstance(parent, list):
            index = _coerce_list_index(key, parent, allow_end=True)
            if index == len(parent):
                parent.append(value)
            else:
                parent.insert(index, value)
        elif isinstance(parent, dict):
            parent[key] = value
        else:
            raise TypeError("Operacao add aplicada a tipo nao suportado.")

    return patched


def _extract_patch_operations(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        if 'patch' not in payload:
            raise ValueError("Estrutura JSON invalida: campo 'patch' nao encontrado.")
        operations = payload['patch']
    else:
        operations = payload

    if not isinstance(operations, list):
        raise ValueError("Campo 'patch' deve ser uma lista de operacoes.")
    return operations


def _write_conversation_log(conversation: List[Dict[str, str]]) -> None:
    try:
        with CHAT_LOG_PATH.open('w', encoding='utf-8') as chat_file:
            for exchange in conversation:
                author = exchange.get('role', '')
                content = exchange.get('content', '')
                chat_file.write(f"## {author}\n\n{content}\n\n")
    except Exception as exc:
        logger.warning(f"Falha ao registrar conversa em chat.md: {exc}")


def _extract_json_candidate(text: str) -> Optional[str]:
    if not text:
        return None
    fenced = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
        return None
    return text[first_brace:last_brace + 1].strip()


def _has_balanced_brackets(text: str) -> bool:
    stack: List[str] = []
    opening = {'{': '}', '[': ']'}
    closing = {v: k for k, v in opening.items()}
    in_string = False
    escape = False

    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in opening:
            stack.append(opening[ch])
        elif ch in closing:
            if not stack or stack.pop() != ch:
                return False

    return not stack and not in_string


def _looks_truncated(candidate: str, exc: json.JSONDecodeError) -> bool:
    stripped = candidate.rstrip()
    if not stripped:
        return True
    if not _has_balanced_brackets(stripped):
        return True
    if exc.pos >= len(candidate) - 1:
        return True
    if not stripped.endswith(('}', ']')):
        return True
    return False


def _format_file_entry(file_path: str, base_dir: Optional[str], content: str) -> str:
    if base_dir:
        try:
            relative_path = os.path.relpath(file_path, base_dir)
        except ValueError:
            relative_path = os.path.basename(file_path)
    else:
        relative_path = os.path.relpath(file_path)

    line_count = content.count('\n')
    if content and not content.endswith('\n'):
        line_count += 1

    return (
        "-------- HEADER --------\n"
        f"{relative_path}\n"
        "-------- FIM HEADER --------\n"
        f"{content}\n"
        "-------- TRAILER --------\n"
        f"Linhas: {line_count}\n"
        "-------- FIM TRAILER --------"
    )


def _build_consolidated_text(file_paths: List[str], base_dir: Optional[str]) -> str:
    if not file_paths:
        return ""

    entries: List[str] = []
    total_words = 0

    for path in file_paths:
        with open(path, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        entry = _format_file_entry(path, base_dir, raw_content)
        total_words += _count_words(entry)
        if total_words > MAX_WORDS_PER_UPLOAD:
            raise ValueError(
                f"Consolidated file would exceed limit of {MAX_WORDS_PER_UPLOAD} words."
            )
        entries.append(entry)

    return "\n\n".join(entries)


def _create_consolidated_temp_file(
    file_paths: List[str],
    base_dir: Optional[str],
    prefix: str,
    temp_filename: Optional[str] = None
) -> Path:
    consolidated_text = _build_consolidated_text(file_paths, base_dir)
    if not consolidated_text.strip():
        raise ValueError("Nenhum conteudo valido encontrado para consolidar.")

    temp_dir = Path(tempfile.gettempdir())
    filename = temp_filename or f"{prefix}_{uuid.uuid4().hex}.txt"
    temp_path = temp_dir / filename
    temp_path.write_text(consolidated_text, encoding='utf-8')
    return temp_path




def _prepare_upload_specs(
    file_paths: List[str],
    base_dir: Optional[str],
    prefix: str,
    prefer_original: bool,
    consolidate: bool,
    unique_hint: Optional[str] = None,
) -> List[Tuple[Path, bool]]:
    if not file_paths:
        raise ValueError("Nenhum arquivo fonte informado para upload.")

    if consolidate or len(file_paths) == 1:
        upload_path, cleanup = _prepare_upload_file(
            file_paths=file_paths,
            base_dir=base_dir,
            prefix=prefix,
            prefer_original=prefer_original,
            unique_hint=unique_hint,
        )
        return [(upload_path, cleanup)]

    specs: List[Tuple[Path, bool]] = []
    for source in file_paths:
        source_path = Path(source)
        if source_path.suffix.lower() in DIRECT_UPLOAD_EXTENSIONS:
            specs.append((source_path, False))
            continue

        consolidated_text = _build_consolidated_text([str(source_path)], base_dir)
        temp_dir = Path(tempfile.gettempdir())
        temp_filename = _compute_temp_upload_name(prefix, source_path.stem, str(source_path))
        temp_path = temp_dir / temp_filename
        temp_path.write_text(consolidated_text, encoding='utf-8')
        specs.append((temp_path, True))
    return specs

def _prepare_upload_file(
    file_paths: List[str],
    base_dir: Optional[str],
    prefix: str,
    prefer_original: bool,
    unique_hint: Optional[str] = None,
) -> Tuple[Path, bool]:
    if not file_paths:
        raise ValueError("Nenhum arquivo fonte informado para upload.")

    if prefer_original and len(file_paths) == 1:
        return Path(file_paths[0]), False

    if prefix == 'stage2':
        slug = slugify(str(unique_hint) or 'stage2')
        if not slug:
            slug = 'stage2'
        temp_filename = f"{prefix}_{slug}_{uuid.uuid4().hex[:8]}.txt"
    else:
        hints = "_".join(Path(str(p)).stem for p in file_paths)
        digest_key = "|".join(str(p) for p in file_paths)
        temp_filename = _compute_temp_upload_name(prefix, hints, digest_key)
    temp_path = _create_consolidated_temp_file(file_paths, base_dir, prefix, temp_filename=temp_filename)
    return temp_path, True


def _predict_upload_names(
    file_paths: List[str],
    base_dir: Optional[str],
    prefix: str,
    prefer_original: bool,
    consolidate: bool,
) -> List[str]:
    if not file_paths:
        return []

    def _resolve_relative(path: Path) -> str:
        if base_dir:
            try:
                return os.path.relpath(str(path), base_dir)
            except ValueError:
                return path.name
        return path.name

    if consolidate or len(file_paths) == 1:
        if prefer_original and len(file_paths) == 1:
            return [_resolve_relative(Path(file_paths[0]))]
        hints = "_".join(Path(str(p)).stem for p in file_paths)
        digest_key = "|".join(str(p) for p in file_paths)
        return [_compute_temp_upload_name(prefix, hints, digest_key)]

    predicted: List[str] = []
    seen = set()
    for source in file_paths:
        source_path = Path(source)
        if source_path.suffix.lower() in DIRECT_UPLOAD_EXTENSIONS:
            name = _resolve_relative(source_path)
        else:
            name = _compute_temp_upload_name(prefix, source_path.stem, str(source_path))
        if name not in seen:
            seen.add(name)
            predicted.append(name)
    return predicted


def _resolve_generator_label(generator: Any) -> str:
    if generator is None:
        return 'desconhecido'
    provider = getattr(generator, 'get_provider_name', None)
    if callable(provider):
        try:
            return provider()
        except Exception:
            pass
    return generator.__class__.__name__


async def _perform_uploads(
    generator,
    uploads: List[Tuple[Path, bool]],
    delay_between_uploads: float = 0.0,
) -> List[Tuple[Dict[str, Any], bool, Path]]:
    upload_infos: List[Tuple[Dict[str, Any], bool, Path]] = []
    for index, (upload_path, cleanup) in enumerate(uploads):
        logger.info(f'Fazendo upload do arquivo: {upload_path}')
        upload_info = await generator.client.upload_arquivo(str(upload_path))
        if not upload_info:
            raise RuntimeError(f"Falha ao fazer upload do arquivo: {upload_path}")
        upload_infos.append((upload_info, cleanup, upload_path))
        if delay_between_uploads > 0 and index < len(uploads) - 1:
            await asyncio.sleep(delay_between_uploads)
    return upload_infos


async def _cleanup_chat(generator) -> None:
    """Exclui o chat associado ao último atendimento do cliente, se existir."""
    client = getattr(generator, "client", None)
    if client is None:
        return
    chat_id = getattr(client, "last_chat_id", None)
    if not chat_id:
        return
    try:
        await client.excluir_chat(chat_id)
        logger.debug(f"Chat {chat_id} excluido com sucesso.")
    except Exception as exc:
        logger.warning(f"Falha ao excluir chat {chat_id}: {exc}")


async def _call_generator_with_existing_uploads(
    generator,
    prompt: Optional[str],
    upload_infos: List[Tuple[Dict[str, Any], bool, Path]],
    messages: Optional[List[Dict[str, str]]] = None,
) -> str:
    if messages is None:
        if prompt is None:
            raise ValueError("Prompt ou mensagens devem ser fornecidos para chamada ao gerador.")
        payload_messages = [{'role': 'user', 'content': prompt}]
    else:
        payload_messages = [dict(message) for message in messages]

    logger.debug(f'Iniciando chamada ao modelo com {len(upload_infos)} arquivo(s) anexados.')
    files_payload = [info for info, _, _ in upload_infos if info]
    response = await generator.call_model_with_messages(
        payload_messages,
        files=files_payload,
    )
    logger.debug('Chamada ao modelo concluida com sucesso.')
    try:
        await _cleanup_chat(generator)
    except Exception:
        pass
    return response


async def _cleanup_upload_infos(
    generator,
    upload_infos: List[Tuple[Dict[str, Any], bool, Path]],
    cleanup_local_paths: bool,
) -> None:
    for upload_info, cleanup, upload_path in upload_infos:
        file_path = None
        if upload_info:
            file_path = (
                upload_info.get("path")
                or upload_info.get("filePathOnStorage")
                or upload_info.get("filename")
            )
        if file_path:
            try:
                await generator.client.excluir_arquivo(file_path)
            except Exception as exc:
                logger.warning(f"Falha ao excluir arquivo remoto {file_path}: {exc}")
        if cleanup_local_paths and cleanup:
            try:
                if upload_path.exists():
                    upload_path.unlink()
            except Exception as exc:
                logger.warning(f"Falha ao remover arquivo temporario {upload_path}: {exc}")
    if cleanup_local_paths:
        logger.debug('Uploads temporarios limpos com sucesso.')


def _cleanup_local_prepared_uploads(
    prepared_uploads: Optional[List[Tuple[Path, bool]]],
) -> None:
    if not prepared_uploads:
        return
    for upload_path, cleanup in prepared_uploads:
        if not cleanup:
            continue
        try:
            if upload_path.exists():
                upload_path.unlink()
        except Exception as exc:
            logger.warning(f"Falha ao remover arquivo temporario {upload_path}: {exc}")


async def _reset_persistent_uploads(
    upload_context: Optional[Dict[Any, List[Tuple[Dict[str, Any], bool, Path]]]],
) -> None:
    if not upload_context:
        return
    for generator_instance, upload_infos in list(upload_context.items()):
        if not upload_infos:
            continue
        await _cleanup_upload_infos(
            generator_instance,
            upload_infos,
            cleanup_local_paths=False,
        )
    upload_context.clear()


async def _call_generator_with_uploads(
    generator,
    prompt: Optional[str],
    uploads: List[Tuple[Path, bool]],
    messages: Optional[List[Dict[str, str]]] = None,
    upload_delay: float = 0.0,
) -> str:
    upload_infos = await _perform_uploads(generator, uploads, upload_delay)
    try:
        return await _call_generator_with_existing_uploads(
            generator,
            prompt,
            upload_infos,
            messages=messages,
        )
    finally:
        await _cleanup_upload_infos(generator, upload_infos, cleanup_local_paths=True)


def _is_doc_engine_error(exc: BaseException) -> bool:
    if not isinstance(exc, ToolExecutionError):
        return False
    message = str(exc).lower()
    return "err:604" in message or "motor" in message and "analise" in message


def _contains_retry_hint(text: Optional[str]) -> bool:
    if not text:
        return False
    return "tentar novamente" in text.lower()


async def _call_with_retries(
    generator,
    prompt: Optional[str],
    source_paths: Optional[List[str]],
    base_dir: Optional[str],
    prefix: str,
    prefer_original_when_single: bool,
    consolidate: bool = True,
    max_retries: int = MAX_RETRIES,
    initial_delay: float = INITIAL_RETRY_DELAY,
    generator_cycle: Optional[List[Any]] = None,
    fallback_generator: Optional[Any] = None,
    fallback_attempt: Optional[int] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    prepared_uploads: Optional[List[Tuple[Path, bool]]] = None,
    persist_uploads: bool = False,
    upload_context: Optional[Dict[Any, List[Tuple[Dict[str, Any], bool, Path]]]] = None,
    upload_delay: float = 0.0,
    upload_unique_hint: Optional[str] = None,
) -> str:
    if prompt is None and messages is None:
        raise ValueError("Prompt ou mensagens devem ser fornecidos para a chamada ao gerador.")

    normalized_sources = list(source_paths or [])
    has_files = bool(normalized_sources)

    if generator_cycle:
        cycle = [gen for gen in generator_cycle if gen is not None]
        if not cycle:
            raise ValueError("generator_cycle deve conter pelo menos um gerador valido.")
    else:
        if generator is None:
            raise ValueError("Nenhum gerador primario informado para a chamada.")
        cycle = [generator]

    delay = max(initial_delay, MIN_CALL_DELAY_SECONDS)
    last_error: Optional[Exception] = None
    local_prepared_uploads = prepared_uploads if has_files else None

    for attempt in range(1, max_retries + 1):
        uploads: Optional[List[Tuple[Path, bool]]] = local_prepared_uploads
        if generator_cycle:
            current_generator = cycle[(attempt - 1) % len(cycle)]
            generator_label = _resolve_generator_label(current_generator)
            logger.info(f"Tentativa {attempt}/{max_retries} com gerador {generator_label}.")
        else:
            current_generator = generator
            generator_label = _resolve_generator_label(current_generator)
            if (
                fallback_generator is not None
                and fallback_attempt is not None
                and attempt >= fallback_attempt
            ):
                current_generator = fallback_generator
                generator_label = _resolve_generator_label(current_generator)
                if attempt == fallback_attempt:
                    logger.info(f"Usando gerador {generator_label} como fallback a partir da tentativa {attempt}.")
            logger.debug(f"Tentativa {attempt}/{max_retries} com gerador {generator_label}.")
        try:
            if has_files:
                if uploads is None:
                    uploads = _prepare_upload_specs(
                        file_paths=normalized_sources,
                        base_dir=base_dir,
                        prefix=prefix,
                        prefer_original=prefer_original_when_single,
                        consolidate=consolidate,
                        unique_hint=upload_unique_hint,
                    )
                    if persist_uploads or prepared_uploads is not None:
                        local_prepared_uploads = uploads

                if persist_uploads:
                    if upload_context is None:
                        raise ValueError("upload_context deve ser fornecido quando persist_uploads=True.")
                    upload_infos = upload_context.get(current_generator)
                    if upload_infos is None:
                        upload_infos = await _perform_uploads(
                            current_generator,
                            uploads,
                            delay_between_uploads=upload_delay,
                        )
                        upload_context[current_generator] = upload_infos
                    result = await _call_generator_with_existing_uploads(
                        current_generator,
                        prompt,
                        upload_infos,
                        messages=messages,
                    )
                    return result

                result = await _call_generator_with_uploads(
                    current_generator,
                    prompt,
                    uploads,
                    messages=messages,
                    upload_delay=upload_delay,
                )
                return result

            # Sem arquivos anexados, apenas repasse o prompt/mensagens.
            return await _call_generator_with_existing_uploads(
                current_generator,
                prompt,
                [],
                messages=messages,
            )
        except ToolExecutionError as exc:
            logger.error("Falha do motor/documento reportada pelo modelo: %s", exc)
            raise
        except Exception as exc:
            last_error = exc
            if (
                has_files
                and not persist_uploads
                and prepared_uploads is None
                and uploads
            ):
                for path, cleanup in uploads:
                    if cleanup and path.exists():
                        try:
                            path.unlink()
                        except Exception:
                            pass
            if attempt == max_retries:
                raise
            sleep_time = max(delay, MIN_CALL_DELAY_SECONDS)
            logger.warning(f"Tentativa {attempt}/{max_retries} falhou ({exc}). Nova tentativa em {sleep_time:.1f}s...")
            await asyncio.sleep(sleep_time)
            delay = max(delay * 1.5, MIN_CALL_DELAY_SECONDS)

    if last_error:
        raise last_error
    raise RuntimeError("Erro desconhecido ao chamar o gerador.")


def section_key(section_id, section_title):
    return section_id, section_title or ''


def _build_files_prompt_segment(
    file_paths: List[str],
    base_dir: Optional[str],
    display_names: Optional[List[str]] = None
) -> str:
    if not file_paths:
        return ""

    names: List[str] = []
    seen = set()
    for idx, path in enumerate(file_paths):
        if display_names and idx < len(display_names):
            name = display_names[idx]
        else:
            try:
                name = os.path.relpath(path, base_dir) if base_dir else os.path.basename(path)
            except ValueError:
                name = os.path.basename(path)
        name = name.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    if not names:
        return ""

    listing = "\n".join(f"- {name}" for name in names)
    return f"\n\n# ARQUIVOS DISPONIVEIS\n{listing}"


def _resolve_display_name(file_path: Path, base_dir: Optional[str]) -> str:
    if base_dir:
        try:
            return os.path.relpath(str(file_path), base_dir)
        except ValueError:
            pass
    return file_path.name


def _truncate_text(text: str, max_chars: int = DOC_TEXT_DEFAULT_MAX_CHARS) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    suffix = f"\n\n[Trecho truncado apos {max_chars} caracteres]"
    return text[:max_chars] + suffix


def _extract_docling_text(file_path: str) -> str:
    support = _get_docling_support()
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        result = support.converter(path)
        return result.text
    text = path.read_text(encoding="utf-8", errors="ignore")
    return _truncate_text(text, max_chars=support.max_chars)


def _build_docling_blocks(file_paths: List[str], base_dir: Optional[str]) -> str:
    support = _get_docling_support()
    blocks: List[str] = []
    for raw_path in file_paths:
        path = Path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo nao encontrado para Docling: {path}")
        display_name = _resolve_display_name(path, base_dir)
        text = _extract_docling_text(str(path))
        if not text.strip():
            continue
        blocks.append(f"## {display_name}\n{text.strip()}")
    if not blocks:
        raise support.error_cls("Docling nao retornou texto utilizavel para o fallback.")
    return "\n\n".join(blocks)


def _append_index_json_to_prompt(
    prompt: str,
    index_paths: Optional[List[str]],
    display_names: Optional[List[str]],
    *,
    max_chars: int = 200_000,
) -> str:
    if not index_paths:
        return prompt

    sections: List[str] = ["\n\n# INDICE ATUAL (JSON)\n"]
    for idx, raw_path in enumerate(index_paths):
        path = Path(raw_path)
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Falha ao ler indice %s: %s", path, exc)
            continue
        snippet = _truncate_text(content, max_chars=max_chars)
        if display_names and idx < len(display_names) and display_names[idx]:
            title = display_names[idx]
        else:
            title = path.name
        sections.append(f"## {title}\n```json\n{snippet}\n```\n")

    if len(sections) == 1:
        return prompt
    return prompt + "".join(sections)


def process_input_folder(folder_path):
    logger.info(f"Escaneando a pasta de entrada: {folder_path}")
    if not os.path.isdir(folder_path):
        logger.error(f"O caminho '{folder_path}' nao e um diretorio valido.")
        return
    pending_dirs: List[str] = [os.path.abspath(folder_path)]

    while pending_dirs:
        current_dir = pending_dirs.pop()
        try:
            with os.scandir(current_dir) as iterator:
                entries = sorted(list(iterator), key=lambda entry: entry.name.lower())
        except OSError as exc:
            logger.warning(f"Falha ao listar conteudo de {current_dir}: {exc}")
            continue

        for entry in entries:
            entry_path = entry.path
            if entry.is_dir(follow_symlinks=False):
                pending_dirs.append(entry_path)
                logger.debug(f"Encontrada subpasta para processamento: {entry_path}")
                continue
            if entry.is_file(follow_symlinks=False) and _is_supported_job_file(entry.name):
                file_path = os.path.abspath(entry_path)
                create_job(file_path, entry.name, current_dir)


async def run_stage1_index_creation(mode: str, job_filter: Optional[int] = None):
    logger.info('Iniciando Estagio 1: Criacao de Indice de Conhecimento.')
    pending_jobs = get_pending_jobs_by_stage(stage_id=1)
    if job_filter is not None:
        pending_jobs = [job for job in pending_jobs if job['id'] == job_filter]
        if not pending_jobs:
            logger.info("Job %s nao esta pendente no Estagio 1.", job_filter)
            return

    if not pending_jobs:
        logger.info('Nenhum job pendente para o Estagio 1.')
        return

    claude_generator = Claude45SonnetGenerator()
    gpt_generator = GPT5Generator()
    gemini_generator = Gemini3ProPreviewGenerator()
    claude_guard = LogoutGuard(claude_generator.client, label="pipeline-stage1-claude")
    gpt_guard = LogoutGuard(gpt_generator.client, label="pipeline-stage1-gpt5")
    gemini_guard = LogoutGuard(gemini_generator.client, label="pipeline-stage1-gemini")
    for guard in (claude_guard, gpt_guard, gemini_guard):
        guard.register()

    for job in pending_jobs:
        job_id = job['id']
        folder_path = job['folder_path']
        current_file_name = job['file_name']
        index_path = get_index_file_path(folder_path)
        index_data = load_index_data(index_path)
        existing_list = index_data.get('knowledges', [])
        has_existing_index = bool(existing_list)
        index_part_paths: List[str] = []
        if has_existing_index:
            index_part_paths = get_index_part_paths(index_path)
            if len(index_part_paths) == 1 and Path(index_part_paths[0]) == Path(index_path):
                _write_index_files(index_path, existing_list)
                index_part_paths = get_index_part_paths(index_path)

        logger.info(f"Processando job {job_id} para o arquivo: {current_file_name}")

        index_display_names: Optional[List[str]] = None
        if has_existing_index and index_part_paths:
            index_display_names = _predict_upload_names(
                index_part_paths,
                base_dir=None,
                prefix='stage1',
                prefer_original=False,
                consolidate=False,
            )

        use_docling_mode = mode.lower() == "docling"
        prompt: str
        if use_docling_mode:
            try:
                docling_blocks = _build_docling_blocks([job['file_path']], folder_path)
            except Exception as exc:
                logger.error("Falha ao converter %s via Docling: %s", current_file_name, exc)
                raise SystemExit(1) from exc
            prompt = generate_docling_extraction_prompt(
                current_file_name,
                docling_blocks,
                existing_index_paths=index_part_paths if has_existing_index else None,
                existing_index_display_names=index_display_names,
            )
        else:
            prompt = generate_knowledge_extraction_prompt(
                current_file_name,
                existing_index_paths=index_part_paths if has_existing_index else None,
                existing_index_display_names=index_display_names,
            )
        prompt = _append_index_json_to_prompt(
            prompt,
            index_part_paths if has_existing_index else None,
            index_display_names,
        )
        source_files = [job['file_path']]

        temp_raw_path = Path(INDEXES_PATH) / 'temp.json'
        patch_debug_paths: List[Path] = []
        conversation: List[Dict[str, str]] = [{'role': 'user', 'content': prompt}]
        _write_conversation_log(conversation)
        accumulated_raw = ""
        accumulated_clean_chunks: List[str] = []
        patch_retry_attempts = 0
        knowledges_for_stage2: List[Dict[str, Any]] = []
        prepared_uploads: Optional[List[Tuple[Path, bool]]] = None
        persistent_upload_context: Dict[Any, List[Tuple[Dict[str, Any], bool, Path]]] = {}
        current_source_files = [] if use_docling_mode else list(source_files)

        try:
            while True:
                if current_source_files and prepared_uploads is None:
                    prepared_uploads = _prepare_upload_specs(
                        file_paths=current_source_files,
                        base_dir=folder_path,
                        prefix='stage1',
                        prefer_original=True,
                        consolidate=False,
                    )
                raw_response = await _call_with_retries(
                    generator=claude_generator,
                    prompt=None,
                    source_paths=current_source_files,
                    base_dir=folder_path,
                    prefix='stage1',
                    prefer_original_when_single=True,
                    consolidate=False,
                    generator_cycle=[claude_generator, gpt_generator, gemini_generator],
                    messages=conversation,
                    prepared_uploads=prepared_uploads if current_source_files else None,
                    persist_uploads=bool(current_source_files),
                    upload_context=persistent_upload_context if current_source_files else None,
                    upload_delay=UPLOAD_DELAY_SECONDS,
                )

                accumulated_raw += raw_response
                sanitized_accumulated = _sanitize_patch_text(accumulated_raw) or accumulated_raw
                temp_raw_path.write_text(sanitized_accumulated, encoding='utf-8')

                cleaned_chunk = remove_think_tags(raw_response)
                accumulated_clean_chunks.append(cleaned_chunk)
                conversation.append({'role': 'assistant', 'content': cleaned_chunk})
                _write_conversation_log(conversation)

                combined_clean = ''.join(accumulated_clean_chunks)
                normalized_combined = _sanitize_patch_text(combined_clean) or combined_clean
                candidate = _extract_json_candidate(normalized_combined)
                candidate = _sanitize_patch_text(candidate) or candidate

                if has_existing_index:
                    try:
                        data, candidate_text = await _ensure_valid_json_patch(
                            candidate=candidate,
                            raw_output=normalized_combined,
                            generator=gemini_generator,
                            job_file_path=job['file_path'],
                            folder_path=folder_path,
                            attempt_context=f"job{job_id}-patch{patch_retry_attempts + 1}",
                        )
                    except ValueError as parse_error:
                        patch_retry_attempts += 1
                        if patch_retry_attempts >= MAX_PATCH_RETRIES:
                            raise
                        logger.warning(f"Falha ao interpretar JSON Patch: {parse_error}. Solicitando nova geracao ao modelo.")
                        conversation.append({
                            'role': 'user',
                            'content': (
                                "O JSON retornado para 'patch' esta invalido. Gere novamente todo o array 'patch' com JSON valido, "
                                "apenas com operacoes 'add' e caminhos RFC 6901 coerentes. Lembre-se de manter o arquivo atual na lista 'files'."
                            ),
                        })
                        _write_conversation_log(conversation)
                        continue
                    operations = _extract_patch_operations(data)
                    logger.info(f"Operacoes JSON Patch recebidas: {len(operations)}")
                    attempt_index = patch_retry_attempts + 1
                    patch_debug_path = Path(INDEXES_PATH) / f'patch_job_{job_id}_attempt_{attempt_index}.json'
                    patch_debug_paths.append(patch_debug_path)
                    try:
                        patch_debug_path.write_text(candidate_text, encoding='utf-8')
                        logger.info(f"JSON Patch salvo para depuracao em: {patch_debug_path}")
                    except Exception as write_exc:
                        logger.warning(f"Falha ao salvar JSON Patch em {patch_debug_path}: {write_exc}")
                        patch_debug_paths.pop()
                        patch_debug_path = None
                    try:
                        patched_index = _apply_json_patch({'knowledges': existing_list}, operations)
                    except Exception as patch_exc:
                        if patch_debug_path:
                            logger.error(f"Erro ao aplicar JSON Patch. Arquivo de depuracao: {patch_debug_path}")
                        patch_retry_attempts += 1
                        if patch_retry_attempts >= MAX_PATCH_RETRIES:
                            raise
                        logger.warning("Aplicacao do JSON Patch falhou. Solicitando nova versao ao modelo...")
                        retry_message = (
                            "O JSON Patch retornado falhou ao ser aplicado "
                            f"({patch_exc}). Gere novamente todo o array 'patch', revendo o indice atual e garantindo que cada caminho RFC 6901 aponta para posicoes validas. "
                            f"Use apenas operacoes 'add'; para referencias '/knowledges/<indice>' utilize indices entre 0 e {len(existing_list)} ou '-' para anexar ao final; "
                            "ao adicionar arquivos, utilize '/knowledges/<indice>/files/-'. "
                            "Retorne JSON valido no formato solicitado, mantendo o arquivo atual em 'files'."
                        )
                        conversation.append({'role': 'user', 'content': retry_message})
                        _write_conversation_log(conversation)
                        continue
                    if not isinstance(patched_index, dict):
                        raise ValueError("Resultado das operacoes JSON Patch nao e um objeto JSON.")
                    sanitized_all = [_sanitize_knowledge_entry(entry) for entry in patched_index.get('knowledges') or []]
                    added_entries = _extract_added_knowledges_from_operations(operations, current_file_name)
                    matched_indices = _match_new_entries_to_indices(added_entries, sanitized_all)
                    for idx in matched_indices:
                        sanitized_all[idx] = _sanitize_knowledge_entry(sanitized_all[idx], current_file_name)
                    index_data = {'knowledges': sanitized_all}
                    existing_list = sanitized_all
                    knowledges_for_stage2 = [
                        {
                            'index': idx,
                            'name': sanitized_all[idx]['name'],
                            'description': sanitized_all[idx]['description'],
                            'files': sanitized_all[idx]['files'],
                            'folder_path': folder_path,
                        }
                        for idx in matched_indices
                    ]
                else:
                    candidate_text = _strip_code_fences(candidate) or _strip_code_fences(normalized_combined) or normalized_combined
                    candidate_text = _sanitize_patch_text(candidate_text) or candidate_text
                    try:
                        data = json.loads(candidate_text)
                    except json.JSONDecodeError as exc:
                        logger.error(f"Falha ao interpretar JSON inicial do indice: {exc}")
                        raise
                    sanitized_all = [_sanitize_knowledge_entry(entry, current_file_name) for entry in data.get('knowledges') or []]
                    index_data = {'knowledges': sanitized_all}
                    existing_list = sanitized_all
                    knowledges_for_stage2 = [
                        {
                            'index': idx,
                            'name': entry['name'],
                            'description': entry['description'],
                            'files': entry['files'],
                            'folder_path': folder_path,
                        }
                        for idx, entry in enumerate(sanitized_all)
                    ]
                break

            save_index_data(index_path, index_data)

            if knowledges_for_stage2:
                logger.info(f"{len(knowledges_for_stage2)} novos conhecimentos identificados para o job {job_id}.")
            else:
                logger.info("Nenhum novo conhecimento identificado para este arquivo.")

            update_job_state(job_id, stage_id=2, status_id=3)
            logger.info(f"Job {job_id} concluido com sucesso.")

        except Exception as e:
            logger.error(f"Erro ao processar o job {job_id}: {e}")
            update_job_state(job_id, stage_id=1, status_id=1)
            raise SystemExit(1) from e
        finally:
            if persistent_upload_context:
                for generator_instance, upload_infos in persistent_upload_context.items():
                    if upload_infos:
                        await _cleanup_upload_infos(
                            generator_instance,
                            upload_infos,
                            cleanup_local_paths=False,
                        )
            if prepared_uploads:
                for upload_path, cleanup in prepared_uploads:
                    if cleanup and upload_path.exists():
                        try:
                            upload_path.unlink()
                        except Exception as cleanup_exc:
                            logger.warning(f"Falha ao remover arquivo temporario {upload_path}: {cleanup_exc}")
            if temp_raw_path.exists():
                try:
                    temp_raw_path.unlink()
                except Exception as cleanup_exc:
                    logger.warning(f"Falha ao remover arquivo temporario {temp_raw_path}: {cleanup_exc}")
            for debug_path in patch_debug_paths:
                if debug_path.exists():
                    try:
                        debug_path.unlink()
                    except Exception as cleanup_exc:
                        logger.warning(f"Falha ao remover arquivo de depuracao {debug_path}: {cleanup_exc}")

    await asyncio.gather(
        claude_guard.close_now(),
        gpt_guard.close_now(),
        gemini_guard.close_now(),
    )

async def process_pending_knowledges(mode: str, job_filter: Optional[int] = None):
    _ensure_pending_knowledges_synced()
    logger.info('Iniciando Estagio 2: Criacao de Arquivos de Conhecimento.')
    pending_rows = [dict(row) for row in get_pending_knowledges()]

    folder_filter: Optional[str] = None
    if job_filter is not None:
        job_row = get_job_by_id(job_filter)
        if not job_row:
            logger.info("Job %s nao encontrado; Estagio 2 ignorado.", job_filter)
            return
        folder_filter = job_row['folder_path']

    def _row_get_value(row: Any, key: str, default: Any = None) -> Any:
        if isinstance(row, dict):
            return row.get(key, default)
        try:
            return row[key]
        except Exception:
            return default

    if folder_filter:
        pending_rows = [
            row
            for row in pending_rows
            if (_row_get_value(row, 'knowledge_folder_path', '') or '') == folder_filter
        ]

    if not pending_rows:
        logger.info('Nenhum conhecimento pendente para processar.')
        return

    with open(KNOWLEDGE_PROMPT_PATH, 'r', encoding='utf-8') as f:
        prompt_template = f.read()
    with open(KNOWLEDGE_PROMPT_DOCLING_PATH, 'r', encoding='utf-8') as f:
        docling_prompt_template = f.read()

    semaphore = asyncio.Semaphore(STAGE2_CONCURRENCY)
    abort_event = asyncio.Event()
    index_cache: Dict[str, str] = {}

    def get_sanitized_index_json(folder: str) -> str:
        if folder not in index_cache:
            try:
                index_cache[folder] = _build_sanitized_index_json(folder)
            except Exception as exc:
                logger.warning(f"Falha ao construir indice sanitizado para {folder}: {exc}")
                index_cache[folder] = '[]'
        return index_cache[folder]

    async def run_with_limit(row: Dict[str, Any]) -> None:
        if abort_event.is_set():
            return
        async with semaphore:
            if abort_event.is_set():
                return
            folder = _row_get_value(row, 'knowledge_folder_path', '') or ''
            sanitized_row = dict(row)
            sanitized_row['sanitized_index_json'] = get_sanitized_index_json(folder)
            sanitized_row['knowledge_prompt_name'] = _sanitize_reference_name(
                sanitized_row.get('knowledge_name') or f"Conhecimento {sanitized_row.get('knowledge_id')}"
            )
            try:
                await _process_single_knowledge(
                    sanitized_row,
                    prompt_template,
                    docling_prompt_template,
                    mode=mode,
                )
            except ToolExecutionError:
                abort_event.set()
                raise

    tasks = [asyncio.create_task(run_with_limit(dict(row))) for row in pending_rows]
    try:
        await asyncio.gather(*tasks)
    except ToolExecutionError as exc:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise exc


async def _process_single_knowledge(
    knowledge: Dict[str, Any],
    prompt_template: str,
    docling_prompt_template: str,
    *,
    mode: str,
) -> None:
    knowledge_id = knowledge['knowledge_id']
    folder_path = knowledge['knowledge_folder_path']
    knowledge_name = knowledge.get('knowledge_name') or f"Conhecimento {knowledge_id}"
    prompt_knowledge_name = knowledge.get('knowledge_prompt_name') or knowledge_name
    source_files = _extract_file_names(knowledge)
    knowledge_category = str(knowledge.get('knowledge_category') or 'Geral').strip() or 'Geral'

    logger.info(f"Processando conhecimento ID: {knowledge_id} - {knowledge_name}")
    guard: Optional[LogoutGuard] = None

    try:
        abs_folder_path = folder_path if os.path.isabs(folder_path) else os.path.join(BASE_DIR, folder_path)

        consolidated_sources: List[str] = []
        if source_files:
            for file_name in source_files:
                file_path = os.path.join(abs_folder_path, file_name)
                if os.path.isfile(file_path):
                    consolidated_sources.append(file_path)
                else:
                    logger.warning(f"Arquivo {file_name} nao encontrado em {abs_folder_path}.")

        if not consolidated_sources:
            logger.error(f"Nenhum arquivo de origem encontrado para o conhecimento {knowledge_id}.")
            update_knowledge_status(knowledge_id, status_id=1)
            return

        raw_index_content = knowledge.get('sanitized_index_json') or '[]'

        use_docling_mode = mode.lower() == "docling"
        if use_docling_mode:
            try:
                docling_blocks = _build_docling_blocks(consolidated_sources, abs_folder_path)
            except Exception as exc:
                logger.error("Falha ao converter fontes Docling para conhecimento %s: %s", knowledge_id, exc)
                raise SystemExit(1) from exc
            prompt_variant = (
                docling_prompt_template
                .replace('{knowledge_category}', knowledge_category)
                .replace('{knowledge_name}', prompt_knowledge_name)
                .replace('{index_knowledge}', raw_index_content)
                .replace('{docling_blocks}', docling_blocks)
            )
        else:
            prompt_variant = (
                prompt_template
                .replace('{knowledge_category}', knowledge_category)
                .replace('{knowledge_name}', prompt_knowledge_name)
                .replace('{index_knowledge}', raw_index_content)
            )
            upload_display_names_stage2 = _predict_upload_names(
                consolidated_sources,
                abs_folder_path,
                prefix='stage2',
                prefer_original=True,
                consolidate=True,
            )
            source_prompt = _build_files_prompt_segment(
                consolidated_sources,
                abs_folder_path,
                upload_display_names_stage2,
            )
            if source_prompt:
                prompt_variant += source_prompt

        generator = Claude45SonnetGenerator()
        guard = LogoutGuard(generator.client, label=f"pipeline-stage2-{knowledge_id}")
        validation_retries = 0

        while True:
            prompt_to_use = prompt_variant
            call_source_paths = [] if use_docling_mode else consolidated_sources
            markdown_output = await _call_with_retries(
                generator=generator,
                prompt=prompt_to_use,
                source_paths=call_source_paths,
                base_dir=abs_folder_path,
                prefix='stage2',
                prefer_original_when_single=True,
                upload_unique_hint=str(knowledge_id),
            )

            markdown_output = remove_think_tags(markdown_output)
            if _contains_retry_hint(markdown_output):
                validation_retries += 1
                if validation_retries >= STAGE2_VALIDATION_RETRY_LIMIT:
                    raise ResponseValidationError(
                        f"Resposta invalida para conhecimento {knowledge_id}: texto pede para tentar novamente."
                    )
                logger.warning(
                    "Conhecimento %s retornou 'tentar novamente'. Repetindo tentativa %s/%s.",
                    knowledge_id,
                    validation_retries,
                    STAGE2_VALIDATION_RETRY_LIMIT,
                )
                await asyncio.sleep(MIN_CALL_DELAY_SECONDS)
                continue
            break

        knowledge_slug = slugify(knowledge_name)
        output_dir = get_docs_output_dir(folder_path)
        os.makedirs(output_dir, exist_ok=True)

        primary_name = _sanitize_windows_filename(knowledge_name, fallback=knowledge_slug or 'conhecimento')
        primary_filename = f"{primary_name}.md"
        fallback_filename = f"{knowledge_slug}.md"
        output_path = os.path.join(output_dir, primary_filename)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_output)
        except (OSError, ValueError) as file_error:
            logger.warning(
                f"Falha ao salvar arquivo com o nome original '{primary_filename}'. Tentando com slug. Erro: {file_error}"
            )
            output_path = os.path.join(output_dir, fallback_filename)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_output)

        logger.info(f"Arquivo Markdown salvo em: {output_path}")

        update_knowledge_status(knowledge_id, status_id=3)
        logger.info(f"Conhecimento {knowledge_id} concluido com sucesso.")

    except ToolExecutionError as exc:
        logger.error(f"Erro ao processar o conhecimento {knowledge_id}: {exc}")
        update_knowledge_status(knowledge_id, status_id=1)
        raise
    except Exception as exc:
        logger.error(f"Erro ao processar o conhecimento {knowledge_id}: {exc}")
        update_knowledge_status(knowledge_id, status_id=1)
        raise SystemExit(1) from exc
    finally:
        if guard:
            await guard.close_now()


def _ensure_pending_knowledges_synced():
    stage2_jobs = list(get_completed_jobs_by_stage(stage_id=2))
    stage3_jobs = list(get_completed_jobs_by_stage(stage_id=3))
    completed_jobs = stage2_jobs + stage3_jobs
    if not completed_jobs:
        return

    processed_folders: set[str] = set()
    to_insert: Dict[str, List[Dict[str, Any]]] = {}

    for job in completed_jobs:
        folder_path = job['folder_path']
        if not folder_path or folder_path in processed_folders:
            continue
        processed_folders.add(folder_path)
        index_path = get_index_file_path(folder_path)
        index_data = load_index_data(index_path)
        entries = index_data.get('knowledges') or []
        if not entries:
            logger.warning(f"Indice vazio ao sincronizar conhecimentos para {folder_path}.")
            continue
        existing_count = count_knowledges_by_folder(folder_path)
        if existing_count >= len(entries):
            continue
        start_idx = max(existing_count, 0)
        index_path = get_index_file_path(folder_path)
        payload: List[Dict[str, Any]] = []
        for idx, entry in enumerate(entries[start_idx:], start=start_idx):
            sanitized = _sanitize_knowledge_entry(entry)
            files = sanitized.get('files') or []
            payload.append({
                'index': idx,
                'name': sanitized.get('name') or '',
                'description': sanitized.get('description') or '',
                'files': files,
                'folder_path': folder_path,
                'status_id': 1,
            })
        to_insert[folder_path] = payload

    for folder_path, payload in to_insert.items():
        if not payload:
            continue
        add_knowledges_from_json(payload)
        logger.info(f"{len(payload)} conhecimentos sincronizados a partir de {get_index_file_path(folder_path)}.")


async def run_stage3_cleanup(job_filter: Optional[int] = None):
    logger.info('Iniciando Estagio 3: Limpeza e Finalizacao de Jobs.')
    completed_stage2_jobs = get_completed_jobs_by_stage(stage_id=2)
    if job_filter is not None:
        completed_stage2_jobs = [job for job in completed_stage2_jobs if job['id'] == job_filter]

    if not completed_stage2_jobs:
        logger.info('Nenhum job para finalizar.')
        return

    for job in completed_stage2_jobs:
        job_id = job['id']
        folder_path = job['folder_path']
        if are_all_knowledges_completed_for_folder(folder_path):
            logger.info(f"Todos os conhecimentos para o job {job_id} estao concluidos. Finalizando...")
            update_job_state(job_id, stage_id=3, status_id=3)
            logger.info(f"Job {job_id} finalizado com sucesso.")


async def main():
    parser = argparse.ArgumentParser(description='Pipeline de extracao e geracao de conhecimento.')
    parser.add_argument('--input', type=str, help='Caminho para uma pasta com arquivos .txt ou .pdf para processar.')
    parser.add_argument('--mode', choices=['upload', 'docling'], default='upload', help='Define se os arquivos serao enviados (upload) ou convertidos via Docling (docling).')
    parser.add_argument('--job', type=int, help='Filtra a execucao para um unico job cadastrado no banco.')
    args = parser.parse_args()
    mode = (args.mode or 'upload').lower()
    job_filter = args.job

    logger.info(
        "Pipeline iniciado com input_dir={} | mode={} | job={}",
        args.input or "banco de jobs pendentes",
        mode,
        job_filter or "todos",
    )
    initialize_database()

    try:
        if args.input:
            logger.info("Processando pasta manual fornecida: {}", args.input)
            process_input_folder(args.input)
            await run_stage1_index_creation(mode, job_filter=job_filter)
            await process_pending_knowledges(mode, job_filter=job_filter)
            await run_stage3_cleanup(job_filter=job_filter)
        else:
            logger.info("Nenhuma pasta informada; executando stages pendentes do banco.")
            await process_pending_knowledges(mode, job_filter=job_filter)
            await run_stage3_cleanup(job_filter=job_filter)
        logger.info("Pipeline finalizado com sucesso.")
    except Exception as exc:
        logger.exception("Falha geral no pipeline: {}", exc)
        raise

async def _ensure_valid_json_patch(
    candidate: Optional[str],
    raw_output: str,
    generator,
    job_file_path: str,
    folder_path: str,
    attempt_context: str = "",
) -> Tuple[Dict, str]:
    label = attempt_context or "json-patch"
    _ = (generator, job_file_path, folder_path)
    base_candidate = candidate or _strip_code_fences(raw_output) or raw_output

    if not base_candidate or not base_candidate.strip():
        raise ValueError("JSON Patch vazio ou ausente.")

    normalized = _strip_code_fences(base_candidate) or base_candidate
    normalized = _sanitize_patch_text(normalized) or normalized

    try:
        data = json.loads(normalized)
        logger.debug(f"[{label}] JSON valido obtido.")
        return data, normalized
    except json.JSONDecodeError as exc:
        logger.warning(f"[{label}] JSON invalido ({exc}). Sera solicitada uma nova geracao ao modelo.")
        raise ValueError(f"JSON inválido: {exc}") from exc


if __name__ == '__main__':
    asyncio.run(main())
