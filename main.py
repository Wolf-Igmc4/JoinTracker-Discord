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
    Además, sanea los datos recibidos para evitar problemas con claves no string.
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
                                f"[INIT] servidor {gid}: no hay registro previo en la BBDD (ERROR 404)."
                            )
                        else:
                            print(
                                f"[INIT] servidor {gid}: error inesperado (ERROR {r.status})."
                            )
                        continue

                    data = await r.json()

                    if isinstance(data, dict) and "error" not in data:
                        # Se sanearán los datos recibidos
                        safe_data_local = stringify_keys(data)

                        with stats_path.open("w", encoding="utf-8") as f:
                            json.dump(safe_data_local, f, indent=2)

                        print(
                            f"\033[32m[INIT] stats.json restaurado para servidor {gid}\033[0m"
                        )
                    else:
                        print(f"\033[33m[INIT] no hay datos para servidor {gid}\033[0m")
            except Exception as e:
                print(
                    f"\033[31m[INIT] no se pudo recuperar stats para servidor {gid}: {e}\033[0m"
                )
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


# ========= Funciones de apagado =========
async def save_before_close():
    """
    Función ejecutada cuando se detecta señal de apagado.
    """
    print("🚨 Apagado detectado: iniciando guardado a BBDD 🚨")

    try:
        await sync_all_guilds(bot, force=False)
        print("✅ [SHUTDOWN] Datos guardados y sincronizados correctamente.")
    except Exception as e:
        print(f"❌ [SHUTDOWN] Error crítico guardando datos: {e}")


# ========= Función principal =========
async def main():
    config = uvicorn.Config(
        app, host="0.0.0.0", port=PORT, log_level="info", loop="asyncio"
    )
    server = uvicorn.Server(config)

    try:
        # Ejecutar bot y FastAPI juntos
        await asyncio.gather(bot.start(TOKEN), server.serve())

    except (KeyboardInterrupt, asyncio.CancelledError):
        # Capturar Ctrl+C o señal de parada de Koyeb
        print("\nSeñal de interrupción recibida. Cerrando el bot...")

    finally:
        # 1. Guardar datos antes de cerrar
        await save_before_close()

        # 2. Cerrar bot
        if not bot.is_closed():
            await bot.close()
            print("🐉 JoinTracker desconectado.")


if __name__ == "__main__":
    asyncio.run(main())
