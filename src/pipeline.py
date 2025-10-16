import argparse
import asyncio
import copy
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from database import (
    add_knowledges_from_json,
    are_all_knowledges_completed_for_job,
    create_job,
    get_completed_jobs_by_stage,
    get_pending_jobs_by_stage,
    get_pending_knowledges,
    initialize_database,
    update_job_state,
    update_knowledge_status,
)
from generators.adapta.claude_opus_generator import ClaudeOpusGenerator
from generators.adapta.gemini_generator import GeminiGenerator
from utils.logger import logger
from prompt_manager import generate_knowledge_extraction_prompt
from utils.text_cleaner import remove_think_tags

INDEXES_PATH = 'indexes'
DOCS_PREFIX = 'docs_'
KNOWLEDGE_PROMPT_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_creation.txt')
MAX_WORDS_PER_UPLOAD = 400000
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2.0
MAX_JSON_PARSE_RETRIES = 10
JSON_PARSE_RETRY_DELAY = 1.0

os.makedirs(INDEXES_PATH, exist_ok=True)


os.makedirs(INDEXES_PATH, exist_ok=True)

os.makedirs(INDEXES_PATH, exist_ok=True)

CHAT_LOG_PATH = Path(INDEXES_PATH) / 'chat.md'
MAX_PATCH_RETRIES = 6
VALIDATOR_PROMPT_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_extraction_continuation_validator.txt')

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[\s_]+", '-', text)
    text = re.sub(r"[^a-z0-9-]", '', text)
    return text.strip('-')


def get_index_file_path(folder_path: str) -> str:
    folder_name = os.path.basename(os.path.normpath(folder_path)) or 'indice'
    slug = slugify(folder_name) or 'indice'
    return os.path.join(INDEXES_PATH, f"{slug}.json")


def get_docs_output_dir(folder_path: str) -> str:
    folder_name = os.path.basename(os.path.normpath(folder_path)) or 'conteudo'
    folder_slug = slugify(folder_name) or 'conteudo'
    return f"{DOCS_PREFIX}{folder_slug}"


def load_index_data(index_path: str) -> Dict:
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'sections': []}


def save_index_data(index_path: str, index_data: Dict) -> None:
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=4)


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


def _create_consolidated_temp_file(file_paths: List[str], base_dir: Optional[str], prefix: str) -> Path:
    consolidated_text = _build_consolidated_text(file_paths, base_dir)
    if not consolidated_text.strip():
        raise ValueError("Nenhum conteudo valido encontrado para consolidar.")

    temp_dir = Path(tempfile.gettempdir())
    temp_path = temp_dir / f"{prefix}_{uuid.uuid4().hex}.txt"
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
        temp_path = temp_dir / f"{prefix}_{source_path.stem}_{uuid.uuid4().hex}.txt"
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

    temp_path = _create_consolidated_temp_file(file_paths, base_dir, prefix)
    return temp_path, True




    if consolidate or len(file_paths) == 1:
        upload_path, cleanup = _prepare_upload_file(
            file_paths=file_paths,
            base_dir=base_dir,
            prefix=prefix,
            prefer_original=prefer_original,
        )
        return [(upload_path, cleanup)]

    uploads: List[Tuple[Path, bool]] = []
    for source in file_paths:
        source_path = Path(source)
        if source_path.suffix.lower() != '.txt':
            temp_dir = Path(tempfile.gettempdir())
            temp_path = temp_dir / f"{prefix}_{uuid.uuid4().hex}.txt"
            try:
                temp_content = source_path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                temp_content = source_path.read_bytes().decode('utf-8', errors='ignore')
            temp_path.write_text(temp_content, encoding='utf-8')
            uploads.append((temp_path, True))
        else:
            uploads.append((source_path, False))
    return uploads


