import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from bot.utils.json_manager import load_json

# Cargar variables del archivo .env (TOKEN, etc.)
load_dotenv()

# Configurar intents para detectar todo tipo de eventos
intents = discord.Intents.all()

# Crear instancia principal del bot con prefijo "/"
bot = commands.Bot(command_prefix="/", intents=intents)


@bot.event
async def on_ready():
    """
    Evento ejecutado cuando el bot se conecta correctamente a Discord.
    Sincroniza comandos de aplicación (slash commands) y muestra estado en consola.
    """
    commands_synced = await bot.tree.sync()
    print(
        f"{len(commands_synced)} comandos sincronizados: \033[93m{', '.join([cmd.name for cmd in commands_synced])}\033[0m."
    )
    print(f"Bot conectado como {bot.user}")


async def load_cogs():
    """
    Carga los módulos (cogs) del bot.
    Aquí se añaden manualmente los que se quieren activar al inicio.
    """
    await bot.load_extension("bot.cogs.voice_cog")
    await bot.load_extension("bot.cogs.commands_cog")
    await bot.load_extension("bot.cogs.misc_cog")


async def main():
    """
    Función principal que gestiona el ciclo de vida del bot.
    Usa 'async with' para asegurar cierre limpio en caso de error o desconexión.
    """
    async with bot:
        await load_cogs()
        await bot.start(os.getenv("TOKEN"))


# Ejecutar solo si este archivo es el punto de entrada
if __name__ == "__main__":
    import asyncio

    print("Iniciando bot...")
    asyncio.run(main())
