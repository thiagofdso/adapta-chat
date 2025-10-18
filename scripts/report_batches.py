import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / 'src'
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from database import get_db_connection, initialize_database

STATUS_LABELS = {
    1: 'pendente',
    2: 'processando',
    3: 'concluido',
    4: 'falhou',
    5: 'descartado',
}


def _format_timestamp(value: str) -> str:
    if not value:
        return '-'
    try:
        return datetime.fromisoformat(value.replace('Z', '')).strftime('%Y-%m-%d %H:%M')
    except ValueError:
        return value


def fetch_all_batch_runs() -> List[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM batch_runs ORDER BY created_at ASC')
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def render_summary(runs: List[Dict]) -> None:
    summary = defaultdict(lambda: defaultdict(int))
    for run in runs:
        summary[run['stage']][run['status_id']] += 1

    if not summary:
        print('Nenhum lote registrado.')
        return

    print('Resumo por estagio:')
    for stage, counts in summary.items():
        total = sum(counts.values())
        parts = [f"total={total}"]
        for status_id in sorted(STATUS_LABELS):
            if counts.get(status_id):
                parts.append(f"{STATUS_LABELS[status_id]}={counts[status_id]}")
        print(f"- {stage}: " + ', '.join(parts))
    print()


def render_details(runs: List[Dict], limit: int) -> None:
    if not runs:
        return

    runs_sorted = sorted(runs, key=lambda item: item['created_at'])
    print(f'Ultimos {limit} lotes:')
    header = f"{'id':>4}  {'stage':<8}  {'status':<12}  {'in/out':<9}  {'created':<16}  {'finished':<16}  {'consumed':<16}"
    print(header)
    print('-' * len(header))

    for run in runs_sorted[-limit:]:
        status_label = STATUS_LABELS.get(run['status_id'], f"status_{run['status_id']}")
        created_at = _format_timestamp(run.get('created_at'))
        finished_at = _format_timestamp(run.get('finished_at') or '')
        consumed_at = _format_timestamp(run.get('consumed_at') or '')
        counts = f"{run.get('input_count', 0)}/{run.get('output_count', 0)}"
        print(f"{run['id']:>4}  {run['stage']:<8}  {status_label:<12}  {counts:<9}  "
              f"{created_at:<16}  {finished_at:<16}  {consumed_at:<16}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description='Relatorio dos lotes do pipeline.')
    parser.add_argument('--limit', type=int, default=10, help='Quantidade de lotes recentes a exibir.')
    args = parser.parse_args()

    initialize_database()
    runs = fetch_all_batch_runs()
    if not runs:
        print('Nenhum lote encontrado no banco de dados.')
        return

    render_summary(runs)
    render_details(runs, limit=max(1, args.limit))


if __name__ == '__main__':
    main()
