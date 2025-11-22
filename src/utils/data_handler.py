# src/utils/data_handler.py

import json
import os
import aiohttp
from src.config import RAIZ_PROYECTO


# ---------------------------------------------------------
# FUNCIONES DE UTILIDAD (Movidas aquí desde helpers)
# ---------------------------------------------------------
def stringify_keys(obj):
    """
    Recorre recursivamente un objeto (diccionarios y listas) y asegura que
    todas las claves de los diccionarios sean de tipo 'str'.

    Esta función es esencial para garantizar que los datos sean serializables
    de forma segura en JSON, especialmente al interactuar entre diferentes
    sistemas (como una BBDD, un cliente Python y un archivo JSON).

    Maneja casos específicos:
    - Convierte claves `None` (objeto Python) a "None" (string).
    - Convierte claves "null" (string) a "None" (string) para evitar
      la asimetría de deserialización de JSON (donde "null" -> None).
    - Convierte otras claves no-string (como 'int') a su representación 'str'.

    :param obj: El objeto (dict, list, u otro) a sanear.
    :return: Una nueva copia del objeto con todas las claves de diccionario
             convertidas a 'str'.
    """
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k is None or k == "null":
                new_key = "None"
            elif not isinstance(k, str):
                new_key = str(k)
            else:
                new_key = k
            new[new_key] = stringify_keys(v)
        return new
    elif isinstance(obj, list):
        return [stringify_keys(i) for i in obj]
    else:
        return obj


# ---------------------------------------------------------
# FUNCIONES DE BAJO NIVEL (Mecanismo I/O)
# ---------------------------------------------------------
def load_json(filename):
    path = os.path.join(RAIZ_PROYECTO, "data", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if not os.path.exists(path):
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


# ---------------------------------------------------------
# FUNCIONES DE LÓGICA DE NEGOCIO (Services)
# ---------------------------------------------------------
async def restore_stats_per_guild(bot, port: int, api_key: str):
    """
    Al arrancar, intenta recuperar stats por cada guild desde /stats/{gid}.
    Muestra la fecha de creación del registro (timestamp) en el log.
    Recibe dependencias como argumentos para evitar ciclos de importación.
    """
    async with aiohttp.ClientSession() as session:
        print("\033[93mRestaurando stats.json por servidor...\033[0m")

        for guild in bot.guilds:
            gid = str(guild.id)
            stats_dir = RAIZ_PROYECTO / "data" / gid
            stats_path = stats_dir / "stats.json"
            stats_dir.mkdir(parents=True, exist_ok=True)

            try:
                url = f"http://localhost:{port}/stats/{gid}"

                async with session.get(
                    url, headers={"x-api-key": api_key}, timeout=150
                ) as r:
                    if r.status != 200:
                        if r.status == 404:
                            print(
                                f"[INIT] servidor {gid}: no hay registro previo (404)."
                            )
                        else:
                            print(
                                f"[INIT] servidor {gid}: error inesperado ({r.status})."
                            )
                        continue

                    payload = await r.json()

                    if isinstance(payload, dict) and "error" not in payload:
                        raw_date = payload.get("created_at")

                        if raw_date:
                            ts_display = str(raw_date).split(".")[0]
                        else:
                            ts_display = "Fecha desconocida"

                        stats_data = payload.get("data", payload)

                        # Usamos la función robusta definida arriba
                        safe_data_local = stringify_keys(stats_data)

                        with stats_path.open("w", encoding="utf-8") as f:
                            json.dump(safe_data_local, f, indent=2)

                        print(
                            f"\033[32m[INIT] stats.json restaurado para {gid} "
                            f"| Fecha BBDD: {ts_display}\033[0m"
                        )
                    else:
                        print(f"\033[33m[INIT] no hay datos válidos para {gid}\033[0m")

            except Exception as e:
                print(f"\033[31m[INIT] excepción al recuperar stats {gid}: {e}\033[0m")

        print("\033[93mRestauración completada.\033[0m")
