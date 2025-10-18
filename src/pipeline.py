import argparse
import asyncio
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from database import (
    add_knowledges_from_json,
    are_all_knowledges_completed_for_job,
    create_job,
    create_batch_run,
    append_batch_item,
    get_unbatched_jobs,
    get_batch_items,
    get_completed_jobs_by_stage,
    get_pending_batch_runs,
    get_pending_jobs_by_stage,
    get_pending_knowledges,
    initialize_database,
    record_batch_file,
    record_batch_metrics,
    update_batch_item_output,
    update_job_state,
    update_batch_status,
    update_knowledge_status,
    set_batch_consumed,
)
from generators.adapta.claude_opus_generator import ClaudeOpusGenerator
from generators.adapta.gemini_generator import GeminiGenerator
from generators.adapta.gpt_generator import GPTGenerator
from utils.logger import logger
from prompt_manager import generate_knowledge_extraction_prompt
from utils.text_cleaner import remove_think_tags

INDEXES_PATH = 'indexes'
DOCS_PREFIX = 'docs_'
KNOWLEDGE_PROMPT_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_creation.txt')
MAX_WORDS_PER_UPLOAD = 400000
MAX_RETRIES = 10
INITIAL_RETRY_DELAY = 2.0
MAX_INDEX_CHUNK_SIZE = 300
UPLOAD_DELAY_SECONDS = 2.0
STAGING_BASE_DIR = '01_staging'
STAGING_BATCHES_DIR = os.path.join(STAGING_BASE_DIR, 'lotes')
STAGING_PHASE1_RESULTS_DIR = os.path.join(STAGING_BASE_DIR, 'fase_01_resultados')
STAGING_PHASE2_RESULTS_DIR = os.path.join(STAGING_BASE_DIR, 'fase_02_resultados')
PROMPT_LOG_FILE = os.path.join(STAGING_BASE_DIR, 'prompt_lote.txt')
DEFAULT_BATCH_SIZE_PHASE1 = 10
DEFAULT_BATCH_SIZE_PHASE2 = 5
BATCH_DEDUP_PROMPT = (
    "Voce e um especialista em organizacao de conhecimento. Analise os conhecimentos extraidos das transcricoes anexadas.\n\n"
    "TAREFA:\n"
    "1. Identifique conhecimentos que tratam do MESMO conceito/tecnica/ideia (nao apenas texto identico)\n"
    "2. Para cada grupo de conhecimentos similares:\n"
    "   - Crie UMA entrada consolidada\n"
    "   - Use o nome mais claro e descritivo\n"
    "   - Combine as descricoes preservando todas as nuances importantes\n"
    "   - Liste TODOS os arquivos fonte\n\n"
    "CRITERIOS DE SIMILARIDADE:\n"
    "- Mesmo conceito tecnico com nomenclaturas diferentes\n"
    "- Descricoes complementares do mesmo assunto\n"
    "- Exemplos diferentes da mesma tecnica\n\n"
    "IMPORTANTE:\n"
    "- Mantenha conhecimentos DISTINTOS separados mesmo que relacionados\n"
    "- Nao perca informacao relevante na consolidacao\n"
    "- Quando em duvida, mantenha separado\n\n"
    "Retorne JSON no formato especificado."
)
PROCESSED_DIR = '02_processed'
FINAL_INDEX_PATH = os.path.join(PROCESSED_DIR, 'indice_final.json')

os.makedirs(INDEXES_PATH, exist_ok=True)


os.makedirs(INDEXES_PATH, exist_ok=True)

os.makedirs(INDEXES_PATH, exist_ok=True)

CHAT_LOG_PATH = Path(INDEXES_PATH) / 'chat.md'
MAX_PATCH_RETRIES = 6


def _ensure_staging_directories() -> None:
    for path in [
        STAGING_BASE_DIR,
        STAGING_BATCHES_DIR,
        STAGING_PHASE1_RESULTS_DIR,
        STAGING_PHASE2_RESULTS_DIR,
    ]:
        os.makedirs(path, exist_ok=True)


def _chunk_sequence(sequence, chunk_size):
    chunk = []
    for item in sequence:
        chunk.append(item)
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _build_lote_directory(batch_id: int) -> Path:
    padded = f"lote_{batch_id:05d}"
    lote_dir = Path(STAGING_BATCHES_DIR) / padded
    (lote_dir / 'input').mkdir(parents=True, exist_ok=True)
    (lote_dir / 'output').mkdir(parents=True, exist_ok=True)
    return lote_dir


def _write_batch_prompt(prompt_text: str) -> str:
    Path(STAGING_BASE_DIR).mkdir(parents=True, exist_ok=True)
    Path(PROMPT_LOG_FILE).write_text(prompt_text, encoding='utf-8')
    return PROMPT_LOG_FILE


def _prepare_batch_input_file(job_row, destination_dir: Path, order_index: int) -> Optional[str]:
    source_path = job_row['file_path']
    if not source_path or not os.path.isfile(source_path):
        logger.warning(f"Arquivo de entrada do job {job_row['id']} nao encontrado: {source_path}")
        return None

    base_name = os.path.basename(source_path)
    destination_name = f"{order_index:03d}_{base_name}"
    destination_path = destination_dir / destination_name

    try:
        shutil.copy2(source_path, destination_path)
    except Exception as exc:
        logger.error(f"Falha ao copiar {source_path} para {destination_path}: {exc}")
        return None

    return str(destination_path)


