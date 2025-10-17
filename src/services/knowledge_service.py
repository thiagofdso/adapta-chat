import json
from database import find_knowledges_by_folder


def _extract_files(files_raw):
    if not files_raw:
        return []
    items = []
    seen = set()
    for name in str(files_raw).split('||'):
        clean = name.strip()
        if clean and clean not in seen:
            seen.add(clean)
            items.append(clean)
        if len(items) >= 5:
            break
    return items


def get_existing_knowledges_as_json(folder_path):
    rows = find_knowledges_by_folder(folder_path)
    if not rows:
        return ""

    knowledges = []
    for row in rows:
        row_dict = dict(row)
        knowledges.append({
            'name': row_dict.get('name') or '',
            'description': row_dict.get('description') or '',
            'files': _extract_files(row_dict.get('files'))
        })

    return json.dumps({'knowledges': knowledges}, indent=4, ensure_ascii=False)
