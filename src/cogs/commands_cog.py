# src/cogs/commands_cog.py

import discord
from discord import app_commands
from discord.ext import commands
from src.utils.data_handler import load_json, save_json
from src.utils.helpers import get_data_path, update_json_file
import os
from datetime import datetime
from src.config import RAIZ_PROYECTO


# --- FUNCIÓN AUXILIAR DE INTERFAZ ---
def generate_settings_interface(
    guild_id: int, user_id: str, specific_status_msg: str = None
):
    """
    Genera el Embed y la Vista de configuración basados en el estado actual del usuario.
    Centraliza la lógica visual para evitar duplicidad de código en los comandos y callbacks.

    Args:
        guild_id (int): ID del servidor.
        user_id (str): ID del usuario.
        specific_status_msg (str, optional): Texto personalizado para el estado. Si es None, se usa el estado del JSON.

    Returns:
        tuple[discord.Embed, discord.ui.View]: El embed y la vista listos para enviar.
    """
    path_stats = get_data_path(guild_id, "stats.json")
    data = load_json(path_stats)

    # Recuperación del estado de persistencia del usuario
    user_data = data.get(user_id, {})
    is_opt_out = user_data.get("opt_out_logs", False)
    tracking_active = not is_opt_out

    # Construcción del texto de estado
    if specific_status_msg:
        status_text = specific_status_msg
    else:
        status_text = "✅ Activo" if tracking_active else "❌ Inactivo"

    # Generación del Embed informativo
    embed = discord.Embed(
        title="⚙️ Configuración",
        description=f"**Seguimiento:** ***{status_text}***\n"
        f"\nℹ️ *Si desactivas el seguimiento, tus tiempos en llamada no se registrarán. "
        f"No se verán afectadas las estadísticas guardadas previamente.*",
        color=discord.Color.blue(),
    )

    # Generación de la Vista con los controles
    view = ToggleSettingsView(user_id, tracking_active, guild_id)

    return embed, view