def _write_lote_config(config_path: Path, payload: Dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open('w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _load_lote_config(batch_id: int) -> Dict[str, Any]:
    lote_dir = Path(STAGING_BATCHES_DIR) / f"lote_{batch_id:05d}"
    config_path = lote_dir / 'lote_config.json'
    try:
        return json.loads(config_path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        logger.warning(f"Config JSON invalido para o lote {batch_id}.")
        return {}


def _resolve_batch_output_file(batch_id: int) -> Optional[Path]:
    config = _load_lote_config(batch_id)
    candidate = config.get('output_file')
    if candidate and os.path.isfile(candidate):
        return Path(candidate)

    lote_dir = Path(STAGING_BATCHES_DIR) / f"lote_{batch_id:05d}"
    output_dir = lote_dir / 'output'
    default_name = output_dir / f"lote_{batch_id:05d}_consolidado.json"
    if default_name.exists():
        return default_name
    try:
        first_json = next(output_dir.glob('*.json'))
        return first_json
    except StopIteration:
        fallback = Path(STAGING_PHASE1_RESULTS_DIR) / f"lote_{batch_id:05d}_consolidado.json"
        if fallback.exists():
            return fallback
    return None


def _prepare_existing_output_file(source_path: Path, destination_dir: Path, order_index: int) -> Optional[str]:
    if not source_path.exists():
        return None

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_name = f"{order_index:03d}_{source_path.name}"
    destination_path = destination_dir / destination_name
    try:
        shutil.copy2(source_path, destination_path)
    except Exception as exc:
        logger.error(f"Falha ao copiar {source_path} para {destination_path}: {exc}")
        return None
    return str(destination_path)


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[\s_]+", '-', text)
    text = re.sub(r"[^a-z0-9-]", '', text)
    return text.strip('-')


def _sanitize_temp_identifier(identifier: str) -> str:
    sanitized = re.sub(r'[^A-Za-z0-9_-]+', '-', identifier)
    sanitized = re.sub(r'-{2,}', '-', sanitized)
    sanitized = sanitized.strip('-_')
    return sanitized or 'arquivo'


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
    folder_name = os.path.basename(os.path.normpath(folder_path)) or 'indice'
    slug = slugify(folder_name) or 'indice'
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
    folder_name = os.path.basename(os.path.normpath(folder_path)) or 'conteudo'
    folder_slug = slugify(folder_name) or 'conteudo'
    return f"{DOCS_PREFIX}{folder_slug}"


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


def _extract_related_ids(row: Dict[str, Any]) -> List[int]:
    raw = None
    if isinstance(row, dict):
        raw = row.get('related_ids')
    if not raw:
        return []
    related: List[int] = []
    seen = set()
    for value in str(raw).split('||'):
        value = value.strip()
        if not value:
            continue
        try:
            related_id = int(value)
        except ValueError:
            continue
        if related_id <= 0 or related_id in seen:
            continue
        seen.add(related_id)
        related.append(related_id)
    return related


def _lookup_related_names(index_data: Dict[str, Any], related_ids: List[int]) -> List[str]:
    if not related_ids:
        return []

    knowledges = index_data.get('knowledges') or []
    names: List[str] = []
    seen = set()

    for raw_id in related_ids:
        try:
            idx = int(raw_id) - 1  # knowledge_id_from_json e 1-based
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(knowledges):
            continue
        name = str(knowledges[idx].get('name') or '').strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    return names


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
) -> List[Tuple[Path, bool]]:
    if not file_paths:
        raise ValueError("Nenhum arquivo fonte informado para upload.")

    if consolidate or len(file_paths) == 1:
        upload_path, cleanup = _prepare_upload_file(
            file_paths=file_paths,
            base_dir=base_dir,
            prefix=prefix,
            prefer_original=prefer_original,
        )
        return [(upload_path, cleanup)]

    specs: List[Tuple[Path, bool]] = []
    for source in file_paths:
        source_path = Path(source)
        if source_path.suffix.lower() == '.txt':
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
    prefer_original: bool
) -> Tuple[Path, bool]:
    if not file_paths:
        raise ValueError("Nenhum arquivo fonte informado para upload.")

    if prefer_original and len(file_paths) == 1:
        return Path(file_paths[0]), False

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
        if source_path.suffix.lower() == '.txt':
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


async def _call_generator_with_existing_uploads(
    generator,
    prompt: Optional[str],
    upload_infos: List[Tuple[Dict[str, Any], bool, Path]],
    messages: Optional[List[Dict[str, str]]] = None,
    tool: Optional[str] = None,
) -> str:
    if messages is None:
        if prompt is None:
            raise ValueError("Prompt ou mensagens devem ser fornecidos para chamada ao gerador.")
        payload_messages = [{'role': 'user', 'content': prompt}]
    else:
        payload_messages = [dict(message) for message in messages]

    logger.debug(f'Iniciando chamada ao modelo com {len(upload_infos)} arquivo(s) anexados.')
    response = await generator.call_model_with_messages(
        payload_messages,
        file_ids=[info for info, _, _ in upload_infos],
        tool=tool,
    )
    logger.debug('Chamada ao modelo concluida com sucesso.')
    return response


async def _cleanup_upload_infos(
    generator,
    upload_infos: List[Tuple[Dict[str, Any], bool, Path]],
    cleanup_local_paths: bool,
) -> None:
    for upload_info, cleanup, upload_path in upload_infos:
        file_id = upload_info.get("id") if upload_info else None
        if file_id:
            try:
                await generator.client.excluir_arquivo(file_id)
            except Exception as exc:
                logger.warning(f"Falha ao excluir arquivo remoto {file_id}: {exc}")
        if cleanup_local_paths and cleanup:
            try:
                if upload_path.exists():
                    upload_path.unlink()
            except Exception as exc:
                logger.warning(f"Falha ao remover arquivo temporario {upload_path}: {exc}")
    if cleanup_local_paths:
        logger.debug('Uploads temporarios limpos com sucesso.')


async def _call_generator_with_uploads(
    generator,
    prompt: Optional[str],
    uploads: List[Tuple[Path, bool]],
    messages: Optional[List[Dict[str, str]]] = None,
    tool: Optional[str] = None,
    upload_delay: float = 0.0,
) -> str:
    upload_infos = await _perform_uploads(generator, uploads, upload_delay)
    try:
        return await _call_generator_with_existing_uploads(
            generator,
            prompt,
            upload_infos,
            messages=messages,
            tool=tool,
        )
    finally:
        await _cleanup_upload_infos(generator, upload_infos, cleanup_local_paths=True)


async def _call_with_retries(
    generator,
    prompt: Optional[str],
    source_paths: List[str],
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
    tool: Optional[str] = None,
    prepared_uploads: Optional[List[Tuple[Path, bool]]] = None,
    persist_uploads: bool = False,
    upload_context: Optional[Dict[Any, List[Tuple[Dict[str, Any], bool, Path]]]] = None,
    upload_delay: float = 0.0,
) -> str:
    if not source_paths:
        raise ValueError("Nenhum arquivo fonte informado para upload.")
    if prompt is None and messages is None:
        raise ValueError("Prompt ou mensagens devem ser fornecidos para a chamada ao gerador.")

    if generator_cycle:
        cycle = [gen for gen in generator_cycle if gen is not None]
        if not cycle:
            raise ValueError("generator_cycle deve conter pelo menos um gerador valido.")
    else:
        if generator is None:
            raise ValueError("Nenhum gerador primario informado para a chamada.")
        cycle = [generator]

    delay = initial_delay
    last_error: Optional[Exception] = None
    local_prepared_uploads = prepared_uploads

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
            if uploads is None:
                uploads = _prepare_upload_specs(
                    file_paths=source_paths,
                    base_dir=base_dir,
                    prefix=prefix,
                    prefer_original=prefer_original_when_single,
                    consolidate=consolidate,
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
                return await _call_generator_with_existing_uploads(
                    current_generator,
                    prompt,
                    upload_infos,
                    messages=messages,
                    tool=tool,
                )

            return await _call_generator_with_uploads(
                current_generator,
                prompt,
                uploads,
                messages=messages,
                tool=tool,
                upload_delay=upload_delay,
            )
        except Exception as exc:
            last_error = exc
            if not persist_uploads and prepared_uploads is None and uploads:
                for path, cleanup in uploads:
                    if cleanup and path.exists():
                        try:
                            path.unlink()
                        except Exception:
                            pass
            if attempt == max_retries:
                raise
            logger.warning(f"Tentativa {attempt}/{max_retries} falhou ({exc}). Nova tentativa em {delay:.1f}s...")
            await asyncio.sleep(delay)
            delay *= 1.5

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


def process_input_folder(folder_path):
    logger.info(f"Escaneando a pasta de entrada: {folder_path}")
    if not os.path.isdir(folder_path):
        logger.error(f"O caminho '{folder_path}' nao e um diretorio valido.")
        return

    for filename in os.listdir(folder_path):
        if filename.endswith('.txt'):
            file_path = os.path.abspath(os.path.join(folder_path, filename))
            create_job(file_path, filename, folder_path)


async def run_stage1_index_creation():
    logger.info('Iniciando Estagio 1: Criacao de Indice de Conhecimento.')
    pending_jobs = get_pending_jobs_by_stage(stage_id=1)

    if not pending_jobs:
        logger.info('Nenhum job pendente para o Estagio 1.')
        return

    claude_generator = ClaudeOpusGenerator()
    gpt_generator = GPTGenerator()
    gemini_generator = GeminiGenerator()

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

        prompt = generate_knowledge_extraction_prompt(
            current_file_name,
            existing_index_paths=index_part_paths if has_existing_index else None,
            existing_index_display_names=index_display_names,
        )
        source_files = [job['file_path']]
        if index_part_paths:
            source_files.extend(index_part_paths)

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

        try:
            prepared_uploads = _prepare_upload_specs(
                file_paths=source_files,
                base_dir=folder_path,
                prefix='stage1',
                prefer_original=True,
                consolidate=False,
            )
            while True:
                raw_response = await _call_with_retries(
                    generator=gemini_generator,
                    prompt=None,
                    source_paths=source_files,
                    base_dir=folder_path,
                    prefix='stage1',
                    prefer_original_when_single=True,
                    consolidate=False,
                    generator_cycle=[gemini_generator, claude_generator, gpt_generator],
                    messages=conversation,
                    tool="",
                    prepared_uploads=prepared_uploads,
                    persist_uploads=True,
                    upload_context=persistent_upload_context,
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
                        }
                        for idx, entry in enumerate(sanitized_all)
                    ]
                break

            save_index_data(index_path, index_data)

            if knowledges_for_stage2:
                add_knowledges_from_json(job_id, knowledges_for_stage2)
                logger.info(f"{len(knowledges_for_stage2)} conhecimentos inseridos no banco de dados para o job {job_id}.")
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

async def process_pending_knowledges():
    logger.info('Iniciando Estagio 2: Criacao de Arquivos de Conhecimento.')
    pending_knowledges = get_pending_knowledges()

    if not pending_knowledges:
        logger.info('Nenhum conhecimento pendente para processar.')
        return

    generator = ClaudeOpusGenerator()
    with open(KNOWLEDGE_PROMPT_PATH, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    index_cache: Dict[str, Dict] = {}

    for knowledge in pending_knowledges:
        knowledge_id = knowledge['knowledge_id']
        folder_path = knowledge['job_folder_path']
        source_files = _extract_file_names(knowledge)
        related_ids = _extract_related_ids(knowledge)

        if folder_path not in index_cache:
            index_cache[folder_path] = load_index_data(get_index_file_path(folder_path))
        index_data = index_cache[folder_path]
        related_names = _lookup_related_names(index_data, related_ids)

        logger.info(f"Processando conhecimento ID: {knowledge_id} - {knowledge['knowledge_name']}")

        try:
            update_knowledge_status(knowledge_id, status_id=2)

            consolidated_sources: List[str] = []
            if source_files:
                for file_name in source_files:
                    file_path = os.path.join(folder_path, file_name)
                    if os.path.isfile(file_path):
                        consolidated_sources.append(file_path)
                    else:
                        logger.warning(f"Arquivo {file_name} nao encontrado em {folder_path}.")

            if not consolidated_sources:
                consolidated_sources.append(knowledge['job_file_path'])

            prompt = prompt_template.replace('{knowledge_category}', knowledge['knowledge_category'])
            prompt = prompt.replace('{knowledge_name}', knowledge['knowledge_name'])
            if related_names:
                related_block = "Conhecimentos relacionados fornecidos:\n" + "\n".join(f"- {name}" for name in related_names)
            else:
                related_block = "Nenhum conhecimento relacionado adicional foi informado."
            prompt = prompt.replace('{related_context}', related_block)
            upload_display_names_stage2 = _predict_upload_names(
                consolidated_sources,
                folder_path,
                prefix='stage2',
                prefer_original=True,
                consolidate=True,
            )
            source_prompt = _build_files_prompt_segment(consolidated_sources, folder_path, upload_display_names_stage2)
            if source_prompt:
                prompt += source_prompt

            markdown_output = await _call_with_retries(
                generator=generator,
                prompt=prompt,
                source_paths=consolidated_sources,
                base_dir=folder_path,
                prefix='stage2',
                prefer_original_when_single=True,
                tool="",
            )
            markdown_output = remove_think_tags(markdown_output)

            knowledge_slug = slugify(knowledge['knowledge_name'])
            output_dir = get_docs_output_dir(folder_path)
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"{knowledge_slug}.md")

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_output)
            logger.info(f"Arquivo Markdown salvo em: {output_path}")

            update_knowledge_status(knowledge_id, status_id=3)
            logger.info(f"Conhecimento {knowledge_id} concluido com sucesso.")

        except Exception as e:
            logger.error(f"Erro ao processar o conhecimento {knowledge_id}: {e}")
            update_knowledge_status(knowledge_id, status_id=1)


