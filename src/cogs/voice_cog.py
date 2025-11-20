# src/cogs/voice_cog.py
import asyncio

import discord
from src.utils.json_manager import load_json, save_json
from discord.ext import commands
from src.utils.helpers import (
    handle_call_data,
    save_time,
    calculate_total_time,
    update_channel_history,
    timer_task,
    check_depressive_attempts,
)
from datetime import datetime


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
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
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

    async def member_joined(self, member: discord.Member, after: discord.VoiceState):
        """Maneja la entrada de un miembro a un canal de voz."""

        update_channel_history(self.historiales_por_canal, after.channel.id, 1)

        print(
            f"\033[92m[{member.guild.name}] {member.display_name} se ha unido a {after.channel.name}. "
            f"Ahora hay {len(after.channel.members)} miembros: "
            f"{', '.join(m.display_name for m in after.channel.members)}.\033[0m"
        )

        guild = member.guild
        stats = load_json(f"{guild.id}/stats.json")
        time_entries = load_json(f"{guild.id}/dates.json")

        # Se desmarcan flags de depresión (por si tenía alguno de antes)
        mid = str(member.id)
        if self.is_depressed.get(mid, False):
            self.is_depressed[mid] = False
            self.recorded_attempts.pop(mid, None)
        self._clear_solo_depressive(mid, time_entries)

        num_members = len(after.channel.members)
        stats_changed = False

        # Canal con ≥2 miembros
        if num_members >= 2:

            for m in after.channel.members:
                await self.cancel_timer(m)
                self.is_depressed[str(m.id)] = False
                self.recorded_attempts.pop(str(m.id), None)

                # Si ese miembro tenía un periodo "total solo" abierto, lo cerramos y acumulamos en stats
                elapsed = self._end_total_solo(time_entries, stats, m)
                if elapsed:
                    stats_changed = True

                if m != member:
                    handle_call_data(stats, member, m)
                    save_time(time_entries, member, m, True)

        # Canal con 1 miembro (queda solo)
        elif num_members == 1:
            # Registrar inicio de tiempo total solo en dates.json
            if self._start_total_solo(time_entries, member):
                stats_changed = True

            # Iniciar temporizador de depresión
            self.start_timer(member, time_entries)

        # Canal sin miembros y otros casos
        else:
            pass

        # Guardamos dates y stats.json
        if stats_changed:
            save_json(stats, f"{guild.id}/stats.json")
        save_json(time_entries, f"{guild.id}/dates.json")

    async def member_left(self, member: discord.Member, before: discord.VoiceState):
        update_channel_history(self.historiales_por_canal, before.channel.id, -1)
        print(
            f"\033[91m[{member.guild.name}] {member.display_name} ha salido de {before.channel.name}. "
            f"Ahora quedan {len(before.channel.members)} miembros: {', '.join(m.display_name for m in before.channel.members)}\033[0m"
        )

        guild = member.guild
        stats = load_json(f"{guild.id}/stats.json")
        time_entries = load_json(f"{guild.id}/dates.json")
        mid = str(member.id)

        stats_changed = False

        # Convertimos el bool en dict para la función
        member_flag = self.is_depressed.get(mid, False)
        member_flag_dict = {mid: member_flag}

        # Cancelamos timer del que sale (si existía)
        await self.cancel_timer(member)

        # Se resetea flag solo si el timer no se completó
        if not member_flag:
            self.is_depressed[mid] = False

        check_depressive_attempts(
            member, member_flag_dict, stats, self.recorded_attempts, time_entries
        )

        # Si el miembro que sale tenía un _solo_total_start en time_entries, lo finalizamos
        elapsed = self._end_total_solo(time_entries, stats, member)
        if elapsed:
            stats_changed = True

        updated_users = []

        for m in before.channel.members:
            updated_users.append(m.display_name)
            if m != member:
                save_time(time_entries, member, m, False)
                calculate_total_time(time_entries, stats, member, m)

        # 2) Si después de la salida queda exactamente 1 miembro (queda solo)
        if len(before.channel.members) == 1:
            remaining = before.channel.members[0]
            # Registrar inicio de tiempo total solo en dates.json
            if self._start_total_solo(time_entries, remaining):
                stats_changed = True

            # Iniciar temporizador de depresión (DESHABILITADO, NO NECESARIO SEGÚN DISEÑO)
            # self.start_timer(remaining, time_entries)

        if updated_users:
            print(
                f"[{member.guild.name}] Actualizado el tiempo con los usuarios: {', '.join(updated_users)}"
            )

        # Guardamos dates y stats.json
        if stats_changed:
            save_json(stats, f"{guild.id}/stats.json")
        save_json(time_entries, f"{guild.id}/dates.json")

    async def member_moved(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
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

        stats_changed = False

        # Canal destino tiene ≥2 miembros: cancelar timers y, por si alguno tenía start en stats, finalizarlo
        if num_after >= 2:
            for m in after.channel.members:
                midm = str(m.id)
                self.is_depressed[midm] = False
                self.recorded_attempts.pop(midm, None)
                await self.cancel_timer(m)

                # Si ese miembro tenía _solo_total_start en stats, finalizamos
                elapsed = self._end_total_solo(time_entries, stats, m)
                if elapsed:
                    stats_changed = True

                if m != member:
                    save_time(time_entries, member, m, True)
                    handle_call_data(stats, member, m)

        # Canal destino tiene exactamente 1 persona (queda solo)
        elif num_after == 1:
            # Registrar inicio de tiempo total solo en dates.json
            if self._start_total_solo(time_entries, member):
                stats_changed = True

            # Iniciar temporizador de depresión
            self.start_timer(member, time_entries)

        # Canal origen tiene ≥2 miembros
        if num_before >= 2:
            for m in before.channel.members:
                print(f"Actualizando estadísticas para {member} con {m}")
                if m != member:
                    save_time(time_entries, member, m, False)
                    handle_call_data(stats, member, m)
                    calculate_total_time(time_entries, stats, member, m)

        # Canal origen queda con exactamente 1 persona (queda solo)
        elif num_before == 1:
            remaining_member = before.channel.members[0]

            # Registrar inicio del tiempo solo para el que queda
            if self._start_total_solo(time_entries, remaining_member):
                stats_changed = True

            # Iniciar temporizador de depresión
            self.start_timer(remaining_member, time_entries)

            save_time(time_entries, member, remaining_member, False)
            calculate_total_time(time_entries, stats, member, remaining_member)
            print(
                f"Actualizado el tiempo con el usuario: {remaining_member.display_name}"
            )

        # Canal sin miembros y otros casos
        else:
            pass

        # Guardamos dates y stats.json
        if stats_changed:
            save_json(stats, f"{guild.id}/stats.json")
        save_json(time_entries, f"{guild.id}/dates.json")

    def start_timer(self, member: discord.Member, time_entries):
        mid = str(member.id)
        if mid in self.timers:
            return

        task = asyncio.create_task(
            timer_task(
                member,
                self.is_depressed,
                self.timeout,
                time_entries,
            )
        )
        self.timers[mid] = task
        print(
            f"\033[93m[{member.guild.name}] Temporizador iniciado para marcar a {member.display_name} con depresión.\033[0m"
        )

    # Helpers
    def _ensure_user_stats(self, stats, mid):
        """Asegura que exista la entrada stats[mid]."""
        if mid not in stats:
            stats[mid] = {}

    def _start_total_solo(self, time_entries, member):
        """
        Marca el inicio del periodo 'total solo' para member en dates.json (time_entries).
        """
        mid = str(member.id)
        if mid not in time_entries:
            time_entries[mid] = {}

        if not time_entries[mid].get("_solo_total_start"):
            time_entries[mid]["_solo_total_start"] = datetime.now().isoformat()
            time_entries[mid]["_solo_total_channel"] = getattr(
                member.voice.channel, "id", None
            )
            return True

        return False

    def _end_total_solo(self, time_entries, stats, member: discord.Member):
        """
        Cierra el periodo 'total solo' leyendo de dates.json (time_entries)
        y suma el resultado en stats.json (stats).
        """
        mid = str(member.id)
        start_iso = time_entries.get(mid, {}).get("_solo_total_start")

        if start_iso:
            try:
                start_dt = datetime.fromisoformat(start_iso)
            except Exception:
                # Formato raro → limpiar y no acumular
                time_entries[mid]["_solo_total_start"] = None
                return 0

            elapsed = (datetime.now() - start_dt).total_seconds()

            # Asegurar existencia en stats para el contador de tiempo total
            self._ensure_user_stats(stats, mid)

            stats[mid]["total_solo_time"] = (
                stats[mid].get("total_solo_time", 0) + elapsed
            )

            # Reseteo tras cerrar el periodo
            time_entries[mid].pop("_solo_total_start", None)
            time_entries[mid].pop("_solo_total_channel", None)

            return elapsed

        return 0

    def _clear_solo_depressive(self, user_id, time_entries):
        """
        Limpia los marcadores de depresión de un usuario si ya no está solo.
        """
        entry = time_entries.get(str(user_id))
        if entry:
            entry.pop("_solo_depressive_start", None)
            entry.pop("_solo_depressive_channel_id", None)
            # Si no queda nada en el dict del usuario, lo eliminamos
            if not entry:
                time_entries.pop(str(user_id))

    async def cancel_timer(self, member: discord.Member):
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


async def setup(bot: commands.Bot):
    """Carga del cog en el bot principal."""
    await bot.add_cog(VoiceCog(bot))
