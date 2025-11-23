# src/cogs/commands_cog.py

import discord
from discord import app_commands
from discord.ext import commands
from src.utils.data_handler import load_json
from src.utils.helpers import get_data_path, update_json_file
import os
from datetime import datetime
from src.config import RAIZ_PROYECTO
from src.utils.ui_components import UserStatsPaginator, generate_settings_interface


class CommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_dir = RAIZ_PROYECTO / "data"
        self.call_data = {}

    async def _get_bidirectional_stats(
        self, call_data: dict, a: str, b: str, guild: discord.Guild = None
    ):
        """
        Recupera estadísticas y el OBJETO DE MIEMBRO DEL SERVIDOR (para que salga el apodo).
        """
        a, b = str(a), str(b)

        if a == b:
            return "same_user"
        if a not in call_data or b not in call_data:
            return None

        val_ab = call_data.get(a, {}).get(b, None)
        val_ba = call_data.get(b, {}).get(a, None)

        if isinstance(val_ab, dict):
            calls_ab = val_ab.get(f"calls_started", 0)
            seconds_ab = val_ab.get("total_shared_time", 0) or 0
        else:
            calls_ab, seconds_ab = 0, 0  # Inicializar si no existe

        if isinstance(val_ba, dict):
            calls_ba = val_ba.get(f"calls_started", 0)
            seconds_ba = val_ba.get("total_shared_time", 0) or 0
        else:
            calls_ba, seconds_ba = 0, 0  # Inicializar si no existe

        total_calls = calls_ab + calls_ba
        total_seconds = seconds_ab or seconds_ba

        user_obj = None
        if guild:
            # Primero intentamos obtenerlo del servidor (tiene apodo)
            user_obj = guild.get_member(int(b))

            # Si no está en caché (get_member devuelve None), intentamos fetch (más lento pero seguro)
            if user_obj is None:
                try:
                    user_obj = await guild.fetch_member(int(b))
                except discord.NotFound:
                    pass  # El usuario ya no está en el servidor

        # Si falla (ej. usuario se fue del server), usamos el global (fetch_user)
        if user_obj is None:
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

    # ===== Funciones auxiliares de formato =====
    @staticmethod
    def fmt_time(seconds):
        """Formatea segundos a una cadena legible (segundos, minutos u horas)."""
        if seconds < 60:
            return f"{round(seconds)} segundos"
        minutes = seconds / 60
        if minutes < 60:
            return f"{round(minutes, 2)} minutos"
        return f"{round(minutes / 60, 2)} horas"

    @staticmethod
    def fmt_count(n):
        """Pluralización básica para contadores."""
        return f"{n} vez" if n == 1 else f"{n} veces"

    # ====== Comandos de barra ====== #
    @app_commands.command(
        name="datos_llamada",
        description="Devuelve las veces y el tiempo total que un usuario ha estado en llamada con otro.",
    )
    async def call_stats(
        self,
        interaction: discord.Interaction,
        user1: discord.Member = None,
        user2: discord.Member = None,
    ):
        guild = interaction.guild
        call_data = load_json(get_data_path(guild, "stats.json"))

        user1 = user1 or interaction.user
        user2 = user2 or interaction.user

        u1, u2 = str(user1.id), str(user2.id)
        stats = await self._get_bidirectional_stats(call_data, u1, u2, guild=guild)

        if stats == "same_user":
            await interaction.response.send_message(
                "¡Tonto! No te selecciones a ti mismo o lo dejes en blanco, QUE EXPLOTO! :(\n"
                "Usa `/datos_totales_llamada` si quieres ver tus estadísticas con todos los del server con los que interactuaste.",
                ephemeral=True,
            )
            return

        if stats is None:
            embed_error = discord.Embed(
                title=f"❌ No existen registros entre **{user1.display_name}** y **{user2.display_name}**.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        # Datos
        calls_u1_to_u2 = stats["calls_ba"]
        calls_u2_to_u1 = stats["calls_ab"]
        total_seconds = stats["total_seconds"]
        total_calls = calls_u1_to_u2 + calls_u2_to_u1
        time_str = self.fmt_time(total_seconds)

        # --- EMBED DISEÑO LISTA ---
        embed = discord.Embed(
            title="📊 Reporte de interacciones",
            color=discord.Color.gold(),
        )

        # 1. THUMBNAIL (Arriba derecha): User 2
        embed.set_thumbnail(url=user2.display_avatar.url)

        # 2. FOOTER (Abajo izquierda): User 1
        # Ponemos su nombre en el texto para que se sepa de quién es la foto
        embed.set_footer(
            text=f"{user1.display_name}", icon_url=user1.display_avatar.url
        )

        # Lista de datos tal cual la pediste
        embed.description = (
            f"🔶  **Estadísticas entre {user1.display_name} y {user2.display_name}:**\n\n"
            f"• **Tiempo compartido en llamada:** `{time_str}`\n"
            f"• **Llamadas totales:** {total_calls}\n"
            f"• **Veces que {user1.display_name} se unió a {user2.display_name}:** {calls_u1_to_u2}\n"
            f"• **Veces que {user2.display_name} se unió a {user1.display_name}:** {calls_u2_to_u1}"
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="datos_totales_llamada",
        description="Muestra estadísticas completas de llamadas de un usuario con tiempos totales.",
    )
    async def all_call_stats(
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        await interaction.response.defer()

        guild = interaction.guild
        call_data = load_json(get_data_path(guild, "stats.json"))

        member = member or interaction.user
        mid = str(member.id)

        # --- 1. Obtener Estadísticas Generales (NUEVO) ---
        my_data = call_data.get(mid, {})
        solo_time = my_data.get("total_solo_time", 0)
        dep_attempts = my_data.get("depressive_attempts", 0)
        dep_time = my_data.get(
            "depressive_time", 0
        )  # Tiempo total de intentos depresivos

        has_incoming = bool(my_data)
        has_outgoing = any(mid in inner for inner in call_data.values())

        # El comando ahora falla solo si no hay *ningún* dato
        if not (has_incoming or has_outgoing) and not (
            solo_time > 0 or dep_attempts > 0
        ):
            return await interaction.followup.send(
                f"No hay datos de llamada para **{member.display_name}**."
            )

        # --- 2. Recolección y Procesamiento de datos de Interacción (Mismo código) ---
        internal_keys = [
            "depressive_attempts",
            "depressive_time",
            "total_solo_time",
            "opt_out_logs",
        ]
        uids_incoming = {k for k in my_data.keys() if k not in internal_keys}
        uids_outgoing = {
            k for k, v in call_data.items() if mid in v and k not in internal_keys
        }
        all_uids = list(uids_incoming | uids_outgoing)

        stats_list = []
        for uid in all_uids:
            stats = await self._get_bidirectional_stats(
                call_data, mid, uid, guild=guild
            )
            if not stats:
                continue
            user_obj = stats.get("user_obj")
            name = user_obj.display_name if user_obj else f"Usuario ID: {uid}"

            stats_entry = {
                "name": name,
                "total_seconds": stats.get("total_seconds", 0),
                "total_calls": stats.get("total_calls", 0),
                "calls_in": stats.get("calls_ab", 0),
                "calls_out": stats.get("calls_ba", 0),
            }
            stats_list.append(stats_entry)

        stats_list.sort(key=lambda x: x["total_seconds"], reverse=True)

        # --- 3. RESPUESTA VISUAL (ACTUALIZADO: Pasando los nuevos datos) ---
        view = UserStatsPaginator(
            stats_list,
            member.display_name,
            solo_time=solo_time,
            dep_attempts=dep_attempts,
            dep_time=dep_time,
        )
        embed, _ = view.get_page_content()

        await interaction.followup.send(embed=embed, view=view)
        view.message = await interaction.original_response()

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
        # Nota: Aquí mantenemos os.path.join porque necesitamos la ruta absoluta para discord.File
        # get_data_path devuelve ruta relativa, usamos os.path.join para absoluta/sistema.
        for filename in ["stats.json", "dates.json"]:
            path = os.path.join(self.data_dir, str(guild.id), filename)

            if os.path.exists(path):
                files.append(discord.File(path))
            else:
                print(f"[WARN] No se encontró {path}.")

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

        # Proceso asíncrono potencialmente lento, deferimos la respuesta
        await interaction.response.defer(ephemeral=False)

        await interaction.followup.send(
            f"Actualización de base de datos local iniciada.",
            ephemeral=False,
        )

        # Variable global para inyección dinámica (si es requerida por update_json_file)
        global_vars = {"stats.json": self.call_data}

        for filename in ["stats.json", "dates.json"]:
            await update_json_file(self.bot, interaction, filename, global_vars)

        await interaction.followup.send(
            "Actualización de base de datos local finalizada.", ephemeral=False
        )

    @app_commands.command(
        name="ajustes", description="Configura si se guardan tus datos."
    )
    async def settings(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        guild_id = interaction.guild.id

        # Generamos la UI inicial centralizada, delegando la lógica visual
        embed, view = generate_settings_interface(guild_id, user_id)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

        # Vinculación del mensaje a la vista para gestión del ciclo de vida (timeout)
        view.message = await interaction.original_response()


# ========= Setup ========= #
async def setup(bot: commands.Bot):
    await bot.add_cog(CommandsCog(bot))
