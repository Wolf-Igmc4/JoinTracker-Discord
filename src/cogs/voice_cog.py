# src/cogs/voice_cog.py
import asyncio
from src.utils.json_manager import load_json
from discord.ext import commands
from src.utils.helpers import (
    handle_call_data,
    save_time,
    calculate_total_time,
    update_channel_history,
    timer_task,
    check_depressive_attempts,
)


class VoiceCog(commands.Cog):
    """Cog responsable de manejar todos los eventos relacionados con canales de voz."""

    def __init__(self, bot):
        self.bot = bot
        self.timeout = 600  # Tiempo en segundos para considerar un intento depresivo
        self.timers = {}  # Guarda tareas asyncio activas por usuario
        self.historiales_por_canal = (
            {}
        )  # Historial de cambios de usuarios en cada canal
        self.is_depressed = {}  # Marca usuarios que han estado solos demasiado tiempo
        self.recorded_attempts = (
            {}
        )  # Evita registrar múltiples intentos depresivos repetidos

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Detecta cambios en los canales de voz."""
        try:
            # Movimiento entre canales
            if (
                before.channel
                and after.channel
                and before.channel.id != after.channel.id
            ):
                # Si se mueve a otro servidor
                if before.channel.guild.id != after.channel.guild.id:
                    await self.member_left(member, before)
                    await self.member_joined(member, after)
                # Si se mueven en el mismo servidor
                else:
                    await self.member_moved(member, before, after)
            # Entrada a canal
            elif not before.channel and after.channel:
                await self.member_joined(member, after)
            # Salida de canal
            elif before.channel and not after.channel:
                await self.member_left(member, before)
        except Exception as e:
            print(f"Error en voice_update: {e}")

    async def member_joined(self, member, after):
        """Maneja la entrada de un miembro a un canal de voz."""

        # Se desmarcan flags de depresión (por si tenía alguno de antes)
        mid = str(member.id)
        if self.is_depressed.get(mid, False):
            self.is_depressed[mid] = False
            self.recorded_attempts.pop(mid, None)

        update_channel_history(self.historiales_por_canal, after.channel.id, 1)

        print(
            f"\033[92m[{member.guild.name}] {member.display_name} se ha unido a {after.channel.name}. "
            f"Ahora hay {len(after.channel.members)} miembros: "
            f"{', '.join(m.display_name for m in after.channel.members)}.\033[0m"
        )

        guild = member.guild
        stats = load_json(f"{guild.id}/stats.json")
        time_entries = load_json(f"{guild.id}/dates.json")

        num_members = len(after.channel.members)

        # Canal con ≥2 miembros
        if num_members >= 2:
            for m in after.channel.members:
                await self.cancel_timer(m)
                self.is_depressed[str(m.id)] = False
                self.recorded_attempts.pop(str(m.id), None)
                if m != member:
                    handle_call_data(stats, member, m)
                    save_time(time_entries, member, m, True)

        # Canal con 1 miembro
        elif num_members == 1:
            self.start_timer(member, time_entries)

        # Canal sin miembros y otros casos
        else:
            pass

    async def member_left(self, member, before):
        update_channel_history(self.historiales_por_canal, before.channel.id, -1)
        print(
            f"\033[91m[{member.guild.name}] {member.display_name} ha salido de {before.channel.name}. "
            f"Ahora quedan {len(before.channel.members)} miembros: {', '.join(m.display_name for m in before.channel.members)}\033[0m"
        )

        guild = member.guild
        stats = load_json(f"{guild.id}/stats.json")
        time_entries = load_json(f"{guild.id}/dates.json")
        mid = str(member.id)

        member_flag = self.is_depressed.get(mid, False)
        # Convertimos el bool en dict para la función
        member_flag_dict = {mid: member_flag}

        await self.cancel_timer(member)

        # Se resetea flag solo si el timer no se completó
        if not member_flag:
            self.is_depressed[mid] = False

        check_depressive_attempts(
            member, member_flag_dict, stats, self.recorded_attempts, time_entries
        )

        updated_users = []

        for m in before.channel.members:
            updated_users.append(m.display_name)
            if m != member:
                save_time(time_entries, member, m, False)
                calculate_total_time(time_entries, stats, member, m)

        if updated_users:
            print(
                f"[{member.guild.name}] Actualizado el tiempo con los usuarios: {', '.join(updated_users)}"
            )

    async def member_moved(self, member, before, after):
        """Maneja cuando un usuario se mueve de un canal a otro."""

        # Actualizar historial de canales
        update_channel_history(self.historiales_por_canal, before.channel.id, -1)
        update_channel_history(self.historiales_por_canal, after.channel.id, 1)

        num_after = len(after.channel.members)
        num_before = len(before.channel.members)

        print(
            f"\033[93m[{member.guild.name}] {member.display_name} se ha movido de "
            f"{before.channel.name} a {after.channel.name}.\033[0m "
            f"Ahora hay {num_after} miembros: {', '.join(m.display_name for m in after.channel.members)}."
        )

        guild = member.guild
        stats = load_json(f"{guild.id}/stats.json")
        time_entries = load_json(f"{guild.id}/dates.json")

        # Canal destino tiene ≥2 miembros
        if num_after >= 2:
            for m in after.channel.members:
                mid = str(m.id)
                self.is_depressed[mid] = False
                self.recorded_attempts.pop(mid, None)
                await self.cancel_timer(m)
                if m != member:
                    save_time(time_entries, member, m, True)
                    handle_call_data(stats, member, m)

        # Canal destino tiene exactamente 1 persona
        elif num_after == 1:
            self.start_timer(member, time_entries)

        # Canal origen tiene ≥2 miembros
        if num_before >= 2:
            for m in before.channel.members:
                print(f"Actualizando estadísticas para {member} con {m}")
                if m != member:
                    save_time(time_entries, member, m, False)
                    handle_call_data(stats, member, m)
                    calculate_total_time(time_entries, stats, member, m)

        # Canal origen queda con exactamente 1 persona
        elif num_before == 1:
            remaining_member = before.channel.members[0]
            self.start_timer(remaining_member, time_entries)
            save_time(time_entries, member, remaining_member, False)
            calculate_total_time(time_entries, stats, member, remaining_member)
            print(
                f"Actualizado el tiempo con el usuario: {remaining_member.display_name}"
            )

        # Canal sin miembros y otros casos
        else:
            pass

    def start_timer(self, member, time_entries):
        mid = str(member.id)
        if mid in self.timers:
            return

        task = asyncio.create_task(
            timer_task(
                member,
                self.is_depressed,
                self.timers,
                self.timeout,
                time_entries,
            )
        )
        self.timers[mid] = task
        print(
            f"\033[93m[{member.guild.name}] Temporizador iniciado para marcar a {member.display_name} con depresión.\033[0m"
        )

    async def cancel_timer(self, member):
        """Cancela y elimina un temporizador activo para un usuario si existe, esperando a que termine la tarea."""
        mid = str(member.id)
        task = self.timers.pop(mid, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(
                    f"\033[91mError al cancelar temporizador de {member.display_name}: {e}\033[0m"
                )


async def setup(bot):
    """Carga del cog en el bot principal."""
    await bot.add_cog(VoiceCog(bot))
