# bot/utils/api_restore.py
import aiohttp
import os
from bot.utils.json_manager import save_json

API_BASE = os.getenv("PUBLIC_API_BASE")

# nombres de tus ficheros locales
FILES = ["call_data.json", "time_data.json"]


async def restore_cache_from_api():
    """
    Se ejecuta 1 sola vez al arrancar el bot.
    Baja los datos de la API pública y los guarda en local.
    """
    if not API_BASE:
        print("[RESTORE] No hay PUBLIC_API_BASE. No restauro nada.")
        return

    print("[RESTORE] Restaurando cache desde API pública...")

    async with aiohttp.ClientSession() as session:
        for filename in FILES:
            url = f"{API_BASE}/db/{filename}"
            try:

                async def fetch():
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            save_json(data, filename)
                            print(f"[RESTORE] {filename} restaurado.")
                        else:
                            print(f"[RESTORE] {filename} no existe remoto.")

                await fetch()
            except Exception as e:
                print(f"[RESTORE] Error restaurando {filename}: {e}")

    print("[RESTORE] Finalizado.")
