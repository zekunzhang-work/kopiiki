import os
from pathlib import Path


_LOADED = False


def load_kopiiki_env():
    global _LOADED
    if _LOADED:
        return []

    backend_dir = Path(__file__).resolve().parent
    root_dir = backend_dir.parent
    loaded_files = []

    for env_path in (root_dir / ".env", backend_dir / ".env"):
        if load_env_file(env_path):
            loaded_files.append(str(env_path))

    _LOADED = True
    return loaded_files


def load_env_file(env_path):
    if not env_path.exists() or not env_path.is_file():
        return False

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
            continue
        if key in os.environ:
            continue
        os.environ[key] = clean_env_value(value)

    return True


def clean_env_value(value):
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1]
    return cleaned
