import os

PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_extraction.txt')
CONTINUATION_PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_extraction_continuation.txt')

BASE_ADDITIONAL_RULES = [
    "Quando identificar relacoes entre conhecimentos, preencha \"knowledge_related\" com os IDs correspondentes e mantenha valores existentes."
]

CONTINUATION_ADDITIONAL_RULES = [
    "Continue o indice existente adicionando apenas os elementos novos identificados no documento atual.",
    "Voce pode criar novas secoes e adicionar novos conhecimentos as secoes existentes sempre que necessario.",
    "Adicione o arquivo atual a lista \"files\" de cada conhecimento pertinente, mantendo tambem os arquivos ja registrados anteriormente.",
    "Quando identificar relacoes entre conhecimentos, preencha \"knowledge_related\" com os IDs correspondentes e mantenha valores existentes.",
    "Retorne exclusivamente operacoes JSON Patch que representem as mudancas necessarias; nao replique o indice completo.",
    "Utilize apenas operacoes validas (como \"add\" e \"replace\") com caminhos JSON Pointer.",
    "Cada objeto de conhecimento fornecido deve conter \"id\", \"category\", \"name\", \"description\", \"files\" (lista de strings) e \"knowledge_related\" (lista de inteiros)."
]


def generate_knowledge_extraction_prompt(current_file_name, existing_index_path=None):
    """Gera o prompt de extracao de conhecimento, adicionando indice atual e regras dinamicas."""
    template_path = CONTINUATION_PROMPT_FILE_PATH if existing_index_path else PROMPT_FILE_PATH

    with open(template_path, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    prompt = prompt_template.replace('{current_file}', current_file_name)

    if existing_index_path:
        index_name = os.path.basename(existing_index_path)
        prompt = prompt.replace('{current_index_file}', index_name)
        rules_block = ''.join(f"* {rule}\n" for rule in CONTINUATION_ADDITIONAL_RULES)
    else:
        prompt = prompt.replace('{current_index_file}', 'nenhum (primeira execucao)')
        rules_block = ''.join(f"* {rule}\n" for rule in BASE_ADDITIONAL_RULES)

    prompt = prompt.replace('# RULES\n', '# RULES\n' + rules_block, 1)

    return prompt
