# bot/main.py
import os
import sys
import subprocess
import threading
import socket
import time
import asyncio
import traceback
import atexit

from dotenv import load_dotenv

load_dotenv()  # cargar .env antes de nada (si lo usas localmente)

import discord
from discord.ext import commands

# Importar app de FastAPI (solo para asegurar que el módulo se importe y las tablas se creen)
from bot.webserver import app

# ---- Configuración: usar PORT que Koyeb inyecta ----
PORT = int(
    os.getenv("PORT", 8000)
)  # Koyeb suele pasar PORT=8000, lo leemos dinámicamente
HOST = "0.0.0.0"


def start_uvicorn_as_subprocess():
    """
    Lanza `python -m uvicorn bot.webserver:app ...` en un proceso hijo.
    Devuelve el objeto Popen o None en caso de fallo.
    """
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
        proc = subprocess.Popen(cmd)
        return proc
    except Exception as e:
        print(f"[STARTUP][ERROR] fallo al lanzar uvicorn subprocess: {e}")
        traceback.print_exc()
        return None


def wait_for_port(
    host: str, port: int, timeout: float = 60.0, interval: float = 0.5
) -> bool:
    """
    Espera hasta que haya algo escuchando en host:port o hasta timeout (segundos).
    Devuelve True si se conecta correctamente, False si expira el timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            # Intentamos conectar a localhost:port
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                print(f"[STARTUP] Conexión a 127.0.0.1:{port} establecida.")
                return True
        except Exception:
            time.sleep(interval)
    print(f"[STARTUP][TIMEOUT] No se pudo conectar a 127.0.0.1:{port} en {timeout}s.")
    return False


def safe_terminate_process(proc):
    """Termina el proceso si sigue vivo (intenta terminate, luego kill)."""
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


# --- Arrancar Uvicorn como subprocess y esperar a que el puerto esté listo ---
uvicorn_proc = start_uvicorn_as_subprocess()
# Registrar terminador para que al salir del proceso principal se intente cerrar el hijo
atexit.register(lambda: safe_terminate_process(uvicorn_proc))

server_ready = wait_for_port("127.0.0.1", PORT, timeout=60.0)

if not server_ready:
    print(
        "[STARTUP][WARNING] FastAPI no respondió a tiempo; Koyeb puede marcar health check failed."
    )
else:
    print("[STARTUP] FastAPI lista, continuando con arranque del bot.")


# ---- Ahora arrancamos el bot (proceso principal) ----

# Configurar intents y bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)


@bot.event
async def on_ready():
    print(f"\n✓ Bot conectado como {bot.user}")
    print(f"✓ ID: {bot.user.id}")
    print(f"✓ Servidores: {len(bot.guilds)}")
    try:
        commands_synced = await bot.tree.sync()
        print(
            f"✓ {len(commands_synced)} comandos sincronizados: {', '.join([cmd.name for cmd in commands_synced])}."
        )
    except Exception as e:
        print(f"✗ Error sincronizando comandos: {e}")
    print(f"\n{'='*50}")
    print(f"🤖 JoinTracker está listo y funcionando!")
    print(f"{'='*50}\n")


async def load_cogs():
    await bot.load_extension("bot.cogs.voice_cog")
    await bot.load_extension("bot.cogs.commands_cog")
    await bot.load_extension("bot.cogs.misc_cog")


async def main():
    async with bot:
        print("Cargando extensiones...")
        try:
            await load_cogs()
            print("Extensiones cargadas correctamente.")
        except Exception as e:
            print(f"Error cargando extensiones: {e}")
            raise

        print("Conectando con Discord...")
        token = os.getenv("TOKEN")
        if not token:
            print(
                "ERROR: No se encontró el TOKEN. Asegúrate de configurar la variable de entorno TOKEN."
            )
            return

        try:
            await bot.start(token)
        except discord.LoginFailure:
            print("ERROR: Token inválido. Verifica que el TOKEN sea correcto.")
            raise
        except discord.PrivilegedIntentsRequired:
            print("ERROR: Se requieren intents privilegiados.")
            raise
        except Exception as e:
            print(f"Error conectando con Discord: {e}")
            traceback.print_exc()
            raise
        finally:
            # Cuando el bot termine, intentamos limpiar el proceso uvicorn
            safe_terminate_process(uvicorn_proc)


if __name__ == "__main__":
    print("Iniciando bot...")
    try:
        asyncio.run(main())
    finally:
        # Por si asyncio.run termina sin invocar finally anterior
        safe_terminate_process(uvicorn_proc)
