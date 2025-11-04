# bot/main.py
import os, sys, subprocess, socket, time, asyncio, traceback, atexit
from dotenv import load_dotenv

load_dotenv()

import discord
from discord.ext import commands

from bot.webserver import app

# from bot.utils.api_restore import restore_cache_from_api

PORT = int(os.getenv("PORT", 8000))
HOST = "0.0.0.0"


def start_uvicorn_as_subprocess():
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "bot.webserver:app",
        "--host",
        HOST,
        "--port",
        str(PORT),
        "--log-level",
        "info",
    ]
    print(f"[STARTUP] Lanzando uvicorn subprocess: {' '.join(cmd)}")
    try:
        return subprocess.Popen(cmd)
    except Exception as e:
        print(f"[STARTUP][ERROR] fallo al lanzar uvicorn subprocess: {e}")
        traceback.print_exc()
        return None


def wait_for_port(port: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                print(f"[STARTUP] Conexión a 127.0.0.1:{port} establecida.")
                return True
        except:
            time.sleep(0.5)
    print(f"[STARTUP][TIMEOUT] No se pudo conectar a 127.0.0.1:{port} en {timeout}s.")
    return False


def safe_terminate_process(proc):
    if proc is None:
        return
    try:
        if proc.poll() is None:
            print("[SHUTDOWN] Terminando proceso uvicorn...")
            proc.terminate()
            time.sleep(2)
            if proc.poll() is None:
                print("[SHUTDOWN] Forzando kill al proceso uvicorn...")
                proc.kill()
    except Exception as e:
        print(f"[SHUTDOWN][ERROR] al terminar proceso uvicorn: {e}")


# 1) arrancar uvicorn
uvicorn_proc = start_uvicorn_as_subprocess()
atexit.register(lambda: safe_terminate_process(uvicorn_proc))
server_ready = wait_for_port(PORT, timeout=60.0)
if not server_ready:
    print(
        "[STARTUP][WARNING] FastAPI no respondió a tiempo; Koyeb puede marcar health check failed."
    )
else:
    print("[STARTUP] FastAPI lista.")


# 2) configurar bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)


@bot.event
async def setup_hook():
    # restaurar JSON local desde API una sola vez
    # await restore_cache_from_api()

    # cargar cogs aquí
    await bot.load_extension("bot.cogs.voice_cog")
    await bot.load_extension("bot.cogs.commands_cog")
    await bot.load_extension("bot.cogs.misc_cog")
    # await bot.load_extension("bot.cogs.sync_cog")


@bot.event
async def on_ready():
    print(f"\n✓ Bot conectado como {bot.user}")
    print(f"✓ ID: {bot.user.id}")
    print(f"✓ Servidores: {len(bot.guilds)}")
    try:
        cmds = await bot.tree.sync()
        print(
            f"✓ {len(cmds)} comandos sincronizados: {', '.join([c.name for c in cmds])}."
        )
    except Exception as e:
        print(f"✗ Error sincronizando comandos: {e}")
    print(f"\n{'='*50}")
    print(f"🤖 JoinTracker está listo y funcionando!")
    print(f"{'='*50}\n")


async def main():
    async with bot:
        token = os.getenv("TOKEN")
        if not token:
            print("ERROR: No se encontró TOKEN.")
            return
        try:
            await bot.start(token)
        finally:
            safe_terminate_process(uvicorn_proc)


if __name__ == "__main__":
    print("Iniciando bot...")
    try:
        asyncio.run(main())
    finally:
        safe_terminate_process(uvicorn_proc)
