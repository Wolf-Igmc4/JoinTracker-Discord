import os, asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands
from fastapi import FastAPI
import uvicorn

load_dotenv()

PORT = int(os.getenv("PORT", 8000))
HOST = "0.0.0.0"

# --- FastAPI ---
app = FastAPI()


# Control de salud del servidor
@app.get("/")
async def root():
    return {"status": "ok"}


@app.head("/")
async def root_head():
    return {"status": "ok"}


# --- Discord ---
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)


@bot.event
async def setup_hook():
    await bot.load_extension("src.cogs.voice_cog")
    await bot.load_extension("src.cogs.commands_cog")
    await bot.load_extension("src.cogs.misc_cog")
    # await bot.load_extension("src.cogs.sync_cog")


@bot.event
async def on_ready():
    print(
        f"Bot conectado como {bot.user} ({bot.user.id}). Servidores: {len(bot.guilds)}"
    )
    try:
        cmds = await bot.tree.sync()
        print(f"{len(cmds)} comandos sincronizados: {[cmd.name for cmd in cmds]}")
    except Exception as e:
        print(f"Error sincronizando comandos: {e}")
    print(f"\n{'='*50}")
    print(f"¡JoinTracker listo y funcionando!")
    print(f"{'='*50}\n")


# --- Función principal ---
async def main():
    token = os.getenv("TOKEN")
    if not token:
        print("ERROR: No se encontró TOKEN.")
        return

    # Lanzar bot y servidor FastAPI juntos
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="info")
    server = uvicorn.Server(config)

    await asyncio.gather(bot.start(token), server.serve())


if __name__ == "__main__":
    asyncio.run(main())
