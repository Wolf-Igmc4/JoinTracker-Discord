# src/cogs/sync_cog.py
# Cog para sincronizar datos periódicamente con un servidor FastAPI externo.

from discord.ext import commands, tasks
from discord import app_commands, Interaction
from pathlib import Path
from typing import Callable, Awaitable
from src.config import RAIZ_PROYECTO
from src.utils.json_manager import load_json
from src.utils.helpers import send_to_fastapi


def owner_check() -> Callable[[Interaction], Awaitable[bool]]:
    """
    Devuelve un app_commands.check que verifica si el autor es owner del bot.
    Uso recomendado: @owner_check()
    """

    async def predicate(interaction: Interaction) -> bool:
        # client.is_owner espera un objeto usuario; retorna True si es owner del bot
        return await interaction.client.is_owner(interaction.user)

    return app_commands.check(predicate)


class SyncCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.flush_task.start()

    def cog_unload(self):
        self.flush_task.cancel()

    @tasks.loop(hours=24)
    async def flush_task(self):
        """Loop automático: cada 24h envía los stats de cada guild si existen."""
        for guild in self.bot.guilds:
            gid = str(guild.id)
            stats_path: Path = RAIZ_PROYECTO / "data" / gid / "stats.json"

            if stats_path.exists():
                call_data = load_json(f"{gid}/stats.json")
                print(
                    "Creando copia de seguridad y enviando datos para servidor: ", gid
                )
                send_to_fastapi(call_data, guild_id=gid)

    # comando slash manual /flush — solo owner puede usarlo
    @app_commands.command(
        name="flush", description="Forzar envío manual inmediato a la base de datos."
    )
    @owner_check()
    async def flush_now(self, interaction: Interaction):
        """Comando manual para forzar subida manual (misma lógica que el loop)."""
        sent = 0
        for guild in self.bot.guilds:
            gid = str(guild.id)
            stats_path: Path = RAIZ_PROYECTO / "data" / gid / "stats.json"

            if stats_path.exists():
                call_data = load_json(f"{gid}/stats.json")
                print("[DEBUG][FLUSH_NOW] type(gid):", type(gid), "gid:", gid)
                send_to_fastapi(call_data, guild_id=gid)
                sent += 1

        await interaction.response.send_message(
            f"✅ Flush manual completado — {sent} servidor(es) sincronizado(s).",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(SyncCog(bot))
