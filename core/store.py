"""Tiny JSON file store: users, characters, styles, projects, jobs, autosaves."""
import json, threading, time, uuid
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "db.json"
_lock = threading.Lock()

DEFAULT = {
    "users": [],
    "characters": [
        {
            "id": "narrator", "owner_id": "guest",
            "name": "Narrator",
            "description": "Calm, clear documentary narrator, medium pitch",
            "gender": "masculine",
            "language": "en-IN",
            "voice": "en-IN-PrabhatNeural",
            "rate": "+0%",
            "pitch": "+0Hz",
            "color": "#7c3aed",
        }
    ],
    "styles": [
        {"id": "cinematic-dark", "owner_id": "guest", "name": "Cinematic Dark", "prompt": "dark cinematic, gold accents",
         "bg": "#0b1020", "primary": "#7c3aed", "accent": "#f59e0b", "text": "#ffffff", "font_style": "bold"},
        {"id": "clean-minimal", "owner_id": "guest", "name": "Clean Minimal", "prompt": "minimal white clean",
         "bg": "#f8fafc", "primary": "#0f172a", "accent": "#2563eb", "text": "#0f172a", "font_style": "regular"},
        {"id": "neon-tech", "owner_id": "guest", "name": "Neon Tech", "prompt": "neon cyberpunk tech",
         "bg": "#050510", "primary": "#06b6d4", "accent": "#ec4899", "text": "#e0faff", "font_style": "bold"},
        {"id": "sunset-story", "owner_id": "guest", "name": "Sunset Story", "prompt": "warm sunset story cartoon",
         "bg": "#2b1608", "primary": "#ea580c", "accent": "#facc15", "text": "#fff7ed", "font_style": "bold"},
    ],
    "projects": [],
    "jobs": [],
    "autosaves": {},
}


def load():
    with _lock:
        if not DB_PATH.exists():
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            DB_PATH.write_text(json.dumps(DEFAULT, indent=2))
            return json.loads(json.dumps(DEFAULT))
        try:
            data = json.loads(DB_PATH.read_text() or "{}")
        except Exception:
            data = {}
        for k, v in DEFAULT.items():
            data.setdefault(k, v)
        return data


def save(data):
    with _lock:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        DB_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def upsert(collection: str, item: dict):
    data = load()
    if not item.get("id"):
        item["id"] = uuid.uuid4().hex[:10]
    item.setdefault("updated_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    items = data[collection]
    for i, old in enumerate(items):
        if old.get("id") == item["id"]:
            items[i] = {**old, **item, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            save(data)
            return items[i]
    item.setdefault("created_at", item["updated_at"])
    items.append(item)
    save(data)
    return item


def find(collection: str, item_id: str):
    for x in load().get(collection, []):
        if x.get("id") == item_id:
            return x
    return None


def delete(collection: str, item_id: str):
    data = load()
    data[collection] = [x for x in data[collection] if x.get("id") != item_id]
    save(data)
    return True


def set_autosave(owner_id: str, draft: dict, updated_at: str = ""):
    data = load()
    if not isinstance(data.get("autosaves"), dict):
        data["autosaves"] = {}
    data["autosaves"][owner_id] = {
        "owner_id": owner_id,
        "updated_at": updated_at or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "draft": draft or {},
    }
    save(data)
    return data["autosaves"][owner_id]


def get_autosave(owner_id: str):
    autos = load().get("autosaves") or {}
    return autos.get(owner_id) or {"owner_id": owner_id, "updated_at": "", "draft": {}}
