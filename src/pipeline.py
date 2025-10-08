import argparse
import os
import asyncio
import json
import re
from database import (
    initialize_database, 
    create_job, 
    get_pending_jobs_by_stage, 
    update_job_state,
    add_knowledges_from_json,
    get_pending_knowledges,
    update_knowledge_status,
    get_completed_jobs_by_stage,
    are_all_knowledges_completed_for_job
)
from prompt_manager import generate_knowledge_extraction_prompt
from generators.adapta.gemini_generator import GeminiGenerator
from generators.adapta.claude_opus_generator import ClaudeOpusGenerator
from utils.text_cleaner import remove_think_tags

TEMP_INDEX_PATH = 'temp_index'
DOCS_PATH = 'docs'
KNOWLEDGE_PROMPT_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'knowledge_creation.txt')

def slugify(text):
    """Converte uma string em um formato 'slug' seguro para nomes de arquivo/pasta."""
    text = text.lower()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'[^a-z0-9-]', '', text)
    return text.strip('-')

def process_input_folder(folder_path):
    """
    Lógica para o Estágio 1: Escaneia uma pasta e cria jobs para arquivos .txt.
    """
    print(f"Escaneando a pasta de entrada: {folder_path}")
    if not os.path.isdir(folder_path):
        print(f"Erro: O caminho '{folder_path}' não é um diretório válido.")
        return

    for filename in os.listdir(folder_path):
        if filename.endswith(".txt"):
            file_path = os.path.abspath(os.path.join(folder_path, filename))
            create_job(file_path, filename, folder_path)

async def run_stage1_index_creation():
    """
    Executa a etapa de criação de índice para jobs pendentes.
    """
    print("Iniciando Estágio 1: Criação de Índice de Conhecimento.")
    pending_jobs = get_pending_jobs_by_stage(stage_id=1)
    
    if not pending_jobs:
        print("Nenhum job pendente para o Estágio 1.")
        return

    generator = GeminiGenerator()
    
    for job in pending_jobs:
        job_id = job['id']
        print(f"Processando job {job_id} para o arquivo: {job['file_name']}")
        
        try:
            update_job_state(job_id, stage_id=1, status_id=2)
            with open(job['file_path'], 'r', encoding='utf-8') as f:
                file_content = f.read()
            prompt = generate_knowledge_extraction_prompt(file_content, job['folder_path'])
            messages = [{"role": "user", "content": prompt}]
            json_output_str = await generator.call_model_with_messages(messages)
            json_output_str = remove_think_tags(json_output_str)
            json_filename = f"{os.path.splitext(job['file_name'])[0]}.json"
            temp_json_path = os.path.join(TEMP_INDEX_PATH, json_filename)
            match = re.search(r'```json\s*(.*?)\s*```', json_output_str, re.DOTALL)
            if match:
                json_output_str = match.group(1).strip()
            with open(temp_json_path, 'w', encoding='utf-8') as f:
                f.write(json_output_str)
            print(f"JSON salvo em {temp_json_path}")
            data = json.loads(json_output_str)
            knowledges = data.get("knowledges", [])
            if knowledges:
                add_knowledges_from_json(job_id, knowledges)
                print(f"{len(knowledges)} conhecimentos inseridos no banco de dados para o job {job_id}.")
            update_job_state(job_id, stage_id=2, status_id=3)
            print(f"Job {job_id} concluído com sucesso.")
        except Exception as e:
            print(f"Erro ao processar o job {job_id}: {e}")
            update_job_state(job_id, stage_id=1, status_id=4)

async def process_pending_knowledges():
    """
    Lógica para o Estágio 2: Processar conhecimentos pendentes do banco de dados.
    """
    print("\nIniciando Estágio 2: Criação de Arquivos de Conhecimento.")
    pending_knowledges = get_pending_knowledges()

    if not pending_knowledges:
        print("Nenhum conhecimento pendente para processar.")
        return

    generator = GeminiGenerator()
    with open(KNOWLEDGE_PROMPT_PATH, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    for knowledge in pending_knowledges:
        knowledge_id = knowledge['knowledge_id']
        print(f"Processando conhecimento ID: {knowledge_id} - {knowledge['knowledge_name']}")

        try:
            update_knowledge_status(knowledge_id, status_id=2)
            with open(knowledge['job_file_path'], 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            prompt = prompt_template.replace('{knowledge_category}', knowledge['knowledge_category'])
            prompt = prompt.replace('{knowledge_name}', knowledge['knowledge_name'])
            prompt = prompt.replace('{file_content}', file_content)
            #print(prompt)
            messages = [{"role": "user", "content": prompt}]
            #markdown_output = await generator.call_model_with_messages(messages,chat_id=generator.generate_chat_id())
            markdown_output = await generator.call_model_with_messages(messages)
            markdown_output = remove_think_tags(markdown_output)

            doc_slug = slugify(os.path.splitext(knowledge['job_file_name'])[0])
            knowledge_slug = slugify(knowledge['knowledge_name'])
            output_dir = os.path.join(DOCS_PATH, doc_slug)
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"{knowledge_slug}.md")

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_output)
            print(f"Arquivo Markdown salvo em: {output_path}")

            update_knowledge_status(knowledge_id, status_id=3)
            print(f"Conhecimento {knowledge_id} concluído com sucesso.")

        except Exception as e:
            print(f"Erro ao processar o conhecimento {knowledge_id}: {e}")
            update_knowledge_status(knowledge_id, status_id=4)

async def run_stage3_cleanup():
    """
    Finaliza jobs cujos conhecimentos foram todos gerados e remove arquivos temporários.
    """
    print("\nIniciando Estágio 3: Limpeza e Finalização de Jobs.")
    # Busca jobs que passaram pelo estágio de criação de índice
    completed_stage2_jobs = get_completed_jobs_by_stage(stage_id=2)

    if not completed_stage2_jobs:
        print("Nenhum job para finalizar.")
        return

    for job in completed_stage2_jobs:
        job_id = job['id']
        if are_all_knowledges_completed_for_job(job_id):
            print(f"Todos os conhecimentos para o job {job_id} estão concluídos. Finalizando...")
            # Atualiza o job para o estágio final
            update_job_state(job_id, stage_id=3, status_id=3)

            # Remove o arquivo JSON temporário
            json_filename = f"{os.path.splitext(job['file_name'])[0]}.json"
            temp_json_path = os.path.join(TEMP_INDEX_PATH, json_filename)
            try:
                os.remove(temp_json_path)
                print(f"Arquivo temporário {temp_json_path} removido.")
            except FileNotFoundError:
                print(f"Aviso: Arquivo temporário {temp_json_path} não encontrado para remoção.")
            except Exception as e:
                print(f"Erro ao remover o arquivo temporário {temp_json_path}: {e}")
            
            print(f"Job {job_id} finalizado com sucesso.")

async def main():
    """
    Função principal para analisar argumentos e orquestrar o pipeline.
    """
    parser = argparse.ArgumentParser(description="Pipeline de extração e geração de conhecimento.")
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

if __name__ == "__main__":
    asyncio.run(main())
