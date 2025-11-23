import discord
from discord.ui import View, Button, Select
from src.utils.data_handler import load_json, save_json
from src.utils.helpers import get_data_path


# ========= CLASES DE CONFIGURACIÓN =========
def generate_settings_interface(
    guild_id: int, user_id: str, specific_status_msg: str = None
):
    """
    Genera el Embed y la Vista de configuración.
    """
    path_stats = get_data_path(guild_id, "stats.json")
    data = load_json(path_stats)

    user_data = data.get(user_id, {})
    is_opt_out = user_data.get("opt_out_logs", False)
    tracking_active = not is_opt_out

    if specific_status_msg:
        status_text = specific_status_msg
    else:
        status_text = "✅ Activo" if tracking_active else "❌ Inactivo"

    embed = discord.Embed(
        title="⚙️ Configuración",
        description=f"**Seguimiento:** ***{status_text}***\n"
        f"\nℹ️ *Si desactivas el seguimiento, tus tiempos en llamada no se registrarán. "
        f"No se verán afectadas las estadísticas guardadas previamente.*",
        color=discord.Color.blue(),
    )

    view = ToggleSettingsView(user_id, tracking_active, guild_id)
    return embed, view


class ConfirmDeleteView(View):
    def __init__(self, user_id: str, guild_id: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.guild_id = guild_id
        self.message = None

    async def on_timeout(self):
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
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.user_id:
            return

        await interaction.response.defer(ephemeral=False)
        mid = self.user_id
        files_to_clean = ["stats.json", "dates.json"]

        for filename in files_to_clean:
            try:
                path = get_data_path(self.guild_id, filename)
                data = load_json(path)

                # Limpieza profunda
                for other_user_id, other_user_data in data.items():
                    if other_user_id == mid:
                        continue
                    if isinstance(other_user_data, dict) and mid in other_user_data:
                        del other_user_data[mid]

                if mid in data:
                    del data[mid]

                if filename == "stats.json":
                    data[mid] = {"opt_out_logs": True}

                save_json(path, data)
            except Exception as e:
                print(f"[ERROR ConfirmDelete] {e}")

        print(f"[INFO] Usuario {self.user_id} borró historial en {self.guild_id}.")

        new_embed = discord.Embed(
            title="⚙️ Configuración",
            description=f"**Seguimiento:** ***❌ Inactivo (Datos borrados)***\n"
            f"\nℹ️ *Tu historial ha sido eliminado y el seguimiento desactivado permanentemente.*",
            color=discord.Color.blue(),
        )

        await interaction.edit_original_response(
            content="✅ **Historial eliminado correctamente.**",
            embed=new_embed,
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.user_id:
            return
        await interaction.response.edit_message(
            content="Operación cancelada.", view=None, embed=None
        )
        self.stop()


class ToggleSettingsView(View):
    def __init__(self, user_id: str, logs_activados: bool, guild_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.logs_activados = logs_activados
        self.guild_id = guild_id
        self.message = None

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

        select_menu = Select(
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

        delete_btn = Button(
            label="Borrar historial de interacciones",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            row=1,
        )
        delete_btn.callback = self.callback_delete
        self.add_item(delete_btn)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                fresh_embed, _ = generate_settings_interface(
                    self.guild_id, self.user_id
                )
                await self.message.edit(
                    content="⌛ **Sesión caducada.**",
                    embed=fresh_embed,
                    view=self,
                )
            except Exception:
                pass

    async def menu_callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "No toques lo de otros.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        eleccion = interaction.data["values"][0]
        path_stats = get_data_path(self.guild_id, "stats.json")
        data = load_json(path_stats)

        if self.user_id not in data:
            data[self.user_id] = {}

        if eleccion == "activar":
            data[self.user_id]["opt_out_logs"] = False
            new_status = True
        else:
            data[self.user_id]["opt_out_logs"] = True
            new_status = False

        save_json(path_stats, data)

        embed, view = generate_settings_interface(self.guild_id, self.user_id)
        await interaction.edit_original_response(content=None, embed=embed, view=view)
        view.message = await interaction.original_response()

    async def callback_delete(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            return
        view_confirm = ConfirmDeleteView(self.user_id, self.guild_id)
        await interaction.response.send_message(
            "⚠️ **¿Estás seguro de que quieres borrar todo?**",
            view=view_confirm,
            ephemeral=False,
        )
        view_confirm.message = await interaction.original_response()


# ========= PAGINADOR BASE =========
class BasePaginatorView(View):
    """
    Clase base reutilizable para paginar listas de items.
    Hereda de esta clase y define `get_page_content` para personalizar qué se muestra.
    """

    def __init__(self, items_per_page=10):
        super().__init__(timeout=180)
        self.items_per_page = items_per_page
        self.current_page = 0
        self.data_list = []  # Lista de datos a paginar (dict, objetos, strings...)
        self.title = "Estadísticas"  # Título por defecto

    def set_data(self, data: list, title: str):
        """Carga los datos y calcula páginas totales."""
        self.data_list = data
        self.title = title
        # Calcular total de páginas (ceil division)
        self.total_pages = (len(data) + self.items_per_page - 1) // self.items_per_page
        self.update_buttons()

    def update_buttons(self):
        """Habilita o deshabilita botones según la página actual."""
        self.children[0].disabled = self.current_page == 0  # Botón Anterior
        self.children[1].disabled = (
            self.current_page >= self.total_pages - 1
        )  # Botón Siguiente

    def get_page_content(self):
        """
        MÉTODO ABSTRACTO: Sobrescríbelo en tu clase hija.
        Debe devolver el (embed, content) para la página actual.
        """
        raise NotImplementedError(
            "Debes implementar get_page_content en la clase hija."
        )

    @discord.ui.button(label="◀", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed, content = self.get_page_content()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            embed, content = self.get_page_content()
            await interaction.response.edit_message(embed=embed, view=self)


class UserStatsPaginator(BasePaginatorView):
    """
    Paginador específico para estadísticas de usuario.
    Muestra estadísticas generales ARRIBA y lista de interacciones ABAJO.
    """

    def __init__(
        self,
        data: list,
        user_display_name: str,
        solo_time: int,
        dep_attempts: int,
        dep_time: int,
    ):
        super().__init__(items_per_page=15)
        self.user_name = user_display_name
        self.solo_time = solo_time
        self.dep_attempts = dep_attempts
        self.dep_time = dep_time
        self.set_data(data, f"Estadísticas de {user_display_name}")

    @staticmethod
    def fmt_time(seconds):
        if seconds < 60:
            return f"{int(seconds)} segundos"
        minutes = seconds / 60
        if minutes < 60:
            return f"{round(minutes, 1)} minutos"
        return f"{round(minutes / 60, 1)} horas"

    def get_page_content(self):
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_items = self.data_list[start:end]

        embed = discord.Embed(title=f"📊 {self.title}", color=discord.Color.blue())

        final_description = ""

        # --- 1. ESTADÍSTICAS DEL MIEMBRO (Solo Página 1) ---
        is_general_data_present = self.solo_time > 0 or self.dep_attempts > 0

        if self.current_page == 0 and is_general_data_present:
            final_description += "🔷 **Estadísticas del miembro:**\n"
            if self.solo_time > 0:
                final_description += (
                    f"• **Tiempo a solas total:** `{self.fmt_time(self.solo_time)}`\n"
                )
            if self.dep_attempts > 0:
                final_description += f"• **Intentos depresivos:** {self.dep_attempts} tristes intentos • `{self.fmt_time(self.dep_time)}`\n"

            # Salto de línea para separar secciones
            final_description += "\n"

        # --- 2. LISTA DE INTERACCIONES ---
        final_description += f"🔶 **Estadísticas con otros usuarios** (Página {self.current_page + 1}/{self.total_pages}):\n"

        lines = []
        for index, stat in enumerate(page_items):
            rank = start + index + 1
            if rank == 1:
                icon = "🥇"
            elif rank == 2:
                icon = "🥈"
            elif rank == 3:
                icon = "🥉"
            else:
                icon = f"`#{rank}`"

            name = stat["name"]
            time_str = self.fmt_time(stat["total_seconds"])
            total = stat["total_calls"]
            c_in = stat.get("calls_in", 0)
            c_out = stat.get("calls_out", 0)

            # Formato de línea
            line = f"{icon} **{name}** • `{time_str}` • {total} llamada{'s' if total != 1 else ''} • 📥 {c_in} | 📤 {c_out}"
            lines.append(line)

        if not lines:
            final_description += "No hay interacciones registradas."
        else:
            final_description += "\n".join(lines)

        # --- 3. ASIGNACIÓN FINAL ---
        embed.description = final_description

        # Footer con leyenda
        embed.set_footer(
            text=f"📥: Se unió a {self.user_name} | 📤: {self.user_name} se unió al usuario"
        )

        return embed, None
