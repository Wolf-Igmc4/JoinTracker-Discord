# bot/main.py
import os
import threading
import socket
import time
import asyncio
import traceback

from dotenv import load_dotenv

load_dotenv()  # cargar .env antes de nada (si lo usas localmente)

import discord
from discord.ext import commands

# Importar app de FastAPI (no inicia aquí, solo importa la instancia)
from bot.webserver import app
import uvicorn

# ---- Configuración: usar PORT que Koyeb inyecta ----
PORT = int(
    os.getenv("PORT", 8000)
)  # Koyeb suele pasar PORT=8000, pero lo leemos dinámicamente
HOST = "0.0.0.0"


def start_uvicorn_in_thread():
    """Arranca uvicorn en hilo y no bloquea el hilo principal."""

    def _run():
        try:
            print(
                f"[STARTUP] Uvicorn iniciando en {HOST}:{PORT} (tomado de PORT env var)."
            )
            uvicorn.run(app, host=HOST, port=PORT, log_level="info")
        except Exception as e:
            print(f"[STARTUP][ERROR] uvicorn falló al arrancar: {e}")
            traceback.print_exc()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def wait_for_port(
    host: str, port: int, timeout: float = 15.0, interval: float = 0.5
) -> bool:
    """Espera hasta que haya algo escuchando en host:port o hasta timeout (segundos)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            # Conectar a localhost donde uvicorn se ha enlazado
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                print(f"[STARTUP] Conexión a 127.0.0.1:{port} establecida.")
                return True
        except Exception:
            time.sleep(interval)
    print(f"[STARTUP][TIMEOUT] No se pudo conectar a 127.0.0.1:{port} en {timeout}s.")
    return False


# ---- Iniciar servidor HTTP y esperar que esté listo ----
uvicorn_thread = start_uvicorn_in_thread()
server_ready = wait_for_port("127.0.0.1", PORT, timeout=20.0)

if not server_ready:
    # Aviso en logs; seguimos intentando arrancar el bot igualmente,
    # pero el health check de Koyeb pudo fallar si esto no quedó a tiempo.
    print(
        "[STARTUP][WARNING] FastAPI no respondió a tiempo; Koyeb puede marcar health check failed."
    )

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


if __name__ == "__main__":
    print("Iniciando bot...")
    asyncio.run(main())
