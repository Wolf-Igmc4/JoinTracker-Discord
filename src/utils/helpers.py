# src/utils/helpers.py
import asyncio
from .json_manager import save_json
import os, json
import requests
from dotenv import load_dotenv
import os


# ---------------- Configuración FastAPI ----------------
load_dotenv()
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY", None)

# DEBUG temporal para verificar si la clave se cargó:
print(f"[DEBUG][ENV] API_URL cargada: {bool(API_URL)}")
print(f"[DEBUG][ENV] API_KEY cargada: {bool(API_KEY)}")


def stringify_keys(obj):
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            new_key = str(k) if not isinstance(k, str) else k
            new[new_key] = stringify_keys(v)
        return new
    elif isinstance(obj, list):
        return [stringify_keys(i) for i in obj]
    else:
        return obj


# DEBUG: encuentra claves no-str en un dict anidado
def find_non_str_keys(obj, path="root"):
    bad = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                bad.append((path + f"/{repr(k)}", type(k).__name__))
            bad.extend(find_non_str_keys(v, path + f"/{repr(k)}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            bad.extend(find_non_str_keys(v, path + f"[{i}]"))
    return bad


def send_to_fastapi(data, guild_id=None):
    """
    Envía data a FastAPI por guild_id.
    Se usa el endpoint POST /save-json con payload {"guild_id","data"}.
    Imprime información de debug (status + body) para depuración.
    """
    gid = str(guild_id) if guild_id is not None else "default"
    if not API_URL:
        print(
            f"[FastAPI][ERROR] API_URL no configurada. No se puede enviar datos para {gid}."
        )
        return

    safe_data = stringify_keys(data)
    # opcional: si quieres detectar cambios
    if safe_data != data:
        print(
            f"[FastAPI][WARN] Datos para {gid} han sido sanitizados (claves no-str convertidas)."
        )

    # debug: encontrar claves no-str
    bad = find_non_str_keys(safe_data)
    if bad:
        print("[DEBUG] Claves no-str detectadas:")
        for path, t in bad:
            print("   ", path, "tipo:", t)
    else:
        print("[DEBUG] Todas las claves son str")

    payload = {"guild_id": gid, "data": safe_data}
    headers = {}
    if API_KEY:
        headers["x-api-key"] = API_KEY

    endpoint = f"{API_URL.rstrip('/')}/save-json"
    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        print(f"[FastAPI][DEBUG] POST {endpoint} -> status {resp.status_code}")
        print(f"[FastAPI][DEBUG] response body: {resp.text}")
        resp.raise_for_status()
        print(f"[FastAPI] Datos enviados para servidor {gid}.")
    except Exception as e:
        print(f"[FastAPI] Excepción al enviar datos para servidor {gid}: {e}")


def _get_paths(member):
    """Devuelve las rutas base de los JSON según el servidor."""
    gid = str(member.guild.id)
    return f"{gid}/stats.json", f"{gid}/fechas.json"


# ============================== #
#  MANEJO DE EVENTOS DE LLAMADA  #
# ============================== #
def handle_call_data(stats, member, channel_member):
    """Actualiza las estadísticas de llamadas entre dos usuarios."""
    joiner_id = str(member.id)  # ID del que entra
    existing_id = str(channel_member.id)  # ID del que ya estaba

    # Garantiza que existan las estructuras necesarias
    stats.setdefault(existing_id, {})
    stats.setdefault(joiner_id, {})
    stats[existing_id].setdefault(joiner_id, {})
    stats[joiner_id].setdefault(existing_id, {})

    stats[existing_id][joiner_id].setdefault("calls_started", 0)
    stats[existing_id][joiner_id].setdefault("total_shared_time", 0)
    stats[joiner_id][existing_id].setdefault(
        "total_shared_time", stats[existing_id][joiner_id]["total_shared_time"]
    )

    # Incrementa contador de llamadas iniciadas por el usuario que entra
    stats[existing_id][joiner_id]["calls_started"] += 1

    # Guardar cambios en el JSON
    stats_path, _ = _get_paths(member)
    save_json(stats, stats_path)


def check_depressive_attempts(
    member, is_depressed, stats, recorded_attempts, time_entries=None
):
    """
    Consolida un intento depresivo:
    - incrementa stats[mid]['intentos_depresivos']
    - suma el tiempo solo leyendo time_entries['_solo'][mid] (si existe) en stats[mid]['depressive_time']
    - borra el marcador de time_entries y guarda ambos JSON
    - marca recorded_attempts[mid] = True para no duplicar
    """
    import datetime

    mid = str(member.id)

    # precondiciones: debe estar marcado como deprimido y no registrado aún
    if not is_depressed.get(mid):
        return
    if recorded_attempts.get(mid):
        return

    stats.setdefault(mid, {})
    # incrementar contador de intentos
    stats[mid]["intentos_depresivos"] = stats[mid].get("intentos_depresivos", 0) + 1

    solo_secs = 0.0

    # Intentamos leer marcador desde time_entries (fechas.json) en la clave especial "_solo"
    # TODO
    if time_entries is not None:
        solo_container = time_entries.get("_solo", {})
        solo = solo_container.get(mid)
        if solo and solo.get("start_time"):
            try:
                solo_start = datetime.datetime.fromisoformat(solo["start_time"])
                now = datetime.datetime.now()
                solo_secs = (now - solo_start).total_seconds()
            except Exception:
                solo_secs = 0.0

            # borrar el marcador en time_entries y persistir
            try:
                del time_entries["_solo"][mid]
                if not time_entries.get("_solo"):
                    # si quedó vacío, quítalo del dict para mantener limpio el JSON
                    time_entries.pop("_solo", None)
                _, fechas_path = _get_paths(member)
                save_json(time_entries, fechas_path)
            except Exception:
                pass

    # Acumular el tiempo en stats
    stats[mid]["depressive_time"] = stats[mid].get("depressive_time", 0) + solo_secs

    # Guardar stats
    try:
        stats_path, _ = _get_paths(member)
        save_json(stats, stats_path)
    except Exception:
        pass

    # Marcar para que no se repita
    recorded_attempts[mid] = True

    # Log legible
    print(
        f"[{member.guild.name}] {member.display_name} ha tenido un episodio depresivo nuevo (total: {stats[mid]['intentos_depresivos']}). "
        f"Ha estado: {stats[mid]['depressive_time']:.2f} segundos solo en total."
    )


# ======================== #
#   MANEJO DE TIEMPO VC    #
# ======================== #
def save_time(time_entries, member, channel_member, enter=True):
    """Registra el inicio o fin de una sesión compartida entre dos usuarios."""
    import datetime

    current_time = datetime.datetime.now().isoformat()

    def ensure_entry(a, b):
        time_entries.setdefault(str(a.id), {}).setdefault(str(b.id), {"entries": []})

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


def calculate_total_time(time_entries, stats, member, channel_member):
    """Recalcula el tiempo total compartido entre dos usuarios.
    Se mantiene reciprocidad en stats."""

    from datetime import datetime

    mid, oid = str(member.id), str(channel_member.id)

    if mid not in time_entries or oid not in time_entries[mid]:
        return

    # Calcula tiempo nuevo desde las entradas activas
    new_total = sum(
        (
            datetime.fromisoformat(e["end_time"])
            - datetime.fromisoformat(e["start_time"])
        ).total_seconds()
        for e in time_entries[mid][oid]["entries"]
        if e["start_time"] and e["end_time"]
    )

    # suma al total previo
    stats.setdefault(mid, {}).setdefault(oid, {"total_shared_time": 0})
    stats.setdefault(oid, {}).setdefault(mid, {"total_shared_time": 0})

    prev_total = stats[mid][oid].get("total_shared_time", 0)
    total = prev_total + new_total

    stats[mid][oid]["total_shared_time"] = total
    stats[oid][mid]["total_shared_time"] = total

    # limpiar histórico ya consolidado
    time_entries[mid][oid]["entries"] = []
    time_entries[oid][mid]["entries"] = []

    _, fechas_path = _get_paths(member)
    save_json(time_entries, fechas_path)

    # guardar stats actualizado
    stats_path, _ = _get_paths(member)
    save_json(stats, stats_path)


# ======================== #
#      HISTORIAL CANAL     #
# ======================== #
def update_channel_history(historiales_por_canal, channel_id, cambio):
    """
    Actualiza el historial de miembros de un canal de voz.

    Parámetros:
    - historiales_por_canal: dict[int, list[int]]
        Diccionario que guarda por cada canal una lista con la cantidad
        de miembros a lo largo del tiempo.
    - channel_id: int
        ID del canal que se va a actualizar.
    - cambio: int
        +1 si un miembro entra, -1 si un miembro sale.
    """
    historiales_por_canal.setdefault(channel_id, [0])
    historiales_por_canal[channel_id].append(
        historiales_por_canal[channel_id][-1] + cambio
    )


# ======================== #
#       TEMPORIZADOR       #
# ======================== #
async def timer_task(member, is_depressed, timers, timeout=150, time_entries=None):
    """
    Marca un usuario como deprimido si permanece solo demasiado tiempo.
    Si se pasa time_entries, guarda en fechas.json (time_entries) la marca de solo_start.
    """
    time_left = timeout
    try:
        while time_left > 0:
            await asyncio.sleep(1)
            if time_left % 30 == 0 or time_left == timeout:
                print(
                    f"[{member.guild.name}] {member.display_name} se deprimirá en {time_left}s."
                )
            time_left -= 1

        mid = str(member.id)
        is_depressed[mid] = True

        # Guardamos el marcador en time_entries (fechas.json) para robustez local
        if time_entries is not None:
            from datetime import datetime

            # Estructura: time_entries["_solo"][mid] = {"start_time": iso, "channel_id": <id>}
            time_entries.setdefault("_solo", {})
            time_entries["_solo"][mid] = {
                "start_time": datetime.now().isoformat(),
                "channel_id": getattr(member.voice.channel, "id", None),
            }
            # persistir
            _, fechas_path = _get_paths(member)
            save_json(time_entries, fechas_path)

        print(
            f"[{member.guild.name}] {member.display_name} se ha marcado como deprimido (marcado en fechas.json)."
        )

    except asyncio.CancelledError:
        # se canceló antes de tiempo (timer cancelado)
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
    Solo se permite `stats.json`.
    """
    if filename != "stats.json":
        await interaction.response.send_message(
            "Solo se puede actualizar `stats.json`. Asegúrate de enviar el archivo con ese nombre.",
            ephemeral=True,
        )
        return False

    user = interaction.user
    origin_channel = interaction.channel

    # Aseguramos que exista un canal DM del usuario
    dm_channel = user.dm_channel or await user.create_dm()

    try:
        await interaction.followup.send(
            f"Por favor, envía stats.json **en este canal** o **por DM**. Tienes {timeout} segundos.",
            ephemeral=True,
        )
    except Exception:
        await user.send(
            f"Por favor, envía stats.json **por DM** al bot. Tienes {timeout} segundos.",
            ephemeral=True,
        )

    def check(message):
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

    try:
        message = await bot.wait_for("message", check=check, timeout=timeout)
        attachment = message.attachments[0]

        tmp_name = f"tmp_{user.id}_{attachment.filename}"
        await attachment.save(tmp_name)
        print(f"[DEBUG] Archivo guardado temporalmente como {tmp_name}")

        with open(tmp_name, "r", encoding="utf-8") as f:
            new_data = json.load(f)

        # Solo actualizamos stats.json
        stats_obj = global_vars.get("stats.json")
        if isinstance(stats_obj, dict):
            stats_obj.clear()
            stats_obj.update(new_data)
        else:
            global_vars["stats.json"] = new_data

        guild = interaction.guild
        write_path = os.path.join(str(guild.id), filename) if guild else filename
        os.makedirs(os.path.dirname(write_path) or ".", exist_ok=True)
        save_json(new_data, write_path)
        print(f"[DEBUG] JSON guardado en {write_path}")

        await interaction.followup.send(
            f"`{filename}` actualizado correctamente.", ephemeral=False
        )
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
        try:
            if tmp_name and os.path.exists(tmp_name):
                os.remove(tmp_name)
        except Exception:
            pass
        return False