async def run_stage3_cleanup():
    logger.info('Iniciando Estagio 3: Limpeza e Finalizacao de Jobs.')
    completed_stage2_jobs = get_completed_jobs_by_stage(stage_id=2)

    if not completed_stage2_jobs:
        logger.info('Nenhum job para finalizar.')
        return

    for job in completed_stage2_jobs:
        job_id = job['id']
        if are_all_knowledges_completed_for_job(job_id):
            logger.info(f"Todos os conhecimentos para o job {job_id} estao concluidos. Finalizando...")
            update_job_state(job_id, stage_id=3, status_id=3)
            logger.info(f"Job {job_id} finalizado com sucesso.")


async def run_stage4_batch_preparation(max_batch_size_phase1: int = DEFAULT_BATCH_SIZE_PHASE1):
    logger.info('Iniciando Estagio 4: Preparacao de Lotes para Merge.')
    _ensure_staging_directories()

    prompt_path = _write_batch_prompt(BATCH_DEDUP_PROMPT)
    fetch_limit = max(max_batch_size_phase1 * 10, max_batch_size_phase1)
    pending_jobs = get_unbatched_jobs(limit=fetch_limit)

    if not pending_jobs:
        logger.info('Nenhum job elegivel para novos lotes.')
        return

    for chunk in _chunk_sequence(pending_jobs, max_batch_size_phase1):
        batch_id = create_batch_run(
            stage='phase1',
            max_batch_size=max_batch_size_phase1,
            token_estimate=0,
            parent_batch_id=None,
        )
        lote_dir = _build_lote_directory(batch_id)
        input_dir = lote_dir / 'input'
        config_entries: List[Dict[str, Any]] = []

        for order, job_row in enumerate(chunk):
            prepared_path = _prepare_batch_input_file(job_row, input_dir, order)
            if not prepared_path:
                continue
            item_id = append_batch_item(
                batch_id=batch_id,
                job_id=job_row['id'],
                knowledge_id=None,
                input_path=prepared_path,
                input_order=order,
            )
            config_entries.append({
                'batch_item_id': item_id,
                'job_id': job_row['id'],
                'original_path': job_row['file_path'],
                'input_path': prepared_path,
                'input_order': order,
                'file_name': os.path.basename(prepared_path),
            })

        if not config_entries:
            logger.warning(f"Nenhum arquivo valido encontrado para o lote {batch_id}. Marcando como descartado.")
            update_batch_status(
                batch_id,
                status_id=5,
                input_count=0,
                error_message='Nenhum arquivo valido para o lote',
                prompt_path=prompt_path,
            )
            continue

        lote_config_path = lote_dir / 'lote_config.json'
        config_payload = {
            'batch_id': batch_id,
            'stage': 'phase1',
            'max_batch_size': max_batch_size_phase1,
            'prompt_file': prompt_path,
            'parent_batches': [],
            'jobs': config_entries,
        }
        _write_lote_config(lote_config_path, config_payload)
        try:
            file_size = lote_config_path.stat().st_size
        except OSError:
            file_size = 0

        record_batch_file(batch_id, str(lote_config_path), file_size_bytes=file_size)
        update_batch_status(
            batch_id,
            status_id=1,
            input_count=len(config_entries),
            prompt_path=prompt_path,
        )
        logger.info(f"Lote {batch_id} preparado com {len(config_entries)} entradas.")


