"""Library visibility and lightweight chapter counts."""

import threading
from cores.storage.project import load_json, save_json
from services.library.repository import projects, safe_project

_lock = threading.RLock()


def hidden_projects(root):
    with _lock:
        data = load_json(root / '.library.json', {})
        if not isinstance(data, dict) or not isinstance(data.get('hidden', []), list) or not all(isinstance(name, str) for name in data.get('hidden', [])):
            raise ValueError('Dữ liệu ẩn truyện không hợp lệ trong .library.json')
        return set(data.get('hidden', []))


def set_hidden(root, name, hidden):
    if type(hidden) is not bool:
        raise ValueError('Trạng thái ẩn phải là bật hoặc tắt')
    path = safe_project(root, name)
    if not path.is_dir() or name not in projects(root):
        raise ValueError('Không tìm thấy truyện')
    with _lock:
        names = hidden_projects(root)
        names.add(name) if hidden else names.discard(name)
        save_json(root / '.library.json', {'hidden': sorted(names)})
    return {'name': name, 'hidden': hidden}


def catalog(root):
    hidden = hidden_projects(root)
    items = []
    for name in projects(root):
        path = safe_project(root, name)
        raw = {p.name for p in (path / 'raw').glob('*.md') if p.is_file()}
        translated = {p.name for p in (path / 'translated').glob('*.md') if p.is_file()}
        items.append({'name': name, 'hidden': name in hidden,
                      'total': len(raw | translated), 'translated': len(translated)})
    return items
