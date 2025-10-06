import sqlite3
import os

# Define o caminho do banco de dados relativo à localização do script
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')

def get_db_connection():
    """
    Cria e retorna uma conexão com o banco de dados.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permite acessar colunas por nome
    return conn

def initialize_database():
    """
    Inicializa o banco de dados SQLite e cria as tabelas necessárias se não existirem.
    """
    # Garante que o diretório de dados exista
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Cria a tabela 'jobs'
    # stage_id: 1 (criação de índice), 2 (índice gerado), 3 (geração de conhecimento concluída)
    # status_id: 1 (pendente), 2 (em andamento), 3 (concluído), 4 (erro)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        file_name TEXT NOT NULL,
        folder_path TEXT NOT NULL,
        stage_id INTEGER NOT NULL,
        status_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    # Cria a tabela 'knowledges'
    # status_id: 1 (pendente), 2 (em andamento), 3 (concluído), 4 (erro)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS knowledges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        knowledge_id_from_json INTEGER NOT NULL,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        status_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (job_id) REFERENCES jobs (id)
    );
    ''')

    conn.commit()
    conn.close()
    print(f"Banco de dados inicializado com sucesso em {DB_PATH}")


def create_job(file_path, file_name, folder_path):
    """
    Cria um novo job no banco de dados se não existir um para o mesmo file_path.
    Retorna o ID do job (novo ou existente).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Verifica se o job já existe
    cursor.execute("SELECT id FROM jobs WHERE file_path = ?", (file_path,))
    existing_job = cursor.fetchone()

    if existing_job:
        print(f"Job para o arquivo {file_name} já existe com o ID: {existing_job['id']}.")
        conn.close()
        return existing_job['id']
    else:
        # Insere um novo job
        stage_id = 1  # 1: index creation
        status_id = 1 # 1: pending
        cursor.execute(
            "INSERT INTO jobs (file_path, file_name, folder_path, stage_id, status_id) VALUES (?, ?, ?, ?, ?)",
            (file_path, file_name, folder_path, stage_id, status_id)
        )
        new_job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        print(f"Novo job criado para o arquivo {file_name} com o ID: {new_job_id}.")
        return new_job_id

def find_knowledges_by_folder(folder_path):
    """
    Encontra todos os conhecimentos existentes para uma determinada pasta.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT k.category, k.name 
        FROM knowledges k
        JOIN jobs j ON k.job_id = j.id
        WHERE j.folder_path = ?
    """, (folder_path,))

    knowledges = cursor.fetchall()
    conn.close()
    return knowledges

def get_pending_jobs_by_stage(stage_id):
    """
    Busca jobs pendentes (status_id = 1) para um determinado estágio.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM jobs WHERE stage_id = ? AND status_id = 1", 
        (stage_id,)
    )
    jobs = cursor.fetchall()
    conn.close()
    return jobs

def update_job_state(job_id, stage_id, status_id):
    """
    Atualiza o estágio e o status de um job.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET stage_id = ?, status_id = ? WHERE id = ?",
        (stage_id, status_id, job_id)
    )
    conn.commit()
    conn.close()

def add_knowledges_from_json(job_id, knowledges_list):
    """
    Insere uma lista de conhecimentos de um JSON no banco de dados.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    records_to_insert = []
    for knowledge in knowledges_list:
        records_to_insert.append((
            job_id,
            knowledge.get('id'),
            knowledge.get('category'),
            knowledge.get('name'),
            1 # status_id: 1 (pending)
        ))

    cursor.executemany(
        "INSERT INTO knowledges (job_id, knowledge_id_from_json, category, name, status_id) VALUES (?, ?, ?, ?, ?)",
        records_to_insert
    )
    conn.commit()
    conn.close()

def get_pending_knowledges():
    """
    Busca conhecimentos pendentes (status_id = 1) e seus jobs associados.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            k.id as knowledge_id,
            k.category as knowledge_category,
            k.name as knowledge_name,
            j.file_path as job_file_path,
            j.file_name as job_file_name
        FROM knowledges k
        JOIN jobs j ON k.job_id = j.id
        WHERE k.status_id = 1
    """)
    knowledges = cursor.fetchall()
    conn.close()
    return knowledges

def update_knowledge_status(knowledge_id, status_id):
    """
    Atualiza o status de um conhecimento específico.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE knowledges SET status_id = ? WHERE id = ?",
        (status_id, knowledge_id)
    )
    conn.commit()
    conn.close()

def get_completed_jobs_by_stage(stage_id):
    """
    Busca jobs concluídos (status_id = 3) em um determinado estágio.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM jobs WHERE stage_id = ? AND status_id = 3",
        (stage_id,)
    )
    jobs = cursor.fetchall()
    conn.close()
    return jobs

def are_all_knowledges_completed_for_job(job_id):
    """
    Verifica se todos os conhecimentos de um job estão concluídos (status 3) ou se não há conhecimentos.
    Retorna False se algum conhecimento estiver pendente, em andamento ou com erro.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    # Conta quantos conhecimentos NÃO estão com status 3 (concluído)
    cursor.execute(
        "SELECT COUNT(id) FROM knowledges WHERE job_id = ? AND status_id != 3",
        (job_id,)
    )
    non_completed_count = cursor.fetchone()[0]
    conn.close()
    return non_completed_count == 0
