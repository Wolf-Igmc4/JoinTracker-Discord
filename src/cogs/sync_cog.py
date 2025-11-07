# src/cogs/sync_cog.py
# Cog para sincronizar datos periódicamente con un servidor FastAPI externo.

from discord.ext import commands, tasks
from discord import app_commands, Interaction
from src.config import RAIZ_PROYECTO
from src.utils.json_manager import load_json
from src.utils.helpers import send_to_fastapi


class SyncCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.flush_task.start()

    def cog_unload(self):
        self.flush_task.cancel()

    @tasks.loop(hours=24)
    async def flush_task(self):
        """Loop automático: cada 24h envía los stats de cada servidor si existen."""
        print("[SyncCog] Ejecutando flush automático de stats por servidor...")
        for guild in self.bot.guilds:
            gid = str(guild.id)
            stats_path = RAIZ_PROYECTO / "data" / gid / "stats.json"
            if stats_path.exists():
                call_data = load_json(f"{gid}/stats.json")
                send_to_fastapi(call_data, guild_id=gid)

    @app_commands.command(
        name="flush",
        description="Envía manualmente las estadísticas locales a la base de datos (solo Anth).",
    )
    async def flush_now(self, interaction: Interaction):
        if interaction.user.id != interaction.client.owner_id:
            await interaction.response.send_message(
                "❌ PILLÍN QUE ME GASTAS LA CUOTA DE LA BASE DE DATOS! Solo el Kitty Owner puede usar este comando (Anth).",
                ephemeral=True,
            )
            return

        sent = 0
        for guild in self.bot.guilds:
            gid = str(guild.id)
            stats_path = RAIZ_PROYECTO / "data" / gid / "stats.json"
            if stats_path.exists():
                call_data = load_json(f"{gid}/stats.json")
                send_to_fastapi(call_data, guild_id=gid)
                sent += 1

        await interaction.response.send_message(
            f"✅ Flush manual completado — {sent} servidor(es) sincronizado(s).",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(SyncCog(bot))
