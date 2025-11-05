# utils/dbsync.py
# src/utils/dbsync.py
import json
import os
import time
from collections import defaultdict
from typing import Dict, Tuple
import psycopg2
from psycopg2.extras import execute_values

# ---------- Configurable ----------
# Path base donde guardas carpetas por guild (igual que ahora)
# por ejemplo: "data/" -> dentro cada carpeta "GUILD_ID/datos.json"
DEFAULT_BASE_PATH = "data"
# ----------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jointracker_totals (
    guild_id      TEXT    NOT NULL,
    user_id       TEXT    NOT NULL,
    partner_id    TEXT    NOT NULL,
    total_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, partner_id)
);
"""


class DBSync:
    """
    Clase que maneja:
      - carga inicial desde Postgres (pull completo por guild)
      - cache local (totals.json)
      - acumulación de cambios en memoria + pending.json
      - sync en batch con Postgres (push)
    """

    def __init__(
        self, database_url: str, guild_id: str, base_path: str = DEFAULT_BASE_PATH
    ):
        self.database_url = database_url
        self.guild_id = str(guild_id)
        self.base_path = os.path.join(base_path, self.guild_id)
        os.makedirs(self.base_path, exist_ok=True)

        # archivos locales
        self.totals_path = os.path.join(self.base_path, "totals.json")
        self.pending_path = os.path.join(self.base_path, "pending.json")

        # estructura en memoria:
        # totals: { user_id: { partner_id: total_seconds } }
        self.totals: Dict[str, Dict[str, float]] = {}
        # pending raw list (se puede reconstruir desde pending.json)
        # each entry: (user_id, partner_id, seconds)
        self.pending: list[Tuple[str, str, float]] = []

        # cargar lo local (si existe)
        self._load_local_files()

    # ---------- Local file helpers ----------
    def _load_local_files(self):
        if os.path.exists(self.totals_path):
            try:
                with open(self.totals_path, "r", encoding="utf-8") as f:
                    self.totals = json.load(f)
            except Exception:
                self.totals = {}
        else:
            self.totals = {}

        if os.path.exists(self.pending_path):
            try:
                with open(self.pending_path, "r", encoding="utf-8") as f:
                    self.pending = json.load(f)
            except Exception:
                self.pending = []
        else:
            self.pending = []

    def _save_local_files(self):
        # totals
        with open(self.totals_path, "w", encoding="utf-8") as f:
            json.dump(self.totals, f, ensure_ascii=False, indent=2)
        # pending
        with open(self.pending_path, "w", encoding="utf-8") as f:
            json.dump(self.pending, f, ensure_ascii=False)

    # ---------- Remote (Postgres) helpers ----------
    def _connect(self):
        """Devuelve una conexión psycopg2 (usa DATABASE_URL style)."""
        return psycopg2.connect(self.database_url, sslmode="prefer")

    def ensure_table_exists(self):
        conn = self._connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(CREATE_TABLE_SQL)
        finally:
            conn.close()

    def load_remote_initial(self):
        """
        Lectura completa desde Postgres para ESTE guild.
        Sobrescribe o crea self.totals local con lo remoto.
        Uso previsto: llamado una vez al arrancar (cold start).
        """
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id, partner_id, total_seconds "
                    "FROM jointracker_totals WHERE guild_id = %s",
                    (self.guild_id,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        # convertir a dict anidado
        totals: Dict[str, Dict[str, float]] = {}
        for user_id, partner_id, total_seconds in rows:
            totals.setdefault(str(user_id), {})[str(partner_id)] = float(total_seconds)

        self.totals = totals
        # vaciamos pending (suponemos que lo remoto ya está correcto)
        self.pending = []
        self._save_local_files()

    # ---------- Public API ----------
    def add_time(self, user_id: str, partner_id: str, seconds: float):
        """
        Añade `seconds` de tiempo entre user_id y partner_id en cache local
        y registra en pending para el próximo sync. Actualiza SIMÉTRICAMENTE.
        """
        u = str(user_id)
        p = str(partner_id)
        s = float(seconds)

        # update local totals (sym)
        self.totals.setdefault(u, {})
        self.totals[u][p] = self.totals[u].get(p, 0.0) + s

        self.totals.setdefault(p, {})
        self.totals[p][u] = self.totals[p].get(u, 0.0) + s

        # append to pending both directions (podemos agregarlos en sync)
        self.pending.append((u, p, s))
        self.pending.append((p, u, s))

        # keep local files reasonably up to date (cheap)
        self._save_local_files()

    def get_total(self, user_id: str, partner_id: str) -> float:
        return float(self.totals.get(str(user_id), {}).get(str(partner_id), 0.0))

    def aggregate_pending(self) -> Dict[Tuple[str, str], float]:
        """
        Agrupa pending para reducir filas a actualizar en Postgres.
        Devuelve un dict {(user,partner): seconds_sum}
        """
        agg = defaultdict(float)
        for u, p, s in self.pending:
            agg[(u, p)] += s
        return agg

    def sync_with_remote(self):
        """
        Hace el push en batch:
         - agrupa pending
         - abre UNA conexión
         - ejecuta un INSERT ... ON CONFLICT DO UPDATE para cada par
         - limpia pending y guarda local
        """
        if not self.pending:
            return {"updated_rows": 0, "message": "No pending changes"}

        agg = self.aggregate_pending()
        rows = []
        for (u, p), s in agg.items():
            # sólo filas con delta > 0
            if s:
                rows.append((self.guild_id, u, p, s))

        if not rows:
            # nothing to do
            self.pending = []
            self._save_local_files()
            return {"updated_rows": 0, "message": "No positive deltas"}

        conn = self._connect()
        updated = 0
        try:
            with conn:
                with conn.cursor() as cur:
                    # usamos execute_values para montar un VALUES (...) bulk
                    sql = """
                    INSERT INTO jointracker_totals (guild_id, user_id, partner_id, total_seconds)
                    VALUES %s
                    ON CONFLICT (guild_id, user_id, partner_id)
                    DO UPDATE SET total_seconds = jointracker_totals.total_seconds + EXCLUDED.total_seconds
                    ;
                    """
                    execute_values(cur, sql, rows, template=None, page_size=100)
                    updated = len(rows)
        finally:
            conn.close()

        # si todo OK, limpiamos pending (ya están reflejados) y guardamos totals locales
        self.pending = []
        self._save_local_files()
        return {"updated_rows": updated, "message": "Sync ok"}

    # utilidad: forzar guardar sólo totals locales (sin tocar postgres)
    def persist_local(self):
        self._save_local_files()

    # debug friendly
    def info(self):
        pending_count = len(self.pending)
        totals_pairs = sum(len(v) for v in self.totals.values())
        return {
            "guild_id": self.guild_id,
            "pending_count": pending_count,
            "total_pairs": totals_pairs,
        }


# ---------------- Example usage ----------------
#
# from src.utils.dbsync import DBSync
#
# db = DBSync(os.environ["DATABASE_URL"], guild_id="123456789")
# db.ensure_table_exists()
# db.load_remote_initial()   # llamar una sola vez al arrancar (pull completo)
#
# # en eventos del bot:
# db.add_time(user_id, partner_id, seconds)   # acumula local y pending
#
# # cuando quieras sincronizar (cron, on-demand, nightly), llama:
# result = db.sync_with_remote()
# print(result)
#
# ------------------------------------------------
