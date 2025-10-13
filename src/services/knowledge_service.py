import json
from collections import OrderedDict
from database import find_knowledges_by_folder


def _section_key(section_id, section_title):
    return section_id, section_title or ''


def _extract_files(files_raw):
    if not files_raw:
        return []
    items = []
    seen = set()
    for name in str(files_raw).split('||'):
        clean = name.strip()
        if clean and clean not in seen:
            seen.add(clean)
            items.append({'name': clean})
    return items


def _extract_related_ids(related_raw):
    if not related_raw:
        return []
    ids = []
    seen = set()
    for value in str(related_raw).split('||'):
        value = value.strip()
        if not value:
            continue
        try:
            related_id = int(value)
        except ValueError:
            continue
        if related_id <= 0 or related_id in seen:
            continue
        seen.add(related_id)
        ids.append(related_id)
    return ids


def get_existing_knowledges_as_json(folder_path):
    rows = find_knowledges_by_folder(folder_path)
    if not rows:
        return ""

    sections_map = OrderedDict()

    for row in rows:
        row_dict = dict(row)
        section_id = row_dict.get('section_id')
        section_title = row_dict.get('section_title')
        key = _section_key(section_id, section_title)

        if key not in sections_map:
            sections_map[key] = {
                'section_id': section_id,
                'title': section_title,
                'knowledges': []
            }

        sections_map[key]['knowledges'].append({
            'id': row_dict.get('knowledge_id_from_json'),
            'category': row_dict.get('category'),
            'name': row_dict.get('name'),
            'description': row_dict.get('description') or '',
            'files': _extract_files(row_dict.get('files')),
            'knowledge_related': _extract_related_ids(row_dict.get('related_ids'))
        })

    sections = list(sections_map.values())

    for index, section in enumerate(sections, start=1):
        if section['section_id'] is None:
            section['section_id'] = index
        if not section['title']:
            section['title'] = f"section {section['section_id']}"

        for knowledge_index, knowledge in enumerate(section['knowledges'], start=1):
            if knowledge['id'] is None:
                knowledge['id'] = knowledge_index

    return json.dumps({'sections': sections}, indent=4, ensure_ascii=False)
