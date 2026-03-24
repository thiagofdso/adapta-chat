import json
import os
from typing import List, Optional

PROMPT_DIR = os.path.join(os.path.dirname(__file__), 'prompts')
PROMPT_FILE_PATH = os.path.join(PROMPT_DIR, 'knowledge_extraction.txt')
CONTINUATION_PROMPT_FILE_PATH = os.path.join(PROMPT_DIR, 'knowledge_extraction_continuation.txt')
DOCLING_PROMPT_FILE_PATH = os.path.join(PROMPT_DIR, 'knowledge_extraction_docling.txt')

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

    listing, bounds_info, rules_block = _build_index_context(existing_index_paths, existing_index_display_names)
    template_path = CONTINUATION_PROMPT_FILE_PATH if existing_index_paths else PROMPT_FILE_PATH

    with open(template_path, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    prompt = (
        prompt_template
        .replace('{current_file}', current_file_name)
        .replace('{current_index_files}', listing, 1)
        .replace('{index_bounds_info}', bounds_info, 1)
    )
    prompt = prompt.replace('# RULES\n', '# RULES\n' + rules_block, 1)
    return prompt


def generate_docling_extraction_prompt(
    current_file_name: str,
    docling_text: str,
    existing_index_paths: Optional[List[str]] = None,
    existing_index_display_names: Optional[List[str]] = None,
) -> str:
    """Gera o prompt de fallback quando o PDF é convertido em texto via Docling."""
    if isinstance(existing_index_paths, str):
        existing_index_paths = [existing_index_paths]

    listing, bounds_info, rules_block = _build_index_context(existing_index_paths, existing_index_display_names)
    with open(DOCLING_PROMPT_FILE_PATH, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    prompt = (
        prompt_template
        .replace('{current_file}', current_file_name)
        .replace('{current_index_files}', listing, 1)
        .replace('{index_bounds_info}', bounds_info, 1)
        .replace('{docling_text}', docling_text.strip(), 1)
        .replace('{dynamic_rules}', rules_block, 1)
    )
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


def _build_index_context(
    existing_index_paths: Optional[List[str]],
    existing_index_display_names: Optional[List[str]],
) -> tuple[str, str, str]:
    if existing_index_paths:
        if existing_index_display_names and len(existing_index_display_names) == len(existing_index_paths):
            index_names = existing_index_display_names
        else:
            index_names = [os.path.basename(path) for path in existing_index_paths]
        listing = '\n'.join(f"- {name}" for name in index_names) or '- nenhum (indice ausente)'
        bounds = _build_index_summary(existing_index_paths)
        rules = CONTINUATION_ADDITIONAL_RULES
    else:
        listing = '- nenhum (primeira execucao)'
        bounds = 'The current index is empty; append new knowledges using "/knowledges/-".'
        rules = BASE_ADDITIONAL_RULES
    rules_block = ''.join(f"* {rule}\n" for rule in rules)
    return listing, bounds, rules_block