class ConfirmDeleteView(discord.ui.View):
    """
    Vista de confirmación para la eliminación de datos.
    Tiene un tiempo de vida corto (30s) por seguridad.
    """

    def __init__(self, user_id: str, guild_id: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.guild_id = guild_id
        self.message = None  # Referencia al mensaje para editarlo al expirar el tiempo

    async def on_timeout(self):
        """Se ejecuta automáticamente tras 30s de inactividad."""
        # Deshabilitar visualmente todos los componentes
        for child in self.children:
            child.disabled = True

        if self.message:
            try:
                await self.message.edit(
                    content="⌛ **Tiempo de espera agotado. Operación cancelada.**",
                    view=self,
                )
            except Exception:
                pass

    @discord.ui.button(label="Sí, borrar todo", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Verificación de propietario
        if str(interaction.user.id) != self.user_id:
            return

        await interaction.response.defer(ephemeral=False)

        mid = self.user_id
        files_to_clean = ["stats.json", "dates.json"]

        # Proceso de limpieza en todos los archivos de datos relevantes
        for filename in files_to_clean:
            try:
                path = get_data_path(self.guild_id, filename)
                data = load_json(path)

                # 1. Limpieza profunda: Eliminar referencias del usuario en registros de terceros
                for other_user_id, other_user_data in data.items():
                    if other_user_id == mid:
                        continue
                    if isinstance(other_user_data, dict) and mid in other_user_data:
                        del other_user_data[mid]

                # 2. Auto-eliminación: Borrar la entrada principal del usuario
                if mid in data:
                    del data[mid]

                # 3. Persistencia: Mantener la preferencia de Opt-out explícita para evitar seguimiento futuro.
                if filename == "stats.json":
                    data[mid] = {"opt_out_logs": True}

                save_json(path, data)
            except Exception as e:
                print(f"[ERROR ConfirmDelete] {e}")

        print(
            f"[INFO] El usuario {interaction.user.name} ({self.user_id}) ha BORRADO su historial en el servidor {interaction.guild.name} ({self.guild_id})."
        )

        # Generación del feedback visual final (Sin botones, para cerrar el ciclo)
        new_embed = discord.Embed(
            title="⚙️ Configuración",
            description=f"**Seguimiento:** ***❌ Inactivo (Datos borrados)***\n"
            f"\nℹ️ *Tu historial ha sido eliminado y el seguimiento desactivado permanentemente.*",
            color=discord.Color.blue(),
        )

        # Editamos el mensaje eliminando la vista (view=None) para que no salgan botones
        await interaction.edit_original_response(
            content="✅ **Historial eliminado correctamente.**",
            embed=new_embed,
            view=None,
        )

        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            return
        await interaction.response.edit_message(
            content="Operación cancelada.", view=None, embed=None
        )
        self.stop()


class ToggleSettingsView(discord.ui.View):
    """
    Vista principal de configuración.
    Permite alternar el estado de seguimiento y acceder al borrado.
    """

    def __init__(self, user_id: str, logs_activados: bool, guild_id: int):
        super().__init__(timeout=300)  # Timeout extendido (5 min) para mejor UX
        self.user_id = user_id
        self.logs_activados = logs_activados
        self.guild_id = guild_id
        self.message = None

        # Configuración dinámica del texto del menú según el estado actual
        if self.logs_activados:
            etiqueta = "Desactivar seguimiento"
            valor = "desactivar"
            emoji = "🔴"
            descripcion = "Dejar de guardar tus estadísticas en llamada."
        else:
            etiqueta = "Activar seguimiento"
            valor = "activar"
            emoji = "🟢"
            descripcion = "Guarda todas tus estadísticas en llamada."

        select_menu = discord.ui.Select(
            placeholder="Pulsa aquí para cambiar tu configuración...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=etiqueta, value=valor, description=descripcion, emoji=emoji
                )
            ],
        )
        select_menu.callback = self.menu_callback
        self.add_item(select_menu)

        delete_btn = discord.ui.Button(
            label="Borrar historial de interacciones",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            row=1,
        )
        delete_btn.callback = self.callback_delete
        self.add_item(delete_btn)

    async def on_timeout(self):
        """Gestión de recursos: Se ejecuta tras 5 min de inactividad."""
        for child in self.children:
            child.disabled = True

        if self.message:
            try:
                # Preservamos el embed original, solo indicamos la expiración
                fresh_embed, _ = generate_settings_interface(
                    self.guild_id, self.user_id
                )
                await self.message.edit(
                    content="⌛ **Sesión caducada.** Usa el comando de nuevo si quieres modificar tu configuración.",
                    embed=fresh_embed,
                    view=self,
                )
            except Exception:
                pass

    async def menu_callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "No toques lo de otros guarrilla.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            eleccion = interaction.data["values"][0]
            path_stats = get_data_path(self.guild_id, "stats.json")
            data = load_json(path_stats)

            if self.user_id not in data:
                data[self.user_id] = {}

            # Actualización del estado en JSON
            if eleccion == "activar":
                data[self.user_id]["opt_out_logs"] = False
                new_status = True
            else:
                data[self.user_id]["opt_out_logs"] = True
                new_status = False

            save_json(path_stats, data)

            print(
                f"[INFO] El usuario {interaction.user.name} ({self.user_id}) cambió su configuración de seguimiento a {'Activo' if new_status else 'Inactivo'} en el servidor {interaction.guild.name} ({self.guild_id})."
            )

            # Regeneración de la interfaz completa llamando al helper (DRY)
            embed, view = generate_settings_interface(self.guild_id, self.user_id)

            await interaction.edit_original_response(
                content=None, embed=embed, view=view
            )

            # Reiniciamos el ciclo de vida vinculando el mensaje a la nueva vista
            view.message = await interaction.original_response()

        except Exception as e:
            print(f"[ERROR Settings] {e}")
            await interaction.followup.send(
                "Error al guardar preferencia.", ephemeral=True
            )

    async def callback_delete(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "No toques lo de otros guarrilla.", ephemeral=True
            )
            return

        # Iniciamos la vista de confirmación intermedia
        view_confirm = ConfirmDeleteView(self.user_id, self.guild_id)

        await interaction.response.send_message(
            "⚠️ **¿Estás seguro de que quieres borrar todo tu historial?**\n\n"
            "• Se eliminarán tus tiempos totales, tanto solo como depresivo.\n"
            "• Se eliminará tu rastro en las estadísticas de otros usuarios.\n"
            "• Esta acción **no se puede deshacer**.",
            view=view_confirm,
            ephemeral=False,
        )

        # Vinculación de mensaje necesaria para el timeout
        view_confirm.message = await interaction.original_response()


class CommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_dir = RAIZ_PROYECTO / "data"
        self.call_data = {}

    async def _get_bidirectional_stats(self, call_data: dict, a: str, b: str):
        """
        Recupera y agrega estadísticas bidireccionales entre dos usuarios (a y b).

        Retorna un diccionario con:
        - calls_ab: llamadas iniciadas por a hacia b
        - calls_ba: llamadas iniciadas por b hacia a
        - total_calls: suma total de interacciones
        - total_seconds: tiempo total compartido (asumiendo simetría o suma)
        - user_obj: objeto discord.User de b (para visualización)
        """
        a, b = str(a), str(b)

        if a == b:
            return "same_user"
        if a not in call_data or b not in call_data:
            return None

        # Obtener sub-diccionarios de interacción mutua
        val_ab = call_data.get(a, {}).get(b, None)
        val_ba = call_data.get(b, {}).get(a, None)

        # Extracción segura de datos A -> B
        if isinstance(val_ab, dict):
            calls_ab = val_ab.get(f"calls_started", 0)
            seconds_ab = val_ab.get("total_shared_time", 0) or 0

        # Extracción segura de datos B -> A
        if isinstance(val_ba, dict):
            calls_ba = val_ba.get(f"calls_started", 0)
            seconds_ba = val_ba.get("total_shared_time", 0) or 0

        total_calls = calls_ab + calls_ba
        total_seconds = seconds_ab or seconds_ba

        # Intentar resolver el objeto usuario para obtener el nombre actualizado
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

    # ===== Funciones auxiliares de formato ===== #
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

    # ====== Slash Commands ====== #
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
        stats = await self._get_bidirectional_stats(call_data, u1, u2)

        # Manejo de casos borde (mismo usuario o sin datos)
        if stats == "same_user":
            await interaction.response.send_message(
                "¡Tonto! No te selecciones a ti mismo o lo dejes en blanco, QUE EXPLOTO! :(\n"
                "Usa `/datos_totales_llamada` si quieres ver tus estadísticas con todos los del server con los que interactuaste."
            )
            return
        if stats is None:
            await interaction.response.send_message(
                f"No hay datos de llamadas entre **{user1.display_name}** y **{user2.display_name}**."
            )
            return

        calls_user1_to_user2 = stats["calls_ba"]
        calls_user2_to_user1 = stats["calls_ab"]
        total_seconds = stats["total_seconds"]

        msg = (
            f"📊 **Estadísticas de llamada entre {user1.display_name} y {user2.display_name}:**\n\n"
            f"🔹 {user1.display_name} → {user2.display_name}: {self.fmt_count(calls_user1_to_user2)}.\n"
            f"🔹 {user2.display_name} → {user1.display_name}: {self.fmt_count(calls_user2_to_user1)}.\n"
            f"🕒 Tiempo total compartido en llamada: {self.fmt_time(total_seconds)}."
        )

        await interaction.response.send_message(msg)

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

        # Verificación de existencia de datos (entrada o salida)
        my_data = call_data.get(mid, {})
        has_incoming = bool(my_data)
        has_outgoing = any(mid in inner for inner in call_data.values())

        if not (has_incoming or has_outgoing):
            return await interaction.followup.send(
                f"No hay datos para **{member.display_name}**."
            )

        # Filtrado de claves: Excluimos metadatos internos para obtener solo IDs de usuarios
        # Se utiliza comprensión de conjuntos para eficiencia y evitar duplicados
        internal_keys = [
            "depressive_attempts",
            "depressive_time",
            "total_solo_time",
            "opt_out_logs",
        ]

        uids_incoming = {k for k in my_data.keys() if k not in internal_keys}

        # Búsqueda inversa: IDs de usuarios que tienen registrado al usuario objetivo en sus datos
        uids_outgoing = {
            k for k, v in call_data.items() if mid in v and k not in internal_keys
        }

        # Unión de conjuntos para obtener lista única de interlocutores
        all_uids = list(uids_incoming | uids_outgoing)

        msg = f"📊 **Estadísticas de llamadas de {member.display_name}:**\n"

        # Estadísticas generales (Soledad y Depresión)
        dep_attempts = my_data.get("depressive_attempts", 0)
        solo_time = my_data.get("total_solo_time", 0)

        if dep_attempts > 0 or solo_time > 0:
            msg += "🔹 **Estadísticas generales**\n"
            if solo_time:
                msg += f"   • Tiempo a solas total: {self.fmt_time(solo_time)}. Todo ese rato ha estado esperando a alguien, o pensando... o llorando desconsoladamente.\n"
            if dep_attempts:
                msg += f"   • Intentos depresivos: {dep_attempts}. Ha estado llorando desconsoladamente {self.fmt_time(my_data.get('depressive_time', 0))}.\n"
            msg += "\n"

        # Listado detallado de interacciones
        if all_uids:
            msg += "🔹 **Interacciones detalladas entre usuarios:**\n"
            msg += f"   (Formato: *Usuario* → *Veces totales en llamada* (*Tiempo*) — *Veces que Usuario entró con {member.display_name}* | *Veces que {member.display_name} entró con Usuario*)\n\n"

            for uid in all_uids:
                # Obtenemos estadísticas agregadas bidireccionales
                stats = await self._get_bidirectional_stats(call_data, mid, uid)
                if not stats:
                    continue

                user_obj = stats.get("user_obj")
                name = user_obj.display_name if user_obj else f"[ID: {uid}]"

                t_calls = self.fmt_count(stats.get("total_calls", 0))
                t_time = self.fmt_time(stats.get("total_seconds", 0))
                c_in = self.fmt_count(stats.get("calls_ab", 0))  # Otros -> Usuario
                c_out = self.fmt_count(stats.get("calls_ba", 0))  # Usuario -> Otros

                msg += f"   • {name} → {t_calls} ({t_time}) — {c_in} | {c_out}.\n"

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
