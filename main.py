# main.py

import asyncio
import json
import os
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv
import uvicorn

import src.bot_instance as bot_instance
from src.config import RAIZ_PROYECTO
from src.utils.helpers import stringify_keys, sync_all_guilds
from webserver import app

# ========= Cargar configuración =========
load_dotenv()
TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", 8000))
API_KEY = os.getenv("API_KEY")

if not TOKEN:
    raise ValueError("No se encontró TOKEN de Discord en el .env")


# ========= FastAPI =========
# Control de salud del servidor
@app.get("/")
async def root():
    return {"status": "ok"}


@app.head("/")
async def root_head():
    return {"status": "ok"}


# ========= Discord Bot =========
intents = discord.Intents.all()
bot_instance.bot = commands.Bot(
    command_prefix="/", intents=intents, owner_id=477811183282552854
)
bot = bot_instance.bot


async def restore_stats_per_guild():
    """
    Al arrancar, intenta recuperar stats por cada guild desde /stats/{gid}.
    Muestra la fecha de creación del registro (timestamp) en el log.
    """
    async with aiohttp.ClientSession() as session:
        print("\033[93mRestaurando stats.json por servidor...\033[0m")
        for guild in bot.guilds:
            gid = str(guild.id)
            stats_dir = RAIZ_PROYECTO / "data" / gid
            stats_path = stats_dir / "stats.json"
            stats_dir.mkdir(parents=True, exist_ok=True)

            try:
                url = f"http://localhost:{PORT}/stats/{gid}"
                async with session.get(
                    url, headers={"x-api-key": API_KEY}, timeout=150
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

                    # Obtenemos la respuesta cruda del API
                    payload = await r.json()

                    if isinstance(payload, dict) and "error" not in payload:
                        # 1. Extracción del timestamp
                        raw_date = payload.get("created_at")

                        # Formateo simple de fecha para limpieza visual (opcional)
                        if raw_date:
                            ts_display = str(raw_date).split(".")[0]
                        else:
                            ts_display = "Fecha desconocida"

                        # 2. Extracción de estadísticas
                        # Si tu API devuelve la fila completa, los stats están bajo la clave "data"
                        # Si tu API devuelve solo el JSON mezclado, payload es la data.
                        stats_data = payload.get("data", payload)

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


@bot.event
async def setup_hook():
    await bot.load_extension("src.cogs.voice_cog")
    await bot.load_extension("src.cogs.commands_cog")
    await bot.load_extension("src.cogs.misc_cog")
    await bot.load_extension("src.cogs.sync_cog")


@bot.event
async def on_ready():
    print(
        f"Bot conectado como {bot.user} ({bot.user.id}). Servidores: {len(bot.guilds)}"
    )
    try:
        cmds = await bot.tree.sync()
        print(
            f"\033[32m{len(cmds)} comandos sincronizados: {', '.join([cmd.name for cmd in cmds])}\033[0m"
        )
    except Exception as e:
        print(f"Error sincronizando comandos: {e}")

    ancho_total = 40  # ancho de la línea
    print("\n" + "=" * ancho_total)
    print(f"{'✅ JoinTracker operativo'.center(ancho_total)}")
    print(
        f"{f'🕒 Arranque: {datetime.now().strftime('%H:%M:%S')}'.center(ancho_total)}"
    )
    print("=" * ancho_total + "\n")

    # Lanzar restauración de datos
    bot.loop.create_task(restore_stats_per_guild())


# ========= Función principal =========
async def main():
    # Configuración estándar
    config = uvicorn.Config(
        app, host="0.0.0.0", port=PORT, log_level="info", loop="asyncio"
    )
    server = uvicorn.Server(config)

    # Uvicorn gestionará el cierre y llamará al lifespan de webserver.py
    async with bot_instance.bot:
        await asyncio.gather(bot_instance.bot.start(TOKEN), server.serve())


if __name__ == "__main__":
    asyncio.run(main())
