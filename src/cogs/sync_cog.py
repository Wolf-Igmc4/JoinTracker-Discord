# src/cogs/sync_cog.py
# Cog para sincronizar datos periódicamente con un servidor FastAPI externo.

import asyncio
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from discord import app_commands, Interaction
from src.config import RAIZ_PROYECTO
from src.utils.data_handler import load_json
from src.utils.helpers import get_data_path, send_to_fastapi, sync_all_guilds


class SyncCog(commands.Cog):
    """Cog para manejar sincronización periódica de stats con FastAPI."""

    def __init__(self, bot):
        self.bot = bot
        self.next_flush_at = None  # Marca del próximo flush
        self.flush_task.start()
        self.flush_eta.start()

    def cog_unload(self):
        """Cancela los loops cuando se descarga el cog."""
        if self.flush_task.is_running():
            self.flush_task.cancel()
        if self.flush_eta.is_running():
            self.flush_eta.cancel()

    @tasks.loop(hours=48)
    async def flush_task(self):
        """Loop automático: cada 48h envía los stats de cada servidor si existen."""
        print("Iniciada copia de seguridad.")
        for guild in self.bot.guilds:
            print(
                f"\033[33m[SyncCog] Ejecutando volcado automático de stats para servidor {guild}...\033[0m"
            )
            gid = str(guild.id)
            stats_path = RAIZ_PROYECTO / "data" / gid / "stats.json"
            if stats_path.exists():
                call_data = load_json(get_data_path(gid, "stats.json"))
                await send_to_fastapi(call_data, guild_id=guild)

        self.next_flush_at = datetime.utcnow() + timedelta(hours=48)

    @flush_task.before_loop
    async def before_flush_task(self):
        """Espera a que el bot esté listo antes de iniciar el loop de 48h y fija next_flush_at."""
        await self.bot.wait_until_ready()
        self.next_flush_at = datetime.utcnow() + timedelta(hours=48)
        await asyncio.sleep(48 * 3600)  # Espera 48h antes del primer envío

    @tasks.loop(hours=6)
    async def flush_eta(self):
        """Cada 6h muestra cuánto tiempo falta para el próximo flush automático."""
        if self.next_flush_at is None:
            await asyncio.sleep(0.1)
            if self.next_flush_at is None:
                return

        now = datetime.utcnow()
        hours = (self.next_flush_at - now).total_seconds() / 3600

        if hours <= 0:
            print(
                "\033[33m⏳ Queda menos de 1 hora para el próximo volcado automático (o está en curso).\033[0m"
            )
        else:
            h = int(round(hours))
            print(
                f"\033[33m⏳ Quedan {h} horas para el próximo volcado automático.\n"
                f"   Hora de mensaje: {now:%Y-%m-%d %H:%M:%S UTC}\n"
                f"   Hora programada: {self.next_flush_at:%Y-%m-%d %H:%M:%S UTC}\033[0m"
            )

    @flush_eta.before_loop
    async def before_flush_eta(self):
        """Espera a que el bot esté listo y a que next_flush_at esté inicializado."""
        await self.bot.wait_until_ready()
        while self.next_flush_at is None:
            await asyncio.sleep(0.1)

    @app_commands.command(
        name="volcado_db",
        description="Envía manualmente las estadísticas locales a la base de datos (solo Anth).",
    )
    async def flush_now(self, interaction: Interaction):
        """Comando para realizar un flush manual de stats a FastAPI del servidor donde se ejecute."""
        if interaction.user.id != interaction.client.owner_id:
            await interaction.response.send_message(
                "❌ PILLÍN QUE ME GASTAS LA CUOTA DE LA BASE DE DATOS! Solo el Kitty Owner puede usar este comando (Anth).",
                ephemeral=True,
            )
            return

        print("Volcado de bases de datos llamada.")
        await interaction.response.defer(ephemeral=True)

        sent = await sync_all_guilds(self.bot, force=True)

        msg = f"✅ Volcado manual completado — Servidores sincronizados: {sent}."

        await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SyncCog(bot))
