import argparse
import asyncio
import json
import os
import re
from typing import Dict, List, Optional

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
from generators.adapta.claude_opus_generator import ClaudeOpusGenerator  # noqa: F401 - kept for future use
from generators.adapta.gemini_generator import GeminiGenerator
from prompt_manager import generate_knowledge_extraction_prompt
from utils.text_cleaner import remove_think_tags

INDEXES_PATH = 'indexes'
DOCS_PREFIX = 'docs_'
KNOWLEDGE_PROMPT_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_creation.txt')

os.makedirs(INDEXES_PATH, exist_ok=True)


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


def section_key(section_id, section_title):
    return section_id, section_title or ''


def _normalize_files_list(files: Optional[List], current_file_name: Optional[str]) -> List[Dict[str, str]]:
    file_names: List[str] = []
    if files:
        for entry in files:
            if isinstance(entry, dict):
                name = entry.get('name')
            else:
                name = entry
            if name:
                file_names.append(str(name).strip())
    if current_file_name:
        file_names.append(current_file_name)

    normalized: List[Dict[str, str]] = []
    seen = set()
    for name in file_names:
        clean = name.strip()
        if clean and clean not in seen:
            seen.add(clean)
            normalized.append({'name': clean})
    return normalized


def _merge_files(existing_files: Optional[List], new_files: Optional[List]) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = []
    seen = set()
    for source in (existing_files or []) + (new_files or []):
        if isinstance(source, dict):
            name = source.get('name')
        else:
            name = source
        if not name:
            continue
        clean = str(name).strip()
        if clean not in seen:
            seen.add(clean)
            merged.append({'name': clean})
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


def _build_existing_maps(existing_index: Optional[Dict]):
    files_map: Dict[int, List[Dict[str, str]]] = {}
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
            current_files = _normalize_files_list(entry.get('files'), current_file_name)
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
    print(f"Escaneando a pasta de entrada: {folder_path}")
    if not os.path.isdir(folder_path):
        print(f"Erro: O caminho '{folder_path}' nao e um diretorio valido.")
        return

    for filename in os.listdir(folder_path):
        if filename.endswith('.txt'):
            file_path = os.path.abspath(os.path.join(folder_path, filename))
            create_job(file_path, filename, folder_path)


async def run_stage1_index_creation():
    print('Iniciando Estagio 1: Criacao de Indice de Conhecimento.')
    pending_jobs = get_pending_jobs_by_stage(stage_id=1)

    if not pending_jobs:
        print('Nenhum job pendente para o Estagio 1.')
        return

    generator = GeminiGenerator()

    for job in pending_jobs:
        job_id = job['id']
        folder_path = job['folder_path']
        current_file_name = job['file_name']
        index_path = get_index_file_path(folder_path)
        index_data = load_index_data(index_path)
        existing_index_content = json.dumps(index_data, ensure_ascii=False, indent=4) if index_data.get('sections') else None

        print(f"Processando job {job_id} para o arquivo: {current_file_name}")

        try:
            update_job_state(job_id, stage_id=1, status_id=2)
            with open(job['file_path'], 'r', encoding='utf-8') as f:
                file_content = f.read()

            prompt = generate_knowledge_extraction_prompt(file_content, folder_path, current_file_name, existing_index_content)
            messages = [{'role': 'user', 'content': prompt}]
            json_output_str = await generator.call_model_with_messages(messages)
            json_output_str = remove_think_tags(json_output_str)
            match = re.search(r"```json\s*(.*?)\s*```", json_output_str, re.DOTALL)
            if match:
                json_output_str = match.group(1).strip()

            data = json.loads(json_output_str)
            knowledges = _flatten_sections(data, current_file_name, existing_index=index_data)
            _update_index_with_entries(index_data, knowledges)
            save_index_data(index_path, index_data)

            if knowledges:
                add_knowledges_from_json(job_id, knowledges)
                print(f"{len(knowledges)} conhecimentos inseridos no banco de dados para o job {job_id}.")

            update_job_state(job_id, stage_id=2, status_id=3)
            print(f"Job {job_id} concluido com sucesso.")
        except Exception as e:
            print(f"Erro ao processar o job {job_id}: {e}")
            update_job_state(job_id, stage_id=1, status_id=4)


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
    print('\nIniciando Estagio 2: Criacao de Arquivos de Conhecimento.')
    pending_knowledges = get_pending_knowledges()

    if not pending_knowledges:
        print('Nenhum conhecimento pendente para processar.')
        return

    generator = GeminiGenerator()
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

        print(f"Processando conhecimento ID: {knowledge_id} - {knowledge['knowledge_name']}")

        try:
            update_knowledge_status(knowledge_id, status_id=2)

            file_blocks: List[str] = []
            if source_files:
                for file_name in source_files:
                    file_path = os.path.join(folder_path, file_name)
                    if os.path.isfile(file_path):
                        with open(file_path, 'r', encoding='utf-8') as f:
                            file_blocks.append(f"# Arquivo: {file_name}\n{f.read()}")
                    else:
                        print(f"Aviso: Arquivo {file_name} nao encontrado em {folder_path}.")

            if not file_blocks:
                with open(knowledge['job_file_path'], 'r', encoding='utf-8') as f:
                    default_file = os.path.basename(knowledge['job_file_path'])
                    file_blocks.append(f"# Arquivo: {default_file}\n{f.read()}")

            combined_content = '\n\n'.join(file_blocks)

            prompt = prompt_template.replace('{knowledge_category}', knowledge['knowledge_category'])
            prompt = prompt.replace('{knowledge_name}', knowledge['knowledge_name'])
            prompt = prompt.replace('{file_content}', combined_content)

            if related_names:
                related_block = '\n'.join(f"- {name}" for name in related_names)
                prompt += '\n\n# CONHECIMENTOS RELACIONADOS\n' + related_block

            messages = [{'role': 'user', 'content': prompt}]
            markdown_output = await generator.call_model_with_messages(messages)
            markdown_output = remove_think_tags(markdown_output)

            knowledge_slug = slugify(knowledge['knowledge_name'])
            output_dir = get_docs_output_dir(folder_path)
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"{knowledge_slug}.md")

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_output)
            print(f"Arquivo Markdown salvo em: {output_path}")

            update_knowledge_status(knowledge_id, status_id=3)
            print(f"Conhecimento {knowledge_id} concluido com sucesso.")

        except Exception as e:
            print(f"Erro ao processar o conhecimento {knowledge_id}: {e}")
            update_knowledge_status(knowledge_id, status_id=4)


async def run_stage3_cleanup():
    print('\nIniciando Estagio 3: Limpeza e Finalizacao de Jobs.')
    completed_stage2_jobs = get_completed_jobs_by_stage(stage_id=2)

    if not completed_stage2_jobs:
        print('Nenhum job para finalizar.')
        return

    for job in completed_stage2_jobs:
        job_id = job['id']
        if are_all_knowledges_completed_for_job(job_id):
            print(f"Todos os conhecimentos para o job {job_id} estao concluidos. Finalizando...")
            update_job_state(job_id, stage_id=3, status_id=3)
            print(f"Job {job_id} finalizado com sucesso.")


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
