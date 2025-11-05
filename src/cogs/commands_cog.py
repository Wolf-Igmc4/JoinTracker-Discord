import discord
from discord import app_commands
from discord.ext import commands
from src.utils.json_manager import load_json
from src.utils.helpers import update_json_file
import os


class CommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        # Inicializamos los JSONs vacíos (para update_json)
        self.call_data = {}
        self.time_entries = {}

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
        name="call_stats",
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
        time_entries = load_json(f"{guild.id}/fechas.json")

        user1 = user1 or interaction.user
        user2 = user2 or interaction.user

        u1, u2 = str(user1.id), str(user2.id)

        if u1 == u2:
            await interaction.response.send_message(
                "¡Tonto! No te selecciones a ti mismo o lo dejes en blanco :(\n"
                "Usa `/all_call_stats` si quieres ver tus estadísticas con todos los del server con los que interactuaste."
            )
            return
        # === Datos de veces que se unieron ===
        calls_user1_to_user2 = (
            call_data.get(u2, {}).get(u1, {}).get(f"calls_started_by_{u1}", 0)
        )
        calls_user2_to_user1 = (
            call_data.get(u1, {}).get(u2, {}).get(f"calls_started_by_{u2}", 0)
        )

        # === Datos de tiempo en llamada ===
        total_seconds = 0
        if u1 in time_entries and u2 in time_entries[u1]:
            total_seconds = time_entries[u1][u2].get("total_time", 0)
        elif u2 in time_entries and u1 in time_entries[u2]:
            total_seconds = time_entries[u2][u1].get("total_time", 0)

        # === Mensaje final ===
        msg = (
            f"📞 Estadísticas de llamada entre **{user1.display_name}** y **{user2.display_name}:**\n\n"
            f"🔹 **{user1.display_name} → {user2.display_name}:** {self.fmt_count(calls_user1_to_user2)}\n"
            f"🔹 **{user2.display_name} → {user1.display_name}:** {self.fmt_count(calls_user2_to_user1)}\n"
            f"🕒 Tiempo total compartido en llamada: **{self.fmt_time(total_seconds)}**"
        )

        await interaction.response.send_message(msg)

    @app_commands.command(
        name="all_call_stats",
        description="Muestra estadísticas completas de llamadas de un usuario con tiempos totales.",
    )
    async def all_call_stats(
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        guild = interaction.guild
        call_data = load_json(f"{guild.id}/stats.json")  # stats.json (nuevo)
        time_entries = load_json(f"{guild.id}/fechas.json")  # buffer antiguo

        member = member or interaction.user
        mid = str(member.id)

        appears_as_target = mid in call_data
        appears_as_source = any(mid in inner for inner in call_data.values())

        if not (appears_as_target or appears_as_source):
            await interaction.response.send_message(
                f"No hay datos de llamadas para **{member.display_name}**."
            )
            return

        msg = f"📊 **Estadísticas de llamadas de {member.display_name}:**\n\n"

        # ==== Intentos depresivos primero ====
        if appears_as_target:
            intentos = call_data[mid].get("intentos_depresivos", 0)
            depressive_time = call_data[mid].get("depressive_time", 0)
            msg += f"🔹 **Intentos depresivos:** {intentos}, durante {self.fmt_time(depressive_time)}\n\n"

        # ==== Otros se unieron al usuario ====
        if appears_as_target:
            msg += f"🔹 **Veces que otros se unieron a {member.display_name}:**\n"
            for uid, val in call_data[mid].items():
                if uid in ["intentos_depresivos", "depressive_time"]:
                    continue

                try:
                    user = await self.bot.fetch_user(int(uid))
                except Exception:
                    user = None

                if isinstance(val, dict):
                    count_key = f"calls_started_by_{uid}"
                    val_display = val.get(count_key, 0)
                else:
                    val_display = val

                # <-- aquí: preferimos total_shared_time desde stats (call_data)
                seconds = call_data.get(mid, {}).get(uid, {}).get("total_shared_time")
                # fallback: si no está (datos antiguos) miramos en fechas.json
                if seconds is None:
                    seconds = (
                        time_entries.get(mid, {}).get(uid, {}).get("total_time", 0)
                    )

                name_display = (
                    user.display_name if user else f"[Usuario desconocido {uid}]"
                )
                msg += f"   • {name_display} → {self.fmt_count(val_display)}, {self.fmt_time(seconds)} en total\n"
            msg += "\n"

        # ==== Usuario se unió a otros ====
        if appears_as_source:
            msg += f"🔹 **Veces que {member.display_name} se unió a otros:**\n"
            for target_id, subdict in call_data.items():
                if mid in subdict and target_id not in [
                    "intentos_depresivos",
                    "depressive_time",
                ]:
                    val = subdict[mid]
                    try:
                        user = await self.bot.fetch_user(int(target_id))
                    except Exception:
                        user = None

                    if isinstance(val, dict):
                        count_key = f"calls_started_by_{mid}"
                        val_display = val.get(count_key, 0)
                    else:
                        val_display = val

                    # <-- aquí también: preferimos total_shared_time desde stats (call_data)
                    seconds = (
                        call_data.get(target_id, {})
                        .get(mid, {})
                        .get("total_shared_time")
                    )
                    if seconds is None:
                        seconds = (
                            time_entries.get(mid, {})
                            .get(target_id, {})
                            .get("total_time", 0)
                        )

                    name_display = (
                        user.display_name
                        if user
                        else f"[Usuario desconocido {target_id}]"
                    )
                    msg += f"   • {name_display} → {self.fmt_count(val_display)}, {self.fmt_time(seconds)} en total\n"

        await interaction.response.send_message(msg)

    @app_commands.command(
        name="send_json",
        description="Envía los archivos stats.json y fechas.json del servidor (solo admin).",
    )
    async def send_json(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild  # Diferenciar por servidor

        if not (user.guild_permissions.administrator):
            await interaction.response.send_message(
                "Solo los administradores pueden usar esto por motivos de privacidad.",
                ephemeral=True,
            )
            return

        files = []
        for filename in ["stats.json", "fechas.json"]:
            path = os.path.join(self.data_dir, str(guild.id), filename)
            if os.path.exists(path):
                files.append(discord.File(path))
            else:
                print(f"[WARN] No se encontró {path}")  # Para depurar en consola

        if files:
            await interaction.response.send_message(
                "Te envío los archivos por privado.", ephemeral=True
            )
            try:
                await user.send(files=files)
            except discord.Forbidden:
                await interaction.followup.send(
                    "No pude enviarte los archivos por DM.", ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "No hay archivos de datos para este servidor.", ephemeral=True
            )

    @app_commands.command(
        name="update_json",
        description="Permite actualizar los archivos JSON del bot en este servidor (solo admin).",
    )
    async def updatejson(self, interaction: discord.Interaction):
        user = interaction.user
        if not (user.guild_permissions.administrator):
            await interaction.response.send_message(
                "Solo los administradores pueden usar esto, TONTO.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Iniciando actualización de JSONs. Tienes 60 segundos por cada archivo para enviar los archivos actualizados.",
            ephemeral=True,
        )

        # Diccionario con variables a actualizar
        global_vars = {"stats.json": self.call_data, "fechas.json": self.time_entries}

        for filename in ["stats.json", "fechas.json"]:
            await update_json_file(self.bot, interaction, filename, global_vars)

        await interaction.followup.send(
            "Actualización de JSONs finalizada.", ephemeral=True
        )


# ========= Setup ========= #
async def setup(bot):
    await bot.add_cog(CommandsCog(bot))
