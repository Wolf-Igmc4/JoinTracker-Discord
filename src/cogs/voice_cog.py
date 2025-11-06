# src/cogs/voice_cog.py
import asyncio
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


class VoiceCog(commands.Cog):
    """Cog responsable de manejar todos los eventos relacionados con canales de voz."""

    def __init__(self, bot):
        self.bot = bot
        self.timeout = 150  # Tiempo en segundos para considerar un intento depresivo
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
                await self.member_moved(member, before, after)
            # Entrada a canal
            elif not before.channel and after.channel:
                await self.member_joined(member, after)
            # Salida de canal
            elif before.channel and not after.channel:
                await self.member_left(member, before)
        except Exception as e:
            print(f"Error en voice update: {e}")

    async def member_joined(self, member, after):
        """Maneja la entrada de un miembro a un canal de voz."""
        mid = str(member.id)
        self.is_depressed[mid] = False
        self.recorded_attempts.pop(mid, None)

        update_channel_history(self.historiales_por_canal, after.channel.id, 1)
        print(
            f"\033[92m[{member.guild.name}] {member.display_name} se ha unido a {after.channel.name}. "
            f"Ahora hay {len(after.channel.members)} miembros: {', '.join(m.display_name for m in after.channel.members)}.\033[0m"
        )

        guild = member.guild
        # cargamos stats (antes datos.json) y las fechas
        stats = load_json(f"{guild.id}/stats.json")
        time_entries = load_json(f"{guild.id}/fechas.json")

        if len(after.channel.members) >= 2:
            for m in after.channel.members:
                self.cancel_timer(m)
                # si el usuario estaba marcado como deprimido, consolidamos su tiempo solo
                if self.is_depressed.get(str(m.id)):
                    check_depressive_attempts(
                        m,
                        self.is_depressed,
                        stats,
                        self.recorded_attempts,
                        time_entries,
                    )

                if m != member:
                    handle_call_data(stats, member, m)
                    save_time(time_entries, member, m, True)
        else:
            self.start_timer(member, stats, time_entries)

    async def member_left(self, member, before):
        """Maneja la salida de un miembro de un canal de voz."""
        update_channel_history(self.historiales_por_canal, before.channel.id, -1)
        print(
            f"\033[91m[{member.guild.name}] {member.display_name} ha salido de {before.channel.name}. "
            f"Ahora quedan {len(before.channel.members)} miembros: {', '.join(m.display_name for m in before.channel.members)}\033[0m"
        )

        guild = member.guild
        stats = load_json(f"{guild.id}/stats.json")
        time_entries = load_json(f"{guild.id}/fechas.json")

        check_depressive_attempts(
            member, self.is_depressed, stats, self.recorded_attempts, time_entries
        )
        self.cancel_timer(member)

        for m in before.channel.members:
            if m != member:
                save_time(time_entries, member, m, True)
                print("Se ha guardado tiempo de llamada al unirse.")
                calculate_total_time(time_entries, stats, member, m)

    async def member_moved(self, member, before, after):
        """Maneja cuando un usuario se mueve de un canal a otro."""
        update_channel_history(self.historiales_por_canal, before.channel.id, -1)
        update_channel_history(self.historiales_por_canal, after.channel.id, 1)
        print(
            f"[{member.guild.name}] {member.display_name} se ha movido de {before.channel.name} a {after.channel.name}. Ahora hay {len(after.channel.members)} miembros: {', '.join(m.display_name for m in after.channel.members)}."
        )

        guild = member.guild
        stats = load_json(f"{guild.id}/stats.json")
        time_entries = load_json(f"{guild.id}/fechas.json")

        # Si el canal destino tiene al menos 2 o más personas, registrar la interacción
        if len(after.channel.members) >= 2:
            self.cancel_timer(member)
            for m in after.channel.members:
                # registrar llamadas/tiempo entre el que se ha movido y los demás
                if m != member:
                    save_time(time_entries, member, m, True)
                    handle_call_data(stats, member, m)

        else:
            # Si el canal origen queda con 1 persona, iniciar temporizador para esa persona
            print("[DEBUG] Canal destino queda solo con el usuario.")
            self.start_timer(member, stats, time_entries)
            for m in before.channel.members:
                if m != member:
                    save_time(time_entries, member, m, False)
                    calculate_total_time(time_entries, stats, member, m)

    def start_timer(self, member, stats, time_entries):
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
            f"\033[93mTemporizador iniciado para {member.display_name} ({self.timeout}s).\033[0m"
        )

    def cancel_timer(self, member):
        """Cancela y elimina un temporizador activo para un usuario si existe."""
        mid = str(member.id)
        if mid in self.timers:
            try:
                self.timers[
                    mid
                ].cancel()  # Cancela el temporizador; mensaje en timer_task
            except Exception as e:
                print(
                    f"\033[91mError al cancelar temporizador de {member.display_name}: {e}\033[0m"
                )
            del self.timers[mid]


async def setup(bot):
    """Carga del cog en el bot principal."""
    await bot.add_cog(VoiceCog(bot))
