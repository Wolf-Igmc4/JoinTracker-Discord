# src/cogs/misc_cog.py
# Cog para funcionalidades misceláneas del bot, incluyendo mensajes cuando es mencionado.
from discord.ext import commands
import discord


class MiscCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignora mensajes del propio bot
        if message.author.bot:
            return

        # Si el bot fue mencionado directamente (@JoinTracker)
        if self.bot.user in message.mentions:
            embed = discord.Embed(
                title="Holaaa! Soy JoinTracker :3",
                description=(
                    "Te ayudo a **rastrear y analizar la actividad en llamadas de voz**.\n\n"
                    "📊 **Comandos principales:**\n"
                    "• `/datos_llamada` → Muestra cuántas veces un usuario se ha unido a otro en llamada.\n"
                    "• `/datos_totales_llamada` → Muestra todas las estadísticas de un usuario.\n"
                    "También registro los intentos de hablar en solitario (llamadas donde nadie más se une), "
                    "pero solo se registran cuando sales del canal! También se sigue la misma lógica para guardar\n"
                    "el tiempo entre usuarios :3.\n"
                    "Puedes ver la información de los comandos escribiendo '/' y leyendo su descripción."
                ),
                color=discord.Color.yellow(),
            )
            embed.set_footer(text="Desarrollado por Anth Zorax")

            await message.channel.send(embed=embed)

        # Permite que otros comandos sigan funcionando
        await self.bot.process_commands(message)


# ========= Setup ========= #
async def setup(bot):
    await bot.add_cog(MiscCog(bot))