async def run_stage5_batch_execution():
    logger.info('Iniciando Estagio 5: Execucao de Lotes (Fase 1).')
    _ensure_staging_directories()

    pending_batches = get_pending_batch_runs(stage='phase1', status_filter=(1,))
    if not pending_batches:
        logger.info('Nenhum lote pendente para execucao.')
        return

    gemini_generator = GeminiGenerator()
    claude_generator = ClaudeOpusGenerator()
    gpt_generator = GPTGenerator()

    for batch in pending_batches:
        batch_id = batch['id']
        logger.info(f"Processando lote {batch_id} (fase 1).")
        lote_dir = _build_lote_directory(batch_id)
        input_dir = lote_dir / 'input'
        output_dir = lote_dir / 'output'
        lote_config_path = lote_dir / 'lote_config.json'

        items = get_batch_items(batch_id)
        if not items:
            logger.warning(f"Lote {batch_id} nao possui itens registrados. Marcando como descartado.")
            update_batch_status(
                batch_id,
                status_id=5,
                error_message='Lote sem itens para processamento.',
                finished_at=datetime.utcnow().isoformat(),
            )
            continue

        valid_items = []
        input_paths: List[str] = []
        for item in items:
            input_path = item['input_path']
            if input_path and os.path.isfile(input_path):
                valid_items.append(item)
                input_paths.append(input_path)
            else:
                update_batch_item_output(
                    item['id'],
                    status_id=5,
                    notes='Arquivo de entrada ausente para o lote.',
                )

        if not input_paths:
            logger.error(f"Lote {batch_id} sem arquivos validos para upload. Marcando como falha.")
            update_batch_status(
                batch_id,
                status_id=4,
                error_message='Nenhum arquivo valido encontrado para o lote.',
                finished_at=datetime.utcnow().isoformat(),
            )
            continue

        for item in valid_items:
            update_batch_item_output(item['id'], status_id=2)

        upload_display_names = _predict_upload_names(
            input_paths,
            base_dir=str(lote_dir),
            prefix='batch',
            prefer_original=True,
            consolidate=False,
        )
        files_prompt = _build_files_prompt_segment(input_paths, str(lote_dir), upload_display_names)
        prompt = BATCH_DEDUP_PROMPT + files_prompt
        prompt_path = _write_batch_prompt(prompt)

        started_at = datetime.utcnow().isoformat()
        update_batch_status(
            batch_id,
            status_id=2,
            input_count=len(input_paths),
            started_at=started_at,
            prompt_path=prompt_path,
        )

        try:
            response_text = await _call_with_retries(
                generator=gemini_generator,
                prompt=prompt,
                source_paths=input_paths,
                base_dir=str(lote_dir),
                prefix='batch',
                prefer_original_when_single=True,
                consolidate=False,
                generator_cycle=[gemini_generator, claude_generator, gpt_generator],
                upload_delay=UPLOAD_DELAY_SECONDS,
            )
            cleaned_text = remove_think_tags(response_text)
            sanitized = _sanitize_patch_text(cleaned_text) or cleaned_text
            candidate = _extract_json_candidate(sanitized) or sanitized
            candidate = _strip_code_fences(candidate) or candidate
            payload = json.loads(candidate)
            knowledges = payload.get('knowledges') if isinstance(payload, dict) else None
            if not isinstance(knowledges, list):
                raise ValueError("Resposta nao contem chave 'knowledges' com lista valida.")

            output_filename = f"lote_{batch_id:05d}_consolidado.json"
            output_path = output_dir / output_filename
            with output_path.open('w', encoding='utf-8') as outfile:
                json.dump(payload, outfile, ensure_ascii=False, indent=2)

            phase_copy_path = Path(STAGING_PHASE1_RESULTS_DIR) / output_filename
            shutil.copy2(output_path, phase_copy_path)

            try:
                config_data = json.loads(lote_config_path.read_text(encoding='utf-8'))
            except FileNotFoundError:
                config_data = {}
            except json.JSONDecodeError:
                config_data = {}
            config_data.update({
                'output_file': str(output_path),
                'output_count': len(knowledges),
                'updated_at': datetime.utcnow().isoformat(),
            })
            _write_lote_config(lote_config_path, config_data)

            record_batch_file(batch_id, str(output_path), file_size_bytes=output_path.stat().st_size)
            record_batch_file(batch_id, str(phase_copy_path), file_size_bytes=phase_copy_path.stat().st_size)
            record_batch_metrics(batch_id, [
                ('input_files', len(input_paths)),
                ('output_knowledges', len(knowledges)),
                ('prompt_length', len(prompt)),
            ])

            for item in valid_items:
                update_batch_item_output(
                    item['id'],
                    output_path=str(output_path),
                    status_id=3,
                )

            finished_at = datetime.utcnow().isoformat()
            update_batch_status(
                batch_id,
                status_id=3,
                output_count=len(knowledges),
                finished_at=finished_at,
                prompt_path=prompt_path,
            )
            logger.info(f"Lote {batch_id} concluido com sucesso. {len(knowledges)} conhecimentos consolidados.")
        except Exception as exc:
            finished_at = datetime.utcnow().isoformat()
            logger.error(f"Erro ao processar o lote {batch_id}: {exc}")
            update_batch_status(
                batch_id,
                status_id=4,
                error_message=str(exc),
                finished_at=finished_at,
                prompt_path=prompt_path,
            )
            for item in valid_items:
                update_batch_item_output(
                    item['id'],
                    status_id=1,
                    notes='Lote falhou; item retornou para pendente.',
                )


