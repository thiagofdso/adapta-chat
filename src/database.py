import sqlite3
import os

from utils.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')


def add_column_if_not_exists(cursor, table_name, column_name, column_type):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def create_files_knowledges_table(cursor):
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS files_knowledges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        knowledge_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,
        FOREIGN KEY (knowledge_id) REFERENCES knowledges (id)
    );
    ''')


def create_knowledge_relations_table(cursor):
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS knowledge_relations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        knowledge_id INTEGER NOT NULL,
        related_knowledge_id INTEGER NOT NULL,
        FOREIGN KEY (knowledge_id) REFERENCES knowledges (id)
    );
    ''')


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = get_db_connection()
    cursor = conn.cursor()

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

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS knowledges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        knowledge_id_from_json INTEGER NOT NULL,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        section_id INTEGER,
        section_title TEXT,
        status_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (job_id) REFERENCES jobs (id)
    );
    ''')

    add_column_if_not_exists(cursor, 'knowledges', 'description', 'TEXT')
    add_column_if_not_exists(cursor, 'knowledges', 'section_id', 'INTEGER')
    add_column_if_not_exists(cursor, 'knowledges', 'section_title', 'TEXT')

    create_files_knowledges_table(cursor)
    create_knowledge_relations_table(cursor)

    conn.commit()
    conn.close()
    logger.info(f"Banco de dados inicializado com sucesso em {DB_PATH}")


def create_job(file_path, file_name, folder_path):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM jobs WHERE file_path = ?", (file_path,))
    existing_job = cursor.fetchone()

    if existing_job:
        logger.info(f"Job para o arquivo {file_name} ja existe com o ID: {existing_job['id']}.")
        conn.close()
        return existing_job['id']

    stage_id = 1
    status_id = 1
    cursor.execute(
        "INSERT INTO jobs (file_path, file_name, folder_path, stage_id, status_id) VALUES (?, ?, ?, ?, ?)",
        (file_path, file_name, folder_path, stage_id, status_id)
    )
    new_job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Novo job criado para o arquivo {file_name} com o ID: {new_job_id}.")
    return new_job_id


def find_knowledges_by_folder(folder_path):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            k.knowledge_id_from_json,
            k.category,
            k.name,
            k.description,
            k.section_id,
            k.section_title,
            GROUP_CONCAT(DISTINCT f.file_name, '||') AS files,
            GROUP_CONCAT(DISTINCT r.related_knowledge_id, '||') AS related_ids
        FROM knowledges k
        JOIN jobs j ON k.job_id = j.id
        LEFT JOIN files_knowledges f ON f.knowledge_id = k.id
        LEFT JOIN knowledge_relations r ON r.knowledge_id = k.id
        WHERE j.folder_path = ?
        GROUP BY k.id
        ORDER BY k.knowledge_id_from_json
    ''', (folder_path,))

    knowledges = cursor.fetchall()
    conn.close()
    return knowledges


def get_pending_jobs_by_stage(stage_id):
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET stage_id = ?, status_id = ? WHERE id = ?",
        (stage_id, status_id, job_id)
    )
    conn.commit()
    conn.close()


def _insert_files_for_knowledge(cursor, knowledge_id, file_names):
    if not file_names:
        return
    unique_names = []
    seen = set()
    for name in file_names:
        name = (name or '').strip()
        if name and name not in seen:
            seen.add(name)
            unique_names.append(name)
    cursor.executemany(
        "INSERT INTO files_knowledges (knowledge_id, file_name) VALUES (?, ?)",
        [(knowledge_id, name) for name in unique_names]
    )


def _insert_related_for_knowledge(cursor, knowledge_id, related_ids):
    if not related_ids:
        return
    unique_ids = []
    seen = set()
    for value in related_ids:
        try:
            related_id = int(value)
        except (TypeError, ValueError):
            continue
        if related_id <= 0 or related_id in seen:
            continue
        seen.add(related_id)
        unique_ids.append(related_id)
    cursor.executemany(
        "INSERT INTO knowledge_relations (knowledge_id, related_knowledge_id) VALUES (?, ?)",
        [(knowledge_id, rid) for rid in unique_ids]
    )


def add_knowledges_from_json(job_id, knowledges_list):
    if not knowledges_list:
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    for knowledge in knowledges_list:
        index_position = knowledge.get('index')
        try:
            knowledge_order = int(index_position) + 1
        except (TypeError, ValueError):
            knowledge_order = 0

        cursor.execute(
            "INSERT INTO knowledges (job_id, knowledge_id_from_json, category, name, description, section_id, section_title, status_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                knowledge_order,
                knowledge.get('category') or 'Geral',
                knowledge.get('name') or '',
                knowledge.get('description') or '',
                None,
                None,
                1
            )
        )
        knowledge_db_id = cursor.lastrowid
        file_list = []
        for value in knowledge.get('files') or []:
            clean = str(value).strip()
            if clean and clean not in file_list:
                file_list.append(clean)
            if len(file_list) >= 5:
                break
        _insert_files_for_knowledge(cursor, knowledge_db_id, file_list)
        _insert_related_for_knowledge(cursor, knowledge_db_id, [])

    conn.commit()
    conn.close()


def get_pending_knowledges():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            k.id AS knowledge_id,
            k.knowledge_id_from_json AS knowledge_json_id,
            k.category AS knowledge_category,
            k.name AS knowledge_name,
            k.description AS knowledge_description,
            k.section_id AS knowledge_section_id,
            k.section_title AS knowledge_section_title,
            j.file_path AS job_file_path,
            j.file_name AS job_file_name,
            j.folder_path AS job_folder_path,
            GROUP_CONCAT(DISTINCT f.file_name, '||') AS file_names,
            GROUP_CONCAT(DISTINCT r.related_knowledge_id, '||') AS related_ids
        FROM knowledges k
        JOIN jobs j ON k.job_id = j.id
        LEFT JOIN files_knowledges f ON f.knowledge_id = k.id
        LEFT JOIN knowledge_relations r ON r.knowledge_id = k.id
        WHERE k.status_id = 1
        GROUP BY k.id
    ''')
    knowledges = cursor.fetchall()
    conn.close()
    return knowledges


def update_knowledge_status(knowledge_id, status_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE knowledges SET status_id = ? WHERE id = ?",
        (status_id, knowledge_id)
    )
    conn.commit()
    conn.close()


def get_completed_jobs_by_stage(stage_id):
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(id) FROM knowledges WHERE job_id = ? AND status_id != 3",
        (job_id,)
    )
    non_completed_count = cursor.fetchone()[0]
    conn.close()
    return non_completed_count == 0