async def _call_generator_with_uploads(
    generator,
    prompt: Optional[str],
    uploads: List[Tuple[Path, bool]],
    messages: Optional[List[Dict[str, str]]] = None,
    tool: Optional[str] = None,
) -> str:
    upload_infos: List[Tuple[Dict[str, Any], bool, Path]] = []
    try:
        for upload_path, cleanup in uploads:
            upload_info = await generator.client.upload_arquivo(str(upload_path))
            if not upload_info:
                raise RuntimeError(f"Falha ao fazer upload do arquivo: {upload_path}")
            upload_infos.append((upload_info, cleanup, upload_path))

        if messages is None:
            if prompt is None:
                raise ValueError("Prompt ou mensagens devem ser fornecidos para chamada ao gerador.")
            payload_messages = [{'role': 'user', 'content': prompt}]
        else:
            payload_messages = messages

        response = await generator.call_model_with_messages(
            [dict(message) for message in payload_messages],
            file_ids=[info for info, _, _ in upload_infos],
            tool=tool,
        )
    finally:
        for upload_info, cleanup, upload_path in upload_infos:
            file_id = upload_info.get("id") if upload_info else None
            if file_id:
                try:
                    await generator.client.excluir_arquivo(file_id)
                except Exception:
                    pass
            if cleanup:
                try:
                    upload_path.unlink()
                except FileNotFoundError:
                    pass

    return response


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
    fallback_generator: Optional[Any] = None,
    fallback_attempt: Optional[int] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    tool: Optional[str] = None,
) -> str:
    if not source_paths:
        raise ValueError("Nenhum arquivo fonte informado para upload.")
    if prompt is None and messages is None:
        raise ValueError("Prompt ou mensagens devem ser fornecidos para a chamada ao gerador.")

    delay = initial_delay
    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        uploads: Optional[List[Tuple[Path, bool]]] = None
        current_generator = generator
        if (
            fallback_generator is not None
            and fallback_attempt is not None
            and attempt >= fallback_attempt
        ):
            current_generator = fallback_generator
            if attempt == fallback_attempt:
                logger.info("Usando gerador Gemini como fallback na tentativa final.")
        try:
            uploads = _prepare_upload_specs(
                file_paths=source_paths,
                base_dir=base_dir,
                prefix=prefix,
                prefer_original=prefer_original_when_single,
                consolidate=consolidate,
            )
            return await _call_generator_with_uploads(
                current_generator,
                prompt,
                uploads,
                messages=messages,
                tool=tool,
            )
        except Exception as exc:
            last_error = exc
            if uploads:
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


def _normalize_files_list(files: Optional[List], current_file_name: Optional[str]) -> List[str]:
    file_names: List[str] = []
    if files:
        for entry in files:
            name = _coerce_file_name(entry)
            if not name:
                continue
            file_names.append(name)
    if current_file_name:
        file_names.append(current_file_name)

    normalized: List[str] = []
    seen = set()
    for name in file_names:
        clean = name.strip()
        if clean and clean not in seen:
            seen.add(clean)
            normalized.append(clean)
    return normalized


def _merge_files(existing_files: Optional[List], new_files: Optional[List]) -> List[str]:
    merged: List[str] = []
    seen = set()
    for source in (existing_files or []) + (new_files or []):
        name = _coerce_file_name(source)
        if not name:
            continue
        clean = name.strip()
        if clean not in seen:
            seen.add(clean)
            merged.append(clean)
    return merged


def _normalize_related_list(related: Optional[List], knowledge_id: int) -> List[int]:
    if not related:
        return []
    normalized: List[int] = []
    seen = set()
    for value in related:
        try:
            related_id = int(value)
        except (TypeError, ValueError):
            continue
        if related_id <= 0 or related_id == knowledge_id or related_id in seen:
            continue
        seen.add(related_id)
        normalized.append(related_id)
    return normalized


def _merge_related(existing_related: Optional[List[int]], new_related: Optional[List[int]], knowledge_id: int) -> List[int]:
    result: List[int] = []
    seen = set()
    for source_list in (existing_related or [], new_related or []):
        for value in source_list:
            try:
                related_id = int(value)
            except (TypeError, ValueError):
                continue
            if related_id <= 0 or related_id == knowledge_id or related_id in seen:
                continue
            seen.add(related_id)
            result.append(related_id)
    return result