async def run_stage6_phase2_preparation(max_batch_size_phase2: int = DEFAULT_BATCH_SIZE_PHASE2):
    logger.info('Iniciando Estagio 6: Preparacao de Lotes (Fase 2).')
    _ensure_staging_directories()

    available_phase1 = get_pending_batch_runs(stage='phase1', status_filter=(3,), consumed=False)
    if len(available_phase1) <= 1:
        logger.info('Menos de dois lotes finalizados na fase 1; nenhuma preparacao de fase 2 necessaria.')
        return

    for chunk in _chunk_sequence(available_phase1, max_batch_size_phase2):
        successful_entries: List[Dict[str, Any]] = []
        for batch_row in chunk:
            output_file = _resolve_batch_output_file(batch_row['id'])
            if not output_file or not output_file.exists():
                logger.warning(f"Output do lote {batch_row['id']} nao encontrado; ignorando na montagem da fase 2.")
                continue
            successful_entries.append({'row': batch_row, 'output': output_file})

        if len(successful_entries) <= 1:
            logger.info('Quantidade insuficiente de arquivos validos para montar lote da fase 2.')
            continue

        parent_ids = [entry['row']['id'] for entry in successful_entries]
        batch_id = create_batch_run(
            stage='phase2',
            max_batch_size=max_batch_size_phase2,
            token_estimate=0,
            parent_batch_id=parent_ids[0],
        )
        lote_dir = _build_lote_directory(batch_id)
        input_dir = lote_dir / 'input'
        config_entries: List[Dict[str, Any]] = []
        consumed_success: List[int] = []

        for order, entry in enumerate(successful_entries):
            parent_batch = entry['row']
            output_path = entry['output']
            prepared_path = _prepare_existing_output_file(output_path, input_dir, order)
            if not prepared_path:
                logger.error(f"Falha ao preparar o arquivo do lote {parent_batch['id']} para a fase 2.")
                continue

            append_batch_item(
                batch_id=batch_id,
                job_id=None,
                knowledge_id=None,
                input_path=prepared_path,
                input_order=order,
                status_id=1,
                notes=f"parent_batch={parent_batch['id']}",
            )
            config_entries.append({
                'batch_item_order': order,
                'parent_batch_id': parent_batch['id'],
                'source_output': str(output_path),
                'input_path': prepared_path,
            })
            consumed_success.append(parent_batch['id'])

        if len(config_entries) <= 1:
            logger.warning(f"Nao foi possivel concluir a montagem do lote {batch_id} da fase 2; revertendo consumo.")
            set_batch_consumed(consumed_success, None)
            update_batch_status(
                batch_id,
                status_id=5,
                error_message='Lote da fase 2 sem entradas suficientes.',
            )
            continue

        lote_config_path = Path(STAGING_BATCHES_DIR) / f"lote_{batch_id:05d}" / 'lote_config.json'
        config_payload = {
            'batch_id': batch_id,
            'stage': 'phase2',
            'max_batch_size': max_batch_size_phase2,
            'parent_batches': consumed_success,
            'source_stage': 'phase1',
            'entries': config_entries,
        }
        _write_lote_config(lote_config_path, config_payload)
        try:
            file_size = lote_config_path.stat().st_size
        except OSError:
            file_size = 0
        record_batch_file(batch_id, str(lote_config_path), file_size_bytes=file_size)

        prompt_path = _write_batch_prompt(BATCH_DEDUP_PROMPT)
        update_batch_status(
            batch_id,
            status_id=1,
            input_count=len(config_entries),
            prompt_path=prompt_path,
        )

        timestamp = datetime.utcnow().isoformat()
        set_batch_consumed(consumed_success, timestamp)
        logger.info(f"Lote {batch_id} da fase 2 preparado com {len(config_entries)} entradas.")


