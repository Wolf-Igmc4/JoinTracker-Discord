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
            calls_ab = val_ab.get(f"calls_started_by_{b}", 0)
            seconds_ab = val_ab.get("total_shared_time", 0) or 0

        # llamadas b->a
        if isinstance(val_ba, dict):
            calls_ba = val_ba.get(f"calls_started_by_{a}", 0)
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
        calls_user1_to_user2 = stats["calls_ab"]
        calls_user2_to_user1 = stats["calls_ba"]

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
        name="all_call_stats",
        description="Muestra estadísticas completas de llamadas de un usuario con tiempos totales.",
    )
    async def all_call_stats(
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        guild = interaction.guild
        call_data = load_json(f"{guild.id}/stats.json")

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

        # ==== Estadísticas generales (intentos depresivos) ====
        if appears_as_target:
            intentos = call_data[mid].get("intentos_depresivos", 0)
            depressive_time = call_data[mid].get("depressive_time", 0)
            msg += f"🔹 **Estadísticas generales**\n"
            msg += f"   • Intentos depresivos: {intentos}. Ha estado llorando descosoladamente {self.fmt_time(depressive_time)}.\n"

            # ==== Veces totales que se unieron los dos usuarios y el tiempo total ====
            for uid, val in call_data[mid].items():
                if uid in ["intentos_depresivos", "depressive_time"]:
                    continue
                # usamos la función que suma ambos sentidos
                stats = await self._get_bidirectional_stats(call_data, mid, uid)
                user_obj = stats["user_obj"]
                name_display = (
                    user_obj.display_name
                    if user_obj
                    else f"[Usuario desconocido {uid}]"
                )
                msg += f"   • {name_display} → {self.fmt_count(stats['total_calls'])}. 🕒 {self.fmt_time(stats['total_seconds'])}.\n"
            msg += "\n"

        # ==== Otros se unieron al usuario ====
        if appears_as_target:
            msg += f"🔹 **Veces que otros se unieron a {member.display_name}:**\n"
            for uid, _ in call_data[mid].items():
                if uid in ["intentos_depresivos", "depressive_time"]:
                    continue

                stats = await self._get_bidirectional_stats(call_data, mid, uid)
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
            for target_id, _ in call_data.items():
                if mid in call_data.get(target_id, {}) and target_id not in [
                    "intentos_depresivos",
                    "depressive_time",
                ]:
                    stats = await self._get_bidirectional_stats(
                        call_data, mid, target_id
                    )
                    user_obj = stats["user_obj"]
                    name_display = (
                        user_obj.display_name
                        if user_obj
                        else f"[Usuario desconocido {target_id}]"
                    )

                    msg += (
                        f"   • {name_display} → {self.fmt_count(stats['calls_ba'])}.\n"
                    )

        await interaction.response.send_message(msg)

    @app_commands.command(
        name="send_json",
        description="Envía los archivos stats.json y fechas.json del servidor (solo admin).",
    )
    async def send_json(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild

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
                print(f"[WARN] No se encontró {path}")

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
        description="Permite actualizar `stats.json` del bot en este servidor (solo admin).",
    )
    async def update_json(self, interaction: discord.Interaction):
        user = interaction.user
        if not user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Solo los administradores pueden usar esto.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Iniciando actualización de `stats.json`. Tienes 60 segundos para enviar el archivo actualizado.",
            ephemeral=True,
        )

        # Diccionario con la variable a actualizar
        global_vars = {"stats.json": self.call_data}

        await update_json_file(self.bot, interaction, "stats.json", global_vars)

        await interaction.followup.send(
            "Actualización de `stats.json` finalizada.", ephemeral=True
        )


# ========= Setup ========= #
async def setup(bot):
    await bot.add_cog(CommandsCog(bot))
