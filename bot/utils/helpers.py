# bot/utils/helpers.py
import asyncio
import datetime
from .json_manager import save_json
import os, json
import requests

# ---------------- Configuración FastAPI ----------------
API_URL = os.getenv(
    "FASTAPI_URL",
    "https://delicious-kelly-anth-zorax-61faf784.koyeb.app/save-json",
)
API_KEY = os.getenv("FASTAPI_KEY", None)


def _send_to_fastapi(data, guild_id=None):
    """
    Envía datos a FastAPI incluyendo guild_id.
    guild_id es opcional: si no se proporciona se usa 'default'.
    No reemplaza el guardado local.
    """
    gid = str(guild_id) if guild_id is not None else "default"
    payload = {"guild_id": gid, "data": data}
    headers = {}
    if API_KEY:
        headers["x-api-key"] = API_KEY

    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=6)
        if resp.status_code != 200:
            print(f"[FastAPI] Error HTTP {resp.status_code}: {resp.text}")
        else:
            # opcional: mostrar respuesta corta
            print(f"[FastAPI] Datos enviados para guild {gid}.")
    except Exception as e:
        print(f"[FastAPI] Excepción al enviar datos para guild {gid}: {e}")


def _get_paths(member):
    """Devuelve las rutas base de los JSON según el servidor."""
    gid = str(member.guild.id)
    return f"{gid}/datos.json", f"{gid}/fechas.json"


# ======================== #
#  MANEJO DE CALL DATA     #
# ======================== #
def handle_call_data(call_data, member, channel_member):
    """Registra cuántas veces un usuario entra donde hay otro."""
    cmid, mid = str(channel_member.id), str(member.id)
    call_data.setdefault(cmid, {}).setdefault(mid, 0)
    call_data[cmid][mid] += 1

    datos_path, _ = _get_paths(member)
    save_json(call_data, datos_path)
    _send_to_fastapi(call_data)


def check_depressive_attempts(member, is_depressed, call_data, recorded_attempts):
    """Registra intentos depresivos si el usuario estuvo solo en llamada."""
    mid = str(member.id)
    if is_depressed.get(mid) and not recorded_attempts.get(mid):
        call_data.setdefault(mid, {})
        call_data[mid]["intentos_depresivos"] = (
            call_data[mid].get("intentos_depresivos", 0) + 1
        )

        datos_path, _ = _get_paths(member)
        save_json(call_data, datos_path)
        _send_to_fastapi(call_data)

        recorded_attempts[mid] = True
        print(
            f"{member.display_name} ha tenido un intento depresivo ({call_data[mid]['intentos_depresivos']})"
        )


# ======================== #
#   MANEJO DE TIEMPO VC    #
# ======================== #
def save_time(time_entries, member, channel_member, enter=True):
    """Guarda los tiempos de entrada/salida entre usuarios."""
    current_time = datetime.datetime.now().isoformat()

    def ensure_entry(a, b):
        time_entries.setdefault(str(a.id), {}).setdefault(
            str(b.id), {"entries": [], "total_time": 0}
        )

    def add_start(a, b):
        ensure_entry(a, b)
        time_entries[str(a.id)][str(b.id)]["entries"].append(
            {"start_time": current_time, "end_time": None}
        )

    def add_end(a, b):
        entries = time_entries.get(str(a.id), {}).get(str(b.id), {}).get("entries", [])
        if entries and entries[-1]["end_time"] is None:
            entries[-1]["end_time"] = current_time

    if enter:
        add_start(member, channel_member)
        add_start(channel_member, member)
    else:
        add_end(member, channel_member)
        add_end(channel_member, member)

    _, fechas_path = _get_paths(member)
    save_json(time_entries, fechas_path)
    _send_to_fastapi(time_entries)


def calculate_total_time(time_entries, member, channel_member):
    """Recalcula el tiempo total compartido entre dos usuarios."""
    from datetime import datetime

    mid, oid = str(member.id), str(channel_member.id)

    if mid not in time_entries or oid not in time_entries[mid]:
        return

    # Tiempo de las entradas actuales
    new_total = sum(
        (
            datetime.fromisoformat(e["end_time"])
            - datetime.fromisoformat(e["start_time"])
        ).total_seconds()
        for e in time_entries[mid][oid]["entries"]
        if e["start_time"] and e["end_time"]
    )

    # Sumar al total previo
    prev_total = time_entries[mid][oid].get("total_time", 0)
    total = prev_total + new_total

    time_entries[mid][oid]["total_time"] = total
    time_entries[oid][mid]["total_time"] = total

    # limpiar histórico ya consolidado
    time_entries[mid][oid]["entries"] = []
    time_entries[oid][mid]["entries"] = []

    _, fechas_path = _get_paths(member)
    save_json(time_entries, fechas_path)
    _send_to_fastapi(time_entries)


# ======================== #
#   HISTORIAL DE CANALES   #
# ======================== #
def update_channel_history(historiales_por_canal, channel_id, cambio):
    """Actualiza el historial del número de miembros en un canal."""
    historiales_por_canal.setdefault(channel_id, [0])
    historiales_por_canal[channel_id].append(
        historiales_por_canal[channel_id][-1] + cambio
    )
    _send_to_fastapi(historiales_por_canal)


