import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from bot.utils.json_manager import load_json

# Cargar variables del archivo .env (TOKEN, etc.)
load_dotenv()

# Configurar intents para detectar todo tipo de eventos (cambiar si es necesario más adelante)
intents = discord.Intents.all()

# Crear instancia principal del bot con prefijo "/"
bot = commands.Bot(command_prefix="/", intents=intents)


@bot.event
async def on_ready():
    """
    Evento ejecutado cuando el bot se conecta correctamente a Discord.
    Sincroniza comandos de aplicación (slash commands) y muestra estado en consola.
    """
    print(f"\n✓ Bot conectado como {bot.user}")
    print(f"✓ ID: {bot.user.id}")
    print(f"✓ Servidores: {len(bot.guilds)}")

    try:
        commands_synced = await bot.tree.sync()
        print(
            f"✓ {len(commands_synced)} comandos sincronizados: \033[93m{', '.join([cmd.name for cmd in commands_synced])}\033[0m."
        )
    except Exception as e:
        print(f"✗ Error sincronizando comandos: {e}")

    print(f"\n{'='*50}")
    print(f"🤖 JoinTracker está listo y funcionando!")
    print(f"{'='*50}\n")


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
            print("Visita https://discord.com/developers/applications")
            print("1. Selecciona tu aplicación")
            print("2. Ve a 'Bot' en el menú lateral")
            print(
                "3. Activa PRESENCE INTENT, SERVER MEMBERS INTENT y MESSAGE CONTENT INTENT"
            )
            raise
        except Exception as e:
            print(f"Error conectando con Discord: {e}")
            import traceback

            traceback.print_exc()
            raise


# Ejecutar solo si este archivo es el punto de entrada
if __name__ == "__main__":
    import asyncio

    print("Iniciando bot...")
    asyncio.run(main())
