import discord
from discord import app_commands
from discord.ext import commands
from src.utils.json_manager import load_json
from src.utils.helpers import update_json_file
import os
from datetime import datetime
from src.config import RAIZ_PROYECTO


class CommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_dir = RAIZ_PROYECTO / "data"

        # Inicializamos los JSONs vacíos (para update_json)
        self.call_data = {}

    async def _get_bidirectional_stats(self, call_data: dict, a: str, b: str):
        """
        Devuelve un dict con:
        - calls_ab: llamadas iniciadas por a hacia b
        - calls_ba: llamadas iniciadas por b hacia a
        - total_calls: suma bidireccional
        - seconds_ab: tiempo compartido registrado a->b
        - seconds_ba: tiempo compartido registrado b->a
        - total_seconds: suma de segundos (0 si no existe)
        - user_obj: objeto discord.User de b (o None si no se puede obtener)
        Los parámetros a y b pueden ser ints o strings; se usan como claves str en call_data.
        """
        a, b = str(a), str(b)

        if a == b:
            return "same_user"
        if a not in call_data or b not in call_data:
            return None

        val_ab = call_data.get(a, {}).get(b, None)  # info que guarda a sobre b
        val_ba = call_data.get(b, {}).get(a, None)  # info que guarda b sobre a

        # llamadas a->b
        if isinstance(val_ab, dict):
            calls_ab = val_ab.get(f"calls_started", 0)
            seconds_ab = val_ab.get("total_shared_time", 0) or 0

        # llamadas b->a
        if isinstance(val_ba, dict):
            calls_ba = val_ba.get(f"calls_started", 0)
            seconds_ba = val_ba.get("total_shared_time", 0) or 0

        total_calls = calls_ab + calls_ba
        total_seconds = seconds_ab or seconds_ba

        # obtenemos usuario b (para mostrar nombre)
        try:
            user_obj = await self.bot.fetch_user(int(b))
        except Exception:
            user_obj = None

        return {
            "calls_ab": calls_ab,
            "calls_ba": calls_ba,
            "total_calls": total_calls,
            "total_seconds": total_seconds,
            "user_obj": user_obj,
        }

    # ===== Funciones auxiliares ===== #
    @staticmethod
    def fmt_time(seconds):
        if seconds < 60:
            return f"{round(seconds)} segundos"
        minutes = seconds / 60
        if minutes < 60:
            return f"{round(minutes, 2)} minutos"
        return f"{round(minutes / 60, 2)} horas"

    @staticmethod
    def fmt_count(n):
        return f"{n} vez" if n == 1 else f"{n} veces"

    # ====== Slash Commands ====== #
    @app_commands.command(
        name="datos_llamada",
        description="Devuelve las veces y el tiempo total que un usuario ha estado en llamada con otro.",
    )
    async def call_stats(
        self,
        interaction,  # sin anotación explícita
        user1: discord.Member = None,
        user2: discord.Member = None,
    ):
        guild = interaction.guild
        call_data = load_json(f"{guild.id}/stats.json")

        user1 = user1 or interaction.user
        user2 = user2 or interaction.user

        u1, u2 = str(user1.id), str(user2.id)
        stats = await self._get_bidirectional_stats(call_data, u1, u2)
        if stats == "same_user":
            await interaction.response.send_message(
                "¡Tonto! No te selecciones a ti mismo o lo dejes en blanco, QUE EXPLOTO! :(\n"
                "Usa `/all_call_stats` si quieres ver tus estadísticas con todos los del server con los que interactuaste."
            )
            return
        if stats is None:
            await interaction.response.send_message(
                f"No hay datos de llamadas entre **{user1.display_name}** y **{user2.display_name}**."
            )
            return
        # === Datos de veces que se unieron ===
        calls_user1_to_user2 = stats["calls_ba"]
        calls_user2_to_user1 = stats["calls_ab"]

        # === Datos de tiempo en llamada ===
        total_seconds = stats["total_seconds"]

        # === Mensaje final ===
        msg = (
            f"📞 Estadísticas de llamada entre **{user1.display_name}** y **{user2.display_name}:**\n\n"
            f"🔹 **{user1.display_name} → {user2.display_name}:** {self.fmt_count(calls_user1_to_user2)}\n"
            f"🔹 **{user2.display_name} → {user1.display_name}:** {self.fmt_count(calls_user2_to_user1)}\n"
            f"🕒 **Tiempo total compartido en llamada:** {self.fmt_time(total_seconds)}"
        )

        await interaction.response.send_message(msg)

    @app_commands.command(
        name="datos_totales_llamada",
        description="Muestra estadísticas completas de llamadas de un usuario con tiempos totales.",
    )
    async def all_call_stats(
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        await interaction.response.defer()  # Da más tiempo al bot

        guild = interaction.guild
        call_data = load_json(f"{guild.id}/stats.json")

        member = member or interaction.user
        mid = str(member.id)

        appears_as_target = mid in call_data
        appears_as_source = any(mid in inner for inner in call_data.values())

        if not (appears_as_target or appears_as_source):
            await interaction.followup.send(
                f"No hay datos de llamadas para **{member.display_name}**."
            )
            return

        msg = f"📊 **Estadísticas de llamadas de {member.display_name}:**\n"

        # ====== Preparar usuarios a procesar ======
        uids_to_process = set()
        if appears_as_target:
            uids_to_process.update(
                uid
                for uid in call_data[mid]
                if uid not in ["depressive_attempts", "depressive_time"]
            )
        if appears_as_source:
            for target_id, inner in call_data.items():
                if mid in inner and target_id not in [
                    "depressive_attempts",
                    "depressive_time",
                ]:
                    uids_to_process.add(target_id)
        uids_to_process = list(uids_to_process)

        # ====== Obtener estadísticas secuencialmente ======
        stats_cache = {}
        for uid in uids_to_process:
            stats_cache[uid] = await self._get_bidirectional_stats(call_data, mid, uid)

        # ==== Estadísticas generales ====
        if appears_as_target:
            depressive_attempts = call_data[mid].get("depressive_attempts", 0)
            depressive_time = call_data[mid].get("depressive_time", 0)
            if depressive_attempts:
                msg += f"🔹 **Estadísticas generales**\n"
                msg += f"   • Intentos depresivos: {depressive_attempts}. Ha estado llorando desconsoladamente {self.fmt_time(depressive_time)}.\n"
            msg += "\n   **Veces y tiempo total compartido con otros usuarios:**\n"
            for uid in call_data[mid]:
                if uid in ["depressive_attempts", "depressive_time"]:
                    continue
                stats = stats_cache[uid]
                user_obj = stats["user_obj"]
                name_display = (
                    user_obj.display_name
                    if user_obj
                    else f"[Usuario desconocido {uid}]"
                )
                msg += f"   • {name_display} → {self.fmt_count(stats['total_calls'])}. Tiempo juntos: 🕒 {self.fmt_time(stats['total_seconds'])}.\n"
            msg += "\n"

        # ==== Otros se unieron al usuario ====
        if appears_as_target:
            msg += f"🔹 **Veces que otros se unieron a {member.display_name}:**\n"
            for uid in call_data[mid]:
                if uid in ["depressive_attempts", "depressive_time"]:
                    continue
                stats = stats_cache[uid]
                user_obj = stats["user_obj"]
                name_display = (
                    user_obj.display_name
                    if user_obj
                    else f"[Usuario desconocido {uid}]"
                )
                msg += f"   • {name_display} → {self.fmt_count(stats['calls_ab'])}.\n"
            msg += "\n"

        # ==== Usuario se unió a otros ====
        if appears_as_source:
            msg += f"🔹 **Veces que {member.display_name} se unió a otros:**\n"
            for target_id, inner in call_data.items():
                if mid in inner and target_id not in [
                    "depressive_attempts",
                    "depressive_time",
                ]:
                    stats = stats_cache[target_id]
                    user_obj = stats["user_obj"]
                    name_display = (
                        user_obj.display_name
                        if user_obj
                        else f"[Usuario desconocido {target_id}]"
                    )
                    msg += (
                        f"   • {name_display} → {self.fmt_count(stats['calls_ba'])}.\n"
                    )

        await interaction.followup.send(msg)

    @app_commands.command(
        name="descargar_json",
        description="Envía los archivos stats.json y dates.json del servidor (solo admin).",
    )
    async def download_json(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild

        if not (user.guild_permissions.administrator):
            await interaction.response.send_message(
                "Solo los administradores pueden usar esto por motivos de privacidad.",
                ephemeral=True,
            )
            return

        files = []
        for filename in ["stats.json", "dates.json"]:
            path = os.path.join(self.data_dir, str(guild.id), filename)
            if os.path.exists(path):
                files.append(discord.File(path))
            else:
                print(f"[WARN] No se encontró {path}")

        if files:
            await interaction.response.send_message(
                "Te envío los archivos por privado.", ephemeral=True
            )
            try:
                print(f"[DEBUG] Enviando archivos por DM a {user.display_name}...")
                await user.send(
                    content=f"Aquí tienes los archivos de datos del servidor {guild.name}, a fecha de {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}:",
                    files=files,
                )

            except discord.Forbidden:
                print("[ERROR] No pude enviar los archivos por DM (Forbidden).")
                await interaction.followup.send(
                    "No pude enviarte los archivos por DM.", ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "No hay archivos de datos para este servidor.", ephemeral=True
            )

    @app_commands.command(
        name="actualizar_json",
        description="Permite actualizar los archivos de estadísticas del bot en este servidor (solo admin).",
    )
    async def update_json(self, interaction: discord.Interaction):
        user = interaction.user
        if not user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Solo los administradores pueden usar esto.", ephemeral=True
            )
            return
        # Indicamos que vamos a procesar la interacción y tardará un poco
        await interaction.response.defer(ephemeral=False)

        await interaction.followup.send(
            f"Actualización de base de datos local iniciada.",
            ephemeral=False,
        )
        global_vars = {"stats.json": self.call_data}

        for filename in ["stats.json", "dates.json"]:
            await update_json_file(self.bot, interaction, filename, global_vars)

        await interaction.followup.send(
            "Actualización de base de datos local finalizada.", ephemeral=False
        )


# ========= Setup ========= #
async def setup(bot):
    await bot.add_cog(CommandsCog(bot))
