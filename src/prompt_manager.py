import os

PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_extraction.txt')

ADDITIONAL_RULES = [
    "Continue o indice existente adicionando apenas os elementos novos identificados no documento atual.",
    "Voce pode criar novas secoes e adicionar novos conhecimentos as secoes existentes sempre que necessario.",
    "Adicione o arquivo atual a lista \"files\" de cada conhecimento pertinente, mantendo tambem os arquivos ja registrados anteriormente.",
    "Quando identificar relacoes entre conhecimentos, preencha \"knowledge_related\" com os IDs correspondentes e mantenha valores existentes."
]


def generate_knowledge_extraction_prompt(current_file_name, existing_index_content=None):
    """Gera o prompt de extracao de conhecimento, adicionando indice atual e regras dinamicas."""
    with open(PROMPT_FILE_PATH, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    prompt = prompt_template.replace('{current_file}', current_file_name)

    if existing_index_content:
        current_index_block = (
            "# CURRENT INDEX\n"
            "```json\n"
            f"{existing_index_content}\n"
            "```\n\n"
        )
        prompt = prompt.replace('# RULES', current_index_block + '# RULES', 1)

        rules_block = ''.join(f"* {rule}\n" for rule in ADDITIONAL_RULES)
        prompt = prompt.replace('# RULES\n', '# RULES\n' + rules_block, 1)
    else:
        prompt = prompt.replace('# RULES\n', '# RULES\n* ' + ADDITIONAL_RULES[-1] + '\n', 1)

    return prompt
