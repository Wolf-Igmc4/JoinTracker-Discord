# src/cogs/sync_cog.py
# Cog para sincronizar datos periódicamente con un servidor FastAPI externo.

from discord.ext import commands, tasks
import os

from src.utils.json_manager import load_json
from src.utils.helpers import _send_to_fastapi


class SyncCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.flush_task.start()

    def cog_unload(self):
        self.flush_task.cancel()

    @tasks.loop(seconds=60)
    async def flush_task(self):
        for guild in self.bot.guilds:
            gid = str(guild.id)

            datos_path = os.path.join("bot", "data", gid, "stats.json")
            fechas_path = os.path.join("bot", "data", gid, "fechas.json")

            if os.path.exists(datos_path):
                call_data = load_json(f"{gid}/stats.json")
                _send_to_fastapi(call_data, guild_id=gid)

            if os.path.exists(fechas_path):
                time_entries = load_json(f"{gid}/fechas.json")
                _send_to_fastapi(time_entries, guild_id=gid)


async def setup(bot):
    await bot.add_cog(SyncCog(bot))
