# bot/utils/json_manager.py
import json, os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        print(
            f"\033[0;33m{filename} no existe, se creará automáticamente cuando se añada un dato.\033[0m"
        )
        return {}

    with open(path, "r", encoding="utf-8") as f:
        print(f"[DEBUG] {filename} cargado.")
        return json.load(f)


def save_json(data, filename):
    path = os.path.join(DATA_DIR, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
