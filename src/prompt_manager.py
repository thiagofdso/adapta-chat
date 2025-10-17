import json
import os
from typing import List, Optional

PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_extraction.txt')
CONTINUATION_PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_extraction_continuation.txt')

BASE_ADDITIONAL_RULES = [
    "Cada conhecimento deve conter apenas \"name\", \"description\" e \"files\" (lista de strings).",
    "Limite a lista \"files\" a no maximo 5 itens, incluindo o arquivo atual sem duplicar nomes."
]

CONTINUATION_ADDITIONAL_RULES = BASE_ADDITIONAL_RULES + [
    "Os arquivos de indice estao divididos em partes de no maximo 300 registros; avalie todos antes de propor novas operacoes."
]


def generate_knowledge_extraction_prompt(
    current_file_name: str,
    existing_index_paths: Optional[List[str]] = None,
    existing_index_display_names: Optional[List[str]] = None
):
    """Gera o prompt de extracao de conhecimento, adicionando indice atual e regras dinamicas."""
    if isinstance(existing_index_paths, str):
        existing_index_paths = [existing_index_paths]

    template_path = CONTINUATION_PROMPT_FILE_PATH if existing_index_paths else PROMPT_FILE_PATH

    with open(template_path, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    prompt = prompt_template.replace('{current_file}', current_file_name)

    if existing_index_paths:
        if existing_index_display_names and len(existing_index_display_names) == len(existing_index_paths):
            index_names = existing_index_display_names
        else:
            index_names = [os.path.basename(path) for path in existing_index_paths]
        listing = '\n'.join(f"- {name}" for name in index_names) or '- nenhum (indice ausente)'
        prompt = prompt.replace('{current_index_files}', listing)
        prompt = prompt.replace('{index_bounds_info}', _build_index_summary(existing_index_paths))
        rules_block = ''.join(f"* {rule}\n" for rule in CONTINUATION_ADDITIONAL_RULES)
    else:
        prompt = prompt.replace('{current_index_files}', '- nenhum (primeira execucao)')
        prompt = prompt.replace('{index_bounds_info}', 'The current index is empty; append new knowledges using "/knowledges/-".')
        rules_block = ''.join(f"* {rule}\n" for rule in BASE_ADDITIONAL_RULES)

    prompt = prompt.replace('# RULES\n', '# RULES\n' + rules_block, 1)

    return prompt


def _build_index_summary(index_paths: List[str]) -> str:
    knowledges: List[dict] = []

    for index_path in index_paths:
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue

        if isinstance(data, dict):
            if isinstance(data.get('knowledges'), list):
                knowledges.extend(data['knowledges'])
            elif isinstance(data.get('sections'), list):
                for section in data['sections']:
                    if isinstance(section, dict):
                        knowledges.extend(section.get('knowledges') or [])

    count = len(knowledges)
    if count == 0:
        return 'The current index is empty; append new knowledges using "/knowledges/-".'
    upper = count - 1
    return f'The current index contains {count} knowledges with valid zero-based indices from 0 to {upper}. Use these bounds when choosing JSON Patch paths.'