async def run_stage7_phase2_execution():
    logger.info('Iniciando Estagio 7: Execucao de Lotes (Fase 2).')
    _ensure_staging_directories()

    pending_batches = get_pending_batch_runs(stage='phase2', status_filter=(1,))
    if not pending_batches:
        logger.info('Nenhum lote da fase 2 pendente para execucao.')
        return

    gemini_generator = GeminiGenerator()
    claude_generator = ClaudeOpusGenerator()
    gpt_generator = GPTGenerator()

    for batch in pending_batches:
        batch_id = batch['id']
        logger.info(f"Executando lote {batch_id} (fase 2).")
        lote_dir = _build_lote_directory(batch_id)
        output_dir = lote_dir / 'output'
        lote_config_path = lote_dir / 'lote_config.json'
        config = _load_lote_config(batch_id)
        parent_batches = config.get('parent_batches', [])

        items = get_batch_items(batch_id)
        if not items:
            logger.warning(f"Lote {batch_id} nao possui itens cadastrados. Marcando como descartado.")
            update_batch_status(
                batch_id,
                status_id=5,
                error_message='Lote sem itens cadastrados.',
                finished_at=datetime.utcnow().isoformat(),
            )
            set_batch_consumed(parent_batches, None)
            continue

        valid_items = []
        input_paths: List[str] = []
        for item in items:
            input_path = item['input_path']
            if input_path and os.path.isfile(input_path):
                valid_items.append(item)
                input_paths.append(input_path)
            else:
                update_batch_item_output(
                    item['id'],
                    status_id=5,
                    notes='Arquivo de entrada ausente para fase 2.',
                )

        if not input_paths:
            logger.error(f"Nenhum arquivo valido encontrado para o lote {batch_id}.")
            update_batch_status(
                batch_id,
                status_id=4,
                error_message='Nenhum arquivo valido encontrado.',
                finished_at=datetime.utcnow().isoformat(),
            )
            set_batch_consumed(parent_batches, None)
            continue

        for item in valid_items:
            update_batch_item_output(item['id'], status_id=2)

        upload_display_names = _predict_upload_names(
            input_paths,
            base_dir=str(lote_dir),
            prefix='phase2',
            prefer_original=True,
            consolidate=False,
        )
        files_prompt = _build_files_prompt_segment(input_paths, str(lote_dir), upload_display_names)
        prompt = BATCH_DEDUP_PROMPT + files_prompt
        prompt_path = _write_batch_prompt(prompt)

        started_at = datetime.utcnow().isoformat()
        update_batch_status(
            batch_id,
            status_id=2,
            input_count=len(input_paths),
            started_at=started_at,
            prompt_path=prompt_path,
        )

        try:
            response_text = await _call_with_retries(
                generator=gemini_generator,
                prompt=prompt,
                source_paths=input_paths,
                base_dir=str(lote_dir),
                prefix='phase2',
                prefer_original_when_single=True,
                consolidate=False,
                generator_cycle=[gemini_generator, claude_generator, gpt_generator],
                upload_delay=UPLOAD_DELAY_SECONDS,
            )
            cleaned_text = remove_think_tags(response_text)
            sanitized = _sanitize_patch_text(cleaned_text) or cleaned_text
            candidate = _extract_json_candidate(sanitized) or sanitized
            candidate = _strip_code_fences(candidate) or candidate
            payload = json.loads(candidate)
            knowledges = payload.get('knowledges') if isinstance(payload, dict) else None
            if not isinstance(knowledges, list):
                raise ValueError("Resposta nao contem a chave 'knowledges' com lista valida.")

            output_filename = f"fase2_lote_{batch_id:05d}_consolidado.json"
            output_path = output_dir / output_filename
            with output_path.open('w', encoding='utf-8') as outfile:
                json.dump(payload, outfile, ensure_ascii=False, indent=2)

            phase_copy_path = Path(STAGING_PHASE2_RESULTS_DIR) / output_filename
            shutil.copy2(output_path, phase_copy_path)

            config.update({
                'output_file': str(output_path),
                'output_count': len(knowledges),
                'parent_batches': parent_batches,
                'updated_at': datetime.utcnow().isoformat(),
            })
            _write_lote_config(lote_config_path, config)

            record_batch_file(batch_id, str(output_path), file_size_bytes=output_path.stat().st_size)
            record_batch_file(batch_id, str(phase_copy_path), file_size_bytes=phase_copy_path.stat().st_size)
            record_batch_metrics(batch_id, [
                ('input_files', len(input_paths)),
                ('output_knowledges', len(knowledges)),
                ('prompt_length', len(prompt)),
            ])

            for item in valid_items:
                update_batch_item_output(
                    item['id'],
                    output_path=str(output_path),
                    status_id=3,
                )

            finished_at = datetime.utcnow().isoformat()
            update_batch_status(
                batch_id,
                status_id=3,
                output_count=len(knowledges),
                finished_at=finished_at,
                prompt_path=prompt_path,
            )
            logger.info(f"Lote {batch_id} da fase 2 concluido com {len(knowledges)} conhecimentos.")
        except Exception as exc:
            finished_at = datetime.utcnow().isoformat()
            logger.error(f"Erro ao processar o lote {batch_id} da fase 2: {exc}")
            update_batch_status(
                batch_id,
                status_id=4,
                error_message=str(exc),
                finished_at=finished_at,
                prompt_path=prompt_path,
            )
            set_batch_consumed(parent_batches, None)
            for item in valid_items:
                update_batch_item_output(
                    item['id'],
                    status_id=1,
                    notes='Falha na fase 2; item retorna a pendente.',
                )


