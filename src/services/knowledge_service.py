import json
from database import find_knowledges_by_folder

def get_existing_knowledges_as_json(folder_path):
    """
    Busca os conhecimentos existentes para uma pasta e os formata como uma string JSON.

    Args:
        folder_path (str): O caminho da pasta a ser consultada.

    Returns:
        str: Uma string JSON contendo os conhecimentos existentes, ou uma string vazia se nenhum for encontrado.
    """
    knowledges_rows = find_knowledges_by_folder(folder_path)

    if not knowledges_rows:
        return ""

    knowledges_list = [dict(row) for row in knowledges_rows]
    
    # Adiciona um ID sequencial para corresponder ao formato de exemplo do prompt
    for i, knowledge in enumerate(knowledges_list):
        knowledge['id'] = i + 1

    output_dict = {"knowledges": knowledges_list}

    return json.dumps(output_dict, indent=4, ensure_ascii=False)