# ======================== #
#    TEMPORIZADOR DE VC    #
# ======================== #
async def timer_task(member, is_depressed, timers, timeout=150):
    """Marca un usuario como deprimido si permanece solo demasiado tiempo."""
    time_left = timeout
    try:
        while time_left > 0:
            await asyncio.sleep(1)
            # Solo imprimir cada 30 segundos o al inicio
            if time_left % 30 == 0 or time_left == timeout:
                print(
                    f"[{member.guild.name}] {member.display_name} se deprimirá en {time_left}s."
                )

            time_left -= 1

        # si se ha agotado el tiempo y SIGUE solo → marcar deprimido
        print(
            f"[{member.guild.name}] {member.display_name} se deprimirá mucho en {member.voice.channel.name} si nadie entra con él ahora."
        )
        is_depressed[str(member.id)] = True

    except asyncio.CancelledError:
        # Se canceló antes de tiempo (se llamó a cancel_timer para el usuario desde voice_cog)
        print(
            f"\033[93m[{member.guild.name}] Temporizador cancelado para {member.display_name} antes de deprimirse (quedaban {time_left}s).\033[0m"
        )
        is_depressed[str(member.id)] = False
        timers.pop(str(member.id), None)


# ======================== #
#    ACTUALIZADOR JSON     #
# ======================== #
async def update_json_file(bot, interaction, filename, global_vars: dict, timeout=60.0):
    """
    Espera a que el usuario envíe un archivo JSON y lo actualiza.
    Acepta el archivo en el mismo canal donde se ejecutó el comando o por DM.
    """
    user = interaction.user
    origin_channel = interaction.channel

    # Aseguramos que exista un canal DM del usuario
    dm_channel = user.dm_channel
    if dm_channel is None:
        dm_channel = await user.create_dm()

    # Hacemos visible la instrucción en el canal (no ephemeral) para que el usuario la vea
    try:
        await interaction.followup.send(
            f"Por favor, envía, `{filename}` **en este canal** o **por DM**. Tienes {timeout} segundos.",
            ephemeral=False,
        )
    except Exception:
        # Si followup falla por alguna razón, intentamos enviar por DM
        await user.send(
            f"Por favor, envía `{filename}` por DM al bot. Tienes {timeout} segundos."
        )

    def check(message):
        # Aceptamos si: mismo autor, tiene attachments con .json y viene del canal original o del DM
        try:
            is_author = message.author == user
            has_attachment = bool(message.attachments)
            filename_ok = has_attachment and message.attachments[
                0
            ].filename.lower().endswith(".json")
            same_channel = message.channel == origin_channel
            from_dm = message.channel == dm_channel
            return (
                is_author
                and has_attachment
                and filename_ok
                and (same_channel or from_dm)
            )
        except Exception:
            return False

    print(
        f"[DEBUG] Esperando {filename} de {user} en canal {origin_channel} o DM {dm_channel}"
    )

    try:
        message = await bot.wait_for("message", check=check, timeout=timeout)
        attachment = message.attachments[0]

        # Guardamos con nombre temporal para evitar colisiones
        tmp_name = f"tmp_{user.id}_{attachment.filename}"
        await attachment.save(tmp_name)
        print(f"[DEBUG] Archivo guardado temporalmente como {tmp_name}")

        # Leemos el JSON
        with open(tmp_name, "r", encoding="utf-8") as f:
            new_data = json.load(f)

        # Actualizamos la variable global (se asume que global_vars contiene la referencia)
        if filename in global_vars:
            target_obj = global_vars[filename]
            # Intentamos actualizar in-place si es mutable
            if isinstance(target_obj, dict):
                target_obj.clear()
                target_obj.update(new_data)
            elif isinstance(target_obj, list):
                target_obj.clear()
                target_obj.extend(new_data)
            else:
                # Si no es mutable, reemplazamos la entrada en el dict global_vars
                global_vars[filename] = new_data

        # Guardamos en disco usando tu save_json (guardará en la ruta que uses internamente)
        # Aquí construimos la ruta por servidor (igual que en tu _get_paths)
        guild = interaction.guild
        if guild:
            write_path = os.path.join(str(guild.id), filename)
        else:
            # fallback: guardamos en raíz si no hay guild (p. ej. DM)
            write_path = filename

        # Asegúrate de que el directorio exista
        os.makedirs(os.path.dirname(write_path) or ".", exist_ok=True)

        save_json(new_data, write_path)
        print(f"[DEBUG] JSON guardado en {write_path}")

        await interaction.followup.send(
            f"`{filename}` actualizado correctamente.", ephemeral=False
        )

        # limpiar
        os.remove(tmp_name)
        return True

    except asyncio.TimeoutError:
        await interaction.followup.send(
            f"Tiempo de espera agotado para `{filename}`.", ephemeral=False
        )
        print(f"[DEBUG] Timeout esperando {filename} de {user}")
        return False

    except Exception as e:
        await interaction.followup.send(
            f"Ocurrió un error con `{filename}`: {e}", ephemeral=True
        )
        print(f"[ERROR] Error procesando {filename}: {e}", exc_info=True)
        # intentar limpiar archivo temporal si existe
        try:
            if tmp_name and os.path.exists(tmp_name):
                os.remove(tmp_name)
        except Exception:
            pass
        return False
