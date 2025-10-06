import os
from services.knowledge_service import get_existing_knowledges_as_json

PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_extraction.txt')

def generate_knowledge_extraction_prompt(file_content, folder_path):
    """
    Gera o prompt de extração de conhecimento, inserindo dinamicamente os conhecimentos existentes.

    Args:
        file_content (str): O conteúdo do arquivo a ser processado.
        folder_path (str): O caminho da pasta onde o arquivo está, para buscar conhecimentos existentes.

    Returns:
        str: O prompt final e completo.
    """
    # Lê o template base do prompt
    with open(PROMPT_FILE_PATH, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    # Busca o JSON de conhecimentos existentes
    existing_knowledges_json = get_existing_knowledges_as_json(folder_path)

    # Se houver conhecimentos existentes, modifica o prompt
    if existing_knowledges_json:
        dynamic_section = (
            "# EXISTING KNOWLEDGES\n"
            f"{existing_knowledges_json}\n\n"
        )

        # Insere a nova regra e a seção de conhecimentos existentes antes das regras gerais
        prompt_template = prompt_template.replace(
            '# RULES',
            f'{dynamic_section}# RULES\n* Não repita os "EXISTING KNOWLEDGES"'
        )

    # Preenche o conteúdo do arquivo no prompt final
    final_prompt = prompt_template.replace('{file_content}', file_content)

    return final_prompt
