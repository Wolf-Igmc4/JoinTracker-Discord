# src/utils/json_manager.py
import json, os
from src.config import RAIZ_PROYECTO


def load_json(filename):
    path = os.path.join(RAIZ_PROYECTO, "data", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)  # crea carpeta si no existe

    if not os.path.exists(path):
        # archivo no existe: devuelve dict vacío y lo crea vacío
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


def save_json(filename: str, data: dict):
    path = os.path.join(RAIZ_PROYECTO, "data", filename)

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, sort_keys=True)
