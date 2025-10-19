import os
import sqlite3
from typing import Iterable, Optional

from utils.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')


def create_files_knowledges_table(cursor) -> None:
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS files_knowledges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            FOREIGN KEY (knowledge_id) REFERENCES knowledges (id)
        );
        '''
    )


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            stage_id INTEGER NOT NULL,
            status_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS knowledges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            position INTEGER,
            folder_path TEXT NOT NULL,
            status_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        '''
    )

    create_files_knowledges_table(cursor)

    conn.commit()
    conn.close()
    logger.info(f"Banco de dados inicializado com sucesso em {DB_PATH}")


def create_job(file_path: str, file_name: str, folder_path: str) -> int:
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
        (file_path, file_name, folder_path, stage_id, status_id),
    )
    new_job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Novo job criado para o arquivo {file_name} com o ID: {new_job_id}.")
    return new_job_id


def find_knowledges_by_folder(folder_path: str) -> Iterable[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        '''
        SELECT
            k.position,
            k.name,
            k.description,
            k.folder_path,
            (
                SELECT GROUP_CONCAT(file_name, '||')
                FROM (
                    SELECT DISTINCT file_name
                    FROM files_knowledges
                    WHERE knowledge_id = k.id
                )
            ) AS files
        FROM knowledges k
        WHERE k.folder_path = ?
        ORDER BY COALESCE(k.position, k.id)
        ''',
        (folder_path,),
    )

    knowledges = cursor.fetchall()
    conn.close()
    return knowledges


def get_pending_jobs_by_stage(stage_id: int) -> Iterable[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM jobs WHERE stage_id = ? AND status_id = 1",
        (stage_id,),
    )
    jobs = cursor.fetchall()
    conn.close()
    return jobs


def update_job_state(job_id: int, stage_id: int, status_id: int) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET stage_id = ?, status_id = ? WHERE id = ?",
        (stage_id, status_id, job_id),
    )
    conn.commit()
    conn.close()


def _insert_files_for_knowledge(cursor, knowledge_id: int, file_names: Iterable[str]) -> None:
    unique_names = []
    seen = set()
    for name in file_names or []:
        clean = (name or '').strip()
        if clean and clean not in seen:
            seen.add(clean)
            unique_names.append(clean)
    if unique_names:
        cursor.executemany(
            "INSERT INTO files_knowledges (knowledge_id, file_name) VALUES (?, ?)",
            [(knowledge_id, name) for name in unique_names],
        )


def add_knowledges_from_json(knowledges_list: Optional[Iterable[dict]]) -> None:
    if not knowledges_list:
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    for knowledge in knowledges_list:
        try:
            position = int(knowledge.get('index')) + 1
        except (TypeError, ValueError):
            position = None

        name = str(knowledge.get('name') or '').strip()
        description = str(knowledge.get('description') or '').strip()
        folder_path = str(knowledge.get('folder_path') or '').strip()
        status_id = knowledge.get('status_id') or 1

        if not folder_path:
            logger.warning(f"Pasta nao informada para o conhecimento '{name}'. Registro ignorado.")
            continue

        cursor.execute(
            '''
            INSERT INTO knowledges (
                name,
                description,
                position,
                folder_path,
                status_id
            ) VALUES (?, ?, ?, ?, ?)
            ''',
            (
                name,
                description,
                position,
                folder_path,
                status_id,
            ),
        )
        knowledge_db_id = cursor.lastrowid
        file_list = []
        for value in knowledge.get('files') or []:
            clean = str(value or '').strip()
            if clean and clean not in file_list:
                file_list.append(clean)
            if len(file_list) >= 5:
                break
        _insert_files_for_knowledge(cursor, knowledge_db_id, file_list)

    conn.commit()
    conn.close()


def get_pending_knowledges() -> Iterable[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT
            k.id AS knowledge_id,
            k.position AS knowledge_position,
            k.name AS knowledge_name,
            k.description AS knowledge_description,
            k.folder_path AS knowledge_folder_path,
            (
                SELECT GROUP_CONCAT(file_name, '||')
                FROM (
                    SELECT DISTINCT file_name
                    FROM files_knowledges
                    WHERE knowledge_id = k.id
                )
            ) AS file_names
        FROM knowledges k
        WHERE k.status_id = 1
        ORDER BY COALESCE(k.position, k.id)
        '''
    )
    knowledges = cursor.fetchall()
    conn.close()
    return knowledges


def update_knowledge_status(knowledge_id: int, status_id: int) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE knowledges SET status_id = ? WHERE id = ?",
        (status_id, knowledge_id),
    )
    conn.commit()
    conn.close()


def get_completed_jobs_by_stage(stage_id: int) -> Iterable[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM jobs WHERE stage_id = ? AND status_id = 3",
        (stage_id,),
    )
    jobs = cursor.fetchall()
    conn.close()
    return jobs


def are_all_knowledges_completed_for_folder(folder_path: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(id) FROM knowledges WHERE folder_path = ? AND status_id != 3",
        (folder_path,),
    )
    non_completed_count = cursor.fetchone()[0]
    conn.close()
    return non_completed_count == 0


def count_knowledges_by_folder(folder_path: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(id) FROM knowledges WHERE folder_path = ?",
        (folder_path,),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return int(count or 0)