def _build_files_prompt_segment(file_paths: List[str], base_dir: Optional[str]) -> str:
    if not file_paths:
        return ""

    names: List[str] = []
    seen = set()
    for path in file_paths:
        if base_dir:
            try:
                name = os.path.relpath(path, base_dir)
            except ValueError:
                name = os.path.basename(path)
        else:
            name = os.path.basename(path)
        name = name.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    if not names:
        return ""

    listing = "\n".join(f"- {name}" for name in names)
    return f"\n\n# ARQUIVOS DISPONIVEIS\n{listing}"


def _build_existing_maps(existing_index: Optional[Dict]):
    files_map: Dict[int, List[str]] = {}
    related_map: Dict[int, List[int]] = {}
    if not existing_index:
        return files_map, related_map
    for section in existing_index.get('sections', []):
        for knowledge in section.get('knowledges', []) or []:
            knowledge_id = knowledge.get('id')
            if isinstance(knowledge_id, int):
                files_map[knowledge_id] = _normalize_files_list(knowledge.get('files'), None)
                related_map[knowledge_id] = _normalize_related_list(knowledge.get('knowledge_related'), knowledge_id)
    return files_map, related_map


def _diagnose_patch_failure(index_data: Dict, operations: List[Dict[str, Any]]) -> Tuple[int, Optional[Dict[str, Any]], Optional[Exception]]:
    snapshot = copy.deepcopy(index_data)
    for idx, operation in enumerate(operations, start=1):
        try:
            snapshot = _apply_json_patch(snapshot, [operation])
        except Exception as exc:
            return idx, operation, exc
    return len(operations), None, None





