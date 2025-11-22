# main.py

import asyncio
import os
from datetime import datetime

import discord
from discord.ext import commands
from dotenv import load_dotenv
import uvicorn

import src.bot_instance as bot_instance
from webserver import app
from src.utils.data_handler import restore_stats_per_guild

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

    # Restauración de datos de BBDD externa al iniciar bot
    bot.loop.create_task(restore_stats_per_guild(bot, PORT, API_KEY))


# ========= Función principal =========
async def main():
    config = uvicorn.Config(
        app, host="0.0.0.0", port=PORT, log_level="info", loop="asyncio"
    )
    server = uvicorn.Server(config)

    # Uvicorn gestionará el cierre y llamará al lifespan de webserver.py
    async with bot_instance.bot:
        await asyncio.gather(bot_instance.bot.start(TOKEN), server.serve())


if __name__ == "__main__":
    asyncio.run(main())