async def run_stage8_finalize_index():
    logger.info('Iniciando Estagio 8: Finalizacao do indice consolidado.')
    _ensure_staging_directories()
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    available_phase2 = get_pending_batch_runs(stage='phase2', status_filter=(3,), consumed=False)
    if not available_phase2:
        fallback_phase1 = get_pending_batch_runs(stage='phase1', status_filter=(3,), consumed=False)
        if len(fallback_phase1) == 1:
            source_path = _resolve_batch_output_file(fallback_phase1[0]['id'])
            if source_path and source_path.exists():
                shutil.copy2(source_path, FINAL_INDEX_PATH)
                timestamp = datetime.utcnow().isoformat()
                set_batch_consumed([fallback_phase1[0]['id']], timestamp)
                record_batch_file(fallback_phase1[0]['id'], FINAL_INDEX_PATH, file_size_bytes=os.path.getsize(FINAL_INDEX_PATH))
                logger.info('Indice final gerado a partir de unico lote da fase 1.')
            else:
                logger.warning('Arquivo de saida do lote unico da fase 1 nao localizado; finalizacao ignorada.')
        else:
            logger.info('Nenhum lote pendente para finalizacao.')
        return

    sources_info: List[Dict[str, Any]] = []
    for batch in available_phase2:
        output_path = _resolve_batch_output_file(batch['id'])
        if output_path and output_path.exists():
            sources_info.append({'batch': batch, 'path': output_path})
        else:
            logger.warning(f"Output do lote da fase 2 {batch['id']} nao encontrado; ignorando.")

    if not sources_info:
        logger.info('Nenhum arquivo valido encontrado entre os lotes da fase 2 para finalizar.')
        return

    parent_batch_ids = [info['batch']['id'] for info in sources_info]
    final_batch_id = create_batch_run(
        stage='final',
        max_batch_size=len(sources_info),
        token_estimate=0,
        parent_batch_id=parent_batch_ids[0],
    )
    lote_dir = _build_lote_directory(final_batch_id)
    input_dir = lote_dir / 'input'
    output_dir = lote_dir / 'output'
    config_entries: List[Dict[str, Any]] = []

    for order, info in enumerate(sources_info):
        prepared_path = _prepare_existing_output_file(Path(info['path']), input_dir, order)
        if not prepared_path:
            logger.error(f"Falha ao preparar arquivo do lote {info['batch']['id']} para consolidacao final.")
            continue
        append_batch_item(
            batch_id=final_batch_id,
            job_id=None,
            knowledge_id=None,
            input_path=prepared_path,
            input_order=order,
            status_id=1,
            notes=f"parent_batch={info['batch']['id']}",
        )
        config_entries.append({
            'batch_item_order': order,
            'parent_batch_id': info['batch']['id'],
            'source_output': str(info['path']),
            'input_path': prepared_path,
        })

    if not config_entries:
        logger.error('Nenhum arquivo preparado para consolidacao final.')
        update_batch_status(
            final_batch_id,
            status_id=4,
            error_message='Consolidacao final sem entradas validas.',
            finished_at=datetime.utcnow().isoformat(),
        )
        set_batch_consumed(parent_batch_ids, None)
        return

    lote_config_path = Path(STAGING_BATCHES_DIR) / f"lote_{final_batch_id:05d}" / 'lote_config.json'
    config_payload = {
        'batch_id': final_batch_id,
        'stage': 'final',
        'parent_batches': parent_batch_ids,
        'entries': config_entries,
    }
    _write_lote_config(lote_config_path, config_payload)
    try:
        file_size = lote_config_path.stat().st_size
    except OSError:
        file_size = 0
    record_batch_file(final_batch_id, str(lote_config_path), file_size_bytes=file_size)

    prompt_path = _write_batch_prompt(BATCH_DEDUP_PROMPT)
    update_batch_status(
        final_batch_id,
        status_id=2 if len(config_entries) > 1 else 1,
        input_count=len(config_entries),
        prompt_path=prompt_path,
        started_at=datetime.utcnow().isoformat() if len(config_entries) > 1 else None,
    )

    batch_items_final = get_batch_items(final_batch_id)

    if len(config_entries) == 1:
        source_file = Path(config_entries[0]['input_path'])
        try:
            payload = json.loads(source_file.read_text(encoding='utf-8'))
            knowledge_count = len(payload.get('knowledges', [])) if isinstance(payload, dict) else 0
        except Exception:
            knowledge_count = 0

        output_path = output_dir / 'final_consolidado.json'
        shutil.copy2(source_file, output_path)
        shutil.copy2(output_path, FINAL_INDEX_PATH)

        record_batch_file(final_batch_id, str(output_path), file_size_bytes=output_path.stat().st_size)
        record_batch_file(final_batch_id, FINAL_INDEX_PATH, file_size_bytes=os.path.getsize(FINAL_INDEX_PATH))
        for item in batch_items_final:
            update_batch_item_output(
                item['id'],
                output_path=str(output_path),
                status_id=3,
            )
        finished_at = datetime.utcnow().isoformat()
        update_batch_status(
            final_batch_id,
            status_id=3,
            output_count=knowledge_count,
            finished_at=finished_at,
            prompt_path=prompt_path,
        )
        set_batch_consumed(parent_batch_ids, finished_at)
        logger.info('Indice final gerado a partir de unico arquivo consolidado da fase 2.')
        return

    input_paths = [entry['input_path'] for entry in config_entries]
    upload_display_names = _predict_upload_names(
        input_paths,
        base_dir=str(lote_dir),
        prefix='final',
        prefer_original=True,
        consolidate=False,
    )
    files_prompt = _build_files_prompt_segment(input_paths, str(lote_dir), upload_display_names)
    prompt = BATCH_DEDUP_PROMPT + files_prompt
    prompt_path = _write_batch_prompt(prompt)
    update_batch_status(
        final_batch_id,
        status_id=2,
        prompt_path=prompt_path,
    )

    gemini_generator = GeminiGenerator()
    claude_generator = ClaudeOpusGenerator()
    gpt_generator = GPTGenerator()

    try:
        response_text = await _call_with_retries(
            generator=gemini_generator,
            prompt=prompt,
            source_paths=input_paths,
            base_dir=str(lote_dir),
            prefix='final',
            prefer_original_when_single=True,
            consolidate=False,
            generator_cycle=[gemini_generator, claude_generator, gpt_generator],
            upload_delay=UPLOAD_DELAY_SECONDS,
        )
        cleaned_text = remove_think_tags(response_text)
        sanitized = _sanitize_patch_text(cleaned_text) or cleaned_text
        candidate = _extract_json_candidate(sanitized) or sanitized
        candidate = _strip_code_fences(candidate) or candidate
        payload = json.loads(candidate)
        knowledges = payload.get('knowledges') if isinstance(payload, dict) else None
        if not isinstance(knowledges, list):
            raise ValueError("Resposta final nao contem 'knowledges' valido.")

        output_path = output_dir / 'final_consolidado.json'
        with output_path.open('w', encoding='utf-8') as outfile:
            json.dump(payload, outfile, ensure_ascii=False, indent=2)

        shutil.copy2(output_path, FINAL_INDEX_PATH)
        record_batch_file(final_batch_id, str(output_path), file_size_bytes=output_path.stat().st_size)
        record_batch_file(final_batch_id, FINAL_INDEX_PATH, file_size_bytes=os.path.getsize(FINAL_INDEX_PATH))

        for item in batch_items_final:
            update_batch_item_output(
                item['id'],
                output_path=str(output_path),
                status_id=3,
            )

        finished_at = datetime.utcnow().isoformat()
        update_batch_status(
            final_batch_id,
            status_id=3,
            output_count=len(knowledges),
            finished_at=finished_at,
            prompt_path=prompt_path,
        )
        set_batch_consumed(parent_batch_ids, finished_at)
        record_batch_metrics(final_batch_id, [
            ('input_files', len(input_paths)),
            ('output_knowledges', len(knowledges)),
            ('prompt_length', len(prompt)),
        ])
        logger.info('Indice final consolidado com sucesso.')
    except Exception as exc:
        finished_at = datetime.utcnow().isoformat()
        logger.error(f"Erro ao consolidar indice final: {exc}")
        update_batch_status(
            final_batch_id,
            status_id=4,
            error_message=str(exc),
            finished_at=finished_at,
            prompt_path=prompt_path,
        )
        set_batch_consumed(parent_batch_ids, None)
        for item in batch_items_final:
            update_batch_item_output(
                item['id'],
                status_id=1,
                notes='Consolidacao final falhou; item retorna a pendente.',
            )

async def main():
    parser = argparse.ArgumentParser(description='Pipeline de extracao e geracao de conhecimento.')
    parser.add_argument('--input', type=str, help='Caminho para uma pasta com arquivos .txt para processar.')
    args = parser.parse_args()

    initialize_database()

    if args.input:
        process_input_folder(args.input)
        await run_stage1_index_creation()
        await process_pending_knowledges()
        await run_stage3_cleanup()
        await run_stage4_batch_preparation()
        await run_stage5_batch_execution()
        await run_stage6_phase2_preparation()
        await run_stage7_phase2_execution()
        await run_stage8_finalize_index()
    else:
        await process_pending_knowledges()
        await run_stage3_cleanup()
        await run_stage4_batch_preparation()
        await run_stage5_batch_execution()
        await run_stage6_phase2_preparation()
        await run_stage7_phase2_execution()
        await run_stage8_finalize_index()

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