def _strip_code_fences(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    stripped = text.strip()
    if stripped.startswith('```') and stripped.endswith('```'):
        stripped = stripped[3:-3]
    elif stripped.startswith('```json') and stripped.endswith('```'):
        stripped = stripped[7:-3]
    return stripped.strip() if stripped else stripped

def _build_validator_prompt(model_output: str) -> str:
    with open(VALIDATOR_PROMPT_PATH, 'r', encoding='utf-8') as f:
        template = f.read()
    return template.replace('{model_output}', model_output.strip())


async def _run_patch_validator(generator, job_file_path: str, folder_path: str, model_output: str) -> str:
    prompt = _build_validator_prompt(model_output)
    response = await _call_with_retries(
        generator=generator,
        prompt=prompt,
        source_paths=[job_file_path],
        base_dir=folder_path,
        prefix='stage1-validator',
        prefer_original_when_single=True,
    )
    return remove_think_tags(response).strip()


async def _ensure_valid_json_patch(candidate: Optional[str], raw_output: str, generator, job_file_path: str, folder_path: str) -> Tuple[Dict, str]:
    attempts = 0
    current_candidate = candidate
    validator_input = raw_output
    stripped_raw = _strip_code_fences(raw_output)
    if current_candidate is None and stripped_raw:
        current_candidate = stripped_raw

    while True:
        if current_candidate is not None:
            normalized = _strip_code_fences(current_candidate) or current_candidate
            try:
                data = json.loads(normalized)
                return data, normalized
            except json.JSONDecodeError as exc:
                logger.warning(f'JSON invalido detectado ({exc}). Enviando ao validador (tentativa {attempts + 1}/{MAX_JSON_PARSE_RETRIES}).')
                validator_input = normalized
        else:
            logger.warning(f'JSON nao detectado. Enviando ao validador (tentativa {attempts + 1}/{MAX_JSON_PARSE_RETRIES}).')
            validator_input = stripped_raw or raw_output
        attempts += 1
        if attempts > MAX_JSON_PARSE_RETRIES:
            raise ValueError('Nao foi possivel obter JSON valido apos validacao.')
        #validator_response = await _run_patch_validator(generator, job_file_path, folder_path, validator_input)
        #validator_response = validator_response.strip()
        current_candidate = _extract_json_candidate(validator_input) or validator_input


def _split_json_pointer(path: str) -> List[str]:
    if not path:
        return []
    if path == '/':
        return []
    if not path.startswith('/'):
        raise ValueError(f"Caminho JSON Pointer invalido: {path}")
    parts = path.split('/')[1:]
    tokens: List[str] = []
    for part in parts:
        token = part.replace('~1', '/').replace('~0', '~')
        tokens.append(token)
    return tokens


def _coerce_list_index(token: str, sequence: List[Any], allow_end: bool) -> int:
    if token == '-' and allow_end:
        return len(sequence)
    try:
        index = int(token)
    except ValueError as exc:
        raise ValueError(f"Indice de lista invalido: {token}") from exc
    if index < 0:
        raise IndexError(f"Indice fora do intervalo: {token}")

    if index < len(sequence):
        return index

    if allow_end and index == len(sequence):
        return index

    # Fallback: tratar token como identificador do objeto (e.g., knowledge id ou section_id)
    for idx, item in enumerate(sequence):
        if isinstance(item, dict):
            if item.get('id') == index or item.get('section_id') == index:
                return idx
    raise IndexError(f"Indice fora do intervalo: {token}")


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
            raise TypeError("Estrutura JSON inesperada ao resolver JSON Pointer.")
    return parent, tokens[-1]


def _apply_json_patch(document: Dict, operations: List[Dict[str, Any]]) -> Dict:
    patched = copy.deepcopy(document)
    for op in operations:
        if not isinstance(op, dict):
            raise ValueError("Operacao JSON Patch invalida: esperado objeto.")
        operator = op.get('op')
        path = op.get('path', '')
        tokens = _split_json_pointer(path)

        if operator == 'add':
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
        elif operator == 'replace':
            value = op.get('value')
            if not tokens:
                patched = value
                continue
            parent, key = _resolve_parent_and_key(patched, tokens)
            if isinstance(parent, list):
                index = _coerce_list_index(key, parent, allow_end=False)
                parent[index] = value
            elif isinstance(parent, dict):
                if key not in parent:
                    raise KeyError(f"Caminho inexistente para replace: {path}")
                parent[key] = value
            else:
                raise TypeError("Operacao replace aplicada a tipo nao suportado.")
        elif operator == 'remove':
            if not tokens:
                raise ValueError("Nao e permitido remover o documento inteiro.")
            parent, key = _resolve_parent_and_key(patched, tokens)
            if isinstance(parent, list):
                index = _coerce_list_index(key, parent, allow_end=False)
                del parent[index]
            elif isinstance(parent, dict):
                if key not in parent:
                    raise KeyError(f"Caminho inexistente para remove: {path}")
                del parent[key]
            else:
                raise TypeError("Operacao remove aplicada a tipo nao suportado.")
        else:
            raise ValueError(f"Operacao JSON Patch nao suportada: {operator}")
    return patched


def _extract_patch_operations(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        operations = payload
    elif isinstance(payload, dict):
        if 'patch' in payload:
            operations = payload['patch']
        elif 'operations' in payload:
            operations = payload['operations']
        else:
            raise ValueError("Estrutura JSON invalida: campo 'patch' nao encontrado.")
    else:
        raise ValueError("Resposta inesperada: esperado objeto JSON Patch ou lista de operacoes.")

    if not isinstance(operations, list):
        raise ValueError("Campo 'patch' deve ser uma lista de operacoes.")
    return operations


def _build_knowledge_lookup(index_data: Dict) -> Dict[int, Tuple[int, str, Dict[str, Any]]]:
    lookup: Dict[int, Tuple[int, str, Dict[str, Any]]] = {}
    sections = index_data.get('sections') or []
    for idx, section in enumerate(sections, start=1):
        section_id = section.get('section_id', idx)
        title = section.get('title') or f'section {section_id}'
        for knowledge in section.get('knowledges', []) or []:
            knowledge_id = knowledge.get('id')
            if isinstance(knowledge_id, int):
                lookup[knowledge_id] = (section_id, title, knowledge)
    return lookup


def _build_entries_from_lookup(knowledge_ids: List[int], lookup: Dict[int, Tuple[int, str, Dict[str, Any]]], current_file_name: str) -> List[Dict]:
    entries: List[Dict] = []
    for knowledge_id in knowledge_ids:
        if knowledge_id not in lookup:
            continue
        section_id, section_title, knowledge = lookup[knowledge_id]
        entry = {
            'id': knowledge_id,
            'category': knowledge.get('category', ''),
            'name': knowledge.get('name', ''),
            'description': knowledge.get('description', ''),
            'files': _normalize_files_list(knowledge.get('files'), current_file_name),
            'knowledge_related': _normalize_related_list(knowledge.get('knowledge_related'), knowledge_id),
            'section_id': section_id,
            'section_title': section_title,
        }
        entries.append(entry)
    return entries


def _flatten_sections(payload: Dict, current_file_name: str, existing_index: Optional[Dict] = None) -> List[Dict]:
    sections = payload.get('sections')
    if sections is None:
        legacy_knowledges = payload.get('knowledges', [])
        sections = [{
            'section_id': None,
            'title': None,
            'knowledges': legacy_knowledges,
        }] if legacy_knowledges else []

    files_map, related_map = _build_existing_maps(existing_index)

    existing_ids = set(files_map.keys()) | set(related_map.keys())
    max_existing_id = max(existing_ids) if existing_ids else 0
    flattened: List[Dict] = []

    for idx, section in enumerate(sections, start=1):
        section_id = section.get('section_id')
        section_title = section.get('title')

        if section_id is None:
            section_id = idx
        if not section_title:
            section_title = f'section {section_id}'

        for knowledge in section.get('knowledges', []) or []:
            entry = dict(knowledge)
            knowledge_id = entry.get('id')

            if knowledge_id is None or not isinstance(knowledge_id, int):
                max_existing_id += 1
                knowledge_id = max_existing_id

            entry['id'] = knowledge_id
            entry['description'] = entry.get('description') or ''
            entry['category'] = entry.get('category') or ''
            entry['name'] = entry.get('name') or ''
            entry['section_id'] = section_id
            entry['section_title'] = section_title

            previous_files = files_map.get(knowledge_id, [])
            current_files = _normalize_files_list(None, current_file_name)
            entry['files'] = _merge_files(previous_files, current_files)

            previous_related = related_map.get(knowledge_id, [])
            current_related = _normalize_related_list(entry.get('knowledge_related'), knowledge_id)
            entry['knowledge_related'] = _merge_related(previous_related, current_related, knowledge_id)

            flattened.append(entry)

    return flattened


def _update_index_with_entries(index_data: Dict, entries: List[Dict]) -> Dict:
    sections = index_data.setdefault('sections', [])

    section_map: Dict = {}
    knowledge_maps: Dict = {}

    for section in sections:
        key = section_key(section.get('section_id'), section.get('title'))
        section_map[key] = section
        knowledge_map = {}
        for knowledge in section.get('knowledges', []) or []:
            kid = knowledge.get('id')
            if kid is not None:
                knowledge_map[kid] = knowledge
            knowledge['description'] = knowledge.get('description') or ''
            knowledge['files'] = _normalize_files_list(knowledge.get('files'), None)
            knowledge['knowledge_related'] = _normalize_related_list(knowledge.get('knowledge_related'), kid if isinstance(kid, int) else -1)
        knowledge_maps[key] = knowledge_map

    for entry in entries:
        key = section_key(entry.get('section_id'), entry.get('section_title'))
        if key not in section_map:
            section = {
                'section_id': entry.get('section_id'),
                'title': entry.get('section_title'),
                'knowledges': []
            }
            sections.append(section)
            section_map[key] = section
            knowledge_maps[key] = {}

        section = section_map[key]
        knowledge_map = knowledge_maps[key]
        knowledge_id = entry.get('id')

        if knowledge_id in knowledge_map:
            existing = knowledge_map[knowledge_id]
            existing['category'] = entry.get('category', existing.get('category'))
            existing['name'] = entry.get('name', existing.get('name'))
            existing['description'] = entry.get('description', existing.get('description', ''))
            existing['files'] = _merge_files(existing.get('files'), entry.get('files'))
            existing['knowledge_related'] = _merge_related(existing.get('knowledge_related'), entry.get('knowledge_related'), knowledge_id)
        else:
            new_knowledge = {
                'id': knowledge_id,
                'category': entry.get('category', ''),
                'name': entry.get('name', ''),
                'description': entry.get('description', ''),
                'files': _normalize_files_list(entry.get('files'), None),
                'knowledge_related': _normalize_related_list(entry.get('knowledge_related'), knowledge_id),
            }
            section.setdefault('knowledges', []).append(new_knowledge)
            knowledge_map[knowledge_id] = new_knowledge

    sections.sort(key=lambda s: (s.get('section_id') is None, s.get('section_id')))
    for section in sections:
        section_id = section.get('section_id')
        if section_id is None:
            section_id = 0
        section['title'] = section.get('title') or f'section {section_id}'
        section['knowledges'] = sorted(section.get('knowledges', []), key=lambda k: (k.get('id') is None, k.get('id')))

    return index_data


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
    gemini_generator = GeminiGenerator()

    for job in pending_jobs:
        job_id = job['id']
        folder_path = job['folder_path']
        current_file_name = job['file_name']
        index_path = get_index_file_path(folder_path)
        index_data = load_index_data(index_path)
        has_existing_index = bool(index_data.get('sections'))
        index_file_for_prompt = index_path if has_existing_index else None
        index_before = copy.deepcopy(index_data) if has_existing_index else None

        logger.info(f"Processando job {job_id} para o arquivo: {current_file_name}")

        try:
            prompt = generate_knowledge_extraction_prompt(current_file_name, index_file_for_prompt)
            source_files = [job['file_path']]
            if has_existing_index:
                source_files.append(index_path)
            source_prompt = _build_files_prompt_segment(source_files, folder_path)
            if source_prompt:
                prompt += source_prompt
            temp_raw_path = Path(INDEXES_PATH) / 'temp.json'
            patch_debug_paths: List[Path] = []
            conversation: List[Dict[str, str]] = [{'role': 'user', 'content': prompt}]
            _write_conversation_log(conversation)
            accumulated_raw = ""
            accumulated_clean_chunks: List[str] = []
            patch_retry_attempts = 0

            knowledges: List[Dict] = []

            while True:
                raw_response = await _call_with_retries(
                    generator=gemini_generator,
                    prompt=None,
                    source_paths=source_files,
                    base_dir=folder_path,
                    prefix='stage1',
                    prefer_original_when_single=True,
                    consolidate=False,
                    fallback_generator=gemini_generator,
                    fallback_attempt=3,
                    messages=conversation,
                    tool="",
                )

                accumulated_raw += raw_response
                temp_raw_path.write_text(accumulated_raw, encoding='utf-8')

                cleaned_chunk = remove_think_tags(raw_response)
                accumulated_clean_chunks.append(cleaned_chunk)
                conversation.append({'role': 'assistant', 'content': cleaned_chunk})
                _write_conversation_log(conversation)


                combined_clean = ''.join(accumulated_clean_chunks)
                candidate = _extract_json_candidate(combined_clean)
                data, candidate_text = await _ensure_valid_json_patch(
                    candidate=candidate,
                    raw_output=combined_clean,
                    generator=gemini_generator,
                    job_file_path=job['file_path'],
                    folder_path=folder_path,
                )

                if has_existing_index:
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
                        patched_index = _apply_json_patch(index_data, operations)
                    except Exception as patch_exc:
                        if patch_debug_path:
                            logger.error(f"Erro ao aplicar JSON Patch. Arquivo de depuracao: {patch_debug_path}")
                        failure_idx, failing_op, inner_exc = _diagnose_patch_failure(index_data, operations)
                        patch_retry_attempts += 1
                        if patch_retry_attempts >= MAX_PATCH_RETRIES:
                            logger.error(
                                "Falha definitiva ao aplicar JSON Patch apos %d tentativas. "
                                "Operacao #%d: %s. Erro reportado: %s",
                                patch_retry_attempts,
                                failure_idx,
                                json.dumps(failing_op, ensure_ascii=False) if failing_op else "<desconhecida>",
                                inner_exc or patch_exc,
                            )
                            raise
                        detail_lines = [
                            "Aplicacao do JSON Patch falhou.",
                            f"- Tentativa: {patch_retry_attempts}/{MAX_PATCH_RETRIES}",
                        ]
                        if failing_op:
                            detail_lines.append(f"- Operacao #{failure_idx}: {json.dumps(failing_op, ensure_ascii=False)}")
                        detail_lines.append(f"- Erro reportado: {inner_exc or patch_exc}")
                        detail_lines.append("Corrija os caminhos apontando para indices existentes (use contagem iniciando em 0 ou '-' para anexar) e reenviar TODO o patch completo.")
                        feedback_message = "\n".join(detail_lines)
                        conversation.append({'role': 'user', 'content': feedback_message})
                        _write_conversation_log(conversation)
                        accumulated_raw = ""
                        accumulated_clean_chunks = []
                        try:
                            temp_raw_path.write_text("", encoding='utf-8')
                        except Exception as cleanup_exc:
                            logger.warning(f"Falha ao limpar arquivo temporario {temp_raw_path}: {cleanup_exc}")
                        logger.warning(f"Requisitando nova versao do JSON Patch apos falha (tentativa {patch_retry_attempts + 1}/{MAX_PATCH_RETRIES}).")
                        continue
                    index_data = patched_index
                    if not isinstance(index_data, dict):
                        raise ValueError("Resultado das operacoes JSON Patch nao e um objeto JSON.")
                    _update_index_with_entries(index_data, [])
                    lookup_after = _build_knowledge_lookup(index_data)
                    lookup_before = _build_knowledge_lookup(index_before) if index_before else {}
                    new_ids = sorted(kid for kid in lookup_after.keys() if kid not in lookup_before)
                    if new_ids:
                        logger.info(f"{len(new_ids)} novos conhecimentos identificados para o job {job_id}.")
                    knowledges = _build_entries_from_lookup(new_ids, lookup_after, current_file_name)
                    candidate_text = candidate_text
                else:
                    knowledges = _flatten_sections(data, current_file_name, existing_index=index_data)
                    _update_index_with_entries(index_data, knowledges)
                break

            save_index_data(index_path, index_data)

            if knowledges:
                add_knowledges_from_json(job_id, knowledges)
                logger.info(f"{len(knowledges)} conhecimentos inseridos no banco de dados para o job {job_id}.")

            update_job_state(job_id, stage_id=2, status_id=3)
            logger.info(f"Job {job_id} concluido com sucesso.")
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
        except Exception as e:
            last_debug = patch_debug_paths[-1] if patch_debug_paths else None
            logger.exception(
                "Erro ao processar o job %s (arquivo: %s). Ultimo patch salvo: %s",
                job_id,
                current_file_name,
                last_debug or "nenhum",
            )
            update_job_state(job_id, stage_id=1, status_id=1)
            continue


def _extract_file_names(row) -> List[str]:
    raw = row['file_names'] if 'file_names' in row.keys() else None
    if not raw:
        return []
    names = [name.strip() for name in str(raw).split('||') if name and name.strip()]
    result = []
    seen = set()
    for name in names:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _extract_related_ids(row) -> List[int]:
    raw = row['related_ids'] if 'related_ids' in row.keys() else None
    if not raw:
        return []
    result = []
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
        result.append(related_id)
    return result


def _lookup_related_names(index_data: Dict, related_ids: List[int]) -> List[str]:
    if not related_ids:
        return []
    id_to_name: Dict[int, str] = {}
    for section in index_data.get('sections', []):
        for knowledge in section.get('knowledges', []) or []:
            kid = knowledge.get('id')
            if isinstance(kid, int):
                id_to_name[kid] = knowledge.get('name', '')
    names: List[str] = []
    for related_id in related_ids:
        name = id_to_name.get(related_id)
        if name:
            names.append(name)
    return names


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
            source_prompt = _build_files_prompt_segment(consolidated_sources, folder_path)
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
            update_knowledge_status(knowledge_id, status_id=4)


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
    else:
        await process_pending_knowledges()
        await run_stage3_cleanup()


if __name__ == '__main__':
    asyncio.run(main())
