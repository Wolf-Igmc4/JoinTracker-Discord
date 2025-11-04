# from discord.ext import commands, tasks
# import os

# from bot.utils.json_manager import load_json
# from bot.utils.helpers import _send_to_fastapi


# class SyncCog(commands.Cog):
#     def __init__(self, bot):
#         self.bot = bot

#         # arrancamos el loop cuando el bot ya está listo
#         self.flush_task.start()

#     def cog_unload(self):
#         self.flush_task.cancel()

#     @tasks.loop(seconds=60)
#     async def flush_task(self):
#         # por cada servidor que tenga el bot
#         for guild in self.bot.guilds:
#             gid = str(guild.id)

#             datos_path = os.path.join("bot", "data", gid, "datos.json")
#             fechas_path = os.path.join("bot", "data", gid, "fechas.json")

#             # si no existe el archivo ese guild aún no ha generado datos → skip
#             if os.path.exists(datos_path):
#                 call_data = load_json(f"{gid}/datos.json")
#                 _send_to_fastapi(call_data, guild_id=gid)

#             if os.path.exists(fechas_path):
#                 time_entries = load_json(f"{gid}/fechas.json")
#                 _send_to_fastapi(time_entries, guild_id=gid)


# async def setup(bot):
#     await bot.add_cog(SyncCog(bot))
