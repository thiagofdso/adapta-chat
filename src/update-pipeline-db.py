#!/usr/bin/env python3
"""
Utility script to update stored paths inside the pipeline database.

Usage:
    poetry run python src/update-pipeline-db.py --old-path "C:\\old" --new-path "C:\\new"
"""

import argparse
import sys
from typing import Dict, Tuple

from database import DB_PATH, get_db_connection
from utils.logger import logger


UpdateResult = Dict[Tuple[str, str], int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Substitui partes dos caminhos salvos nas tabelas jobs e knowledges."
    )
    parser.add_argument(
        "--old-path",
        required=True,
        help="Trecho atual do caminho que deve ser substituído (ex: C:\\whatsweb\\adapta\\).",
    )
    parser.add_argument(
        "--new-path",
        required=True,
        help="Novo trecho que substituirá o caminho antigo.",
    )
    return parser.parse_args()


def replace_paths(old_path: str, new_path: str) -> UpdateResult:
    conn = get_db_connection()
    cursor = conn.cursor()

    updates = (
        ("jobs", "file_path"),
        ("jobs", "folder_path"),
        ("knowledges", "folder_path"),
    )

    results: UpdateResult = {}
    for table, column in updates:
        cursor.execute(
            f"""
            UPDATE {table}
            SET {column} = REPLACE({column}, ?, ?)
            WHERE INSTR({column}, ?) > 0
            """,
            (old_path, new_path, old_path),
        )
        results[(table, column)] = cursor.rowcount or 0

    conn.commit()
    conn.close()
    return results


def main() -> int:
    args = parse_args()
    old_path = (args.old_path or "").strip()
    new_path = (args.new_path or "").strip()

    if not old_path:
        logger.error("--old-path não pode ser vazio.")
        return 2

    if not new_path:
        logger.error("--new-path não pode ser vazio.")
        return 2

    if old_path == new_path:
        logger.warning("Os valores de --old-path e --new-path são idênticos; nada será alterado.")
        return 0

    logger.info(f"Atualizando caminhos no banco {DB_PATH}")
    results = replace_paths(old_path, new_path)
    total_updates = sum(results.values())

    for (table, column), count in results.items():
        logger.info(f"Tabela {table} coluna {column} -> {count} registros atualizados.")

    if total_updates == 0:
        logger.info("Nenhum registro continha o trecho informado.")
    else:
        logger.success(f"Atualização concluída. {total_updates} registros modificados ao todo.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
