# webserver.py

import os
import hmac
import hashlib
from datetime import datetime
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Depends
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, JSON, TIMESTAMP, String
from sqlalchemy.ext.declarative import declarative_base

import src.bot_instance as bot_instance
from src.utils.helpers import sync_all_guilds
from src.utils.data_handler import stringify_keys

# ========= Cargar variables de entorno =========
load_dotenv()  # carga .env
API_KEY = os.getenv("API_KEY")
GITHUB_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

POSTGRES_USER = os.getenv("DATABASE_USER")
POSTGRES_PASSWORD = os.getenv("DATABASE_PASSWORD")
POSTGRES_HOST = os.getenv("DATABASE_HOST")
POSTGRES_PORT = os.getenv("DATABASE_PORT", "5432")
POSTGRES_DB = os.getenv("DATABASE_NAME")
DATABASE_SSLMODE = os.getenv("DATABASE_SSLMODE")
if not all([POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_DB]):
    raise ValueError(
        "Faltan variables de entorno de la base de datos. "
        "Asegúrate de tener DATABASE_USER, DATABASE_PASSWORD, DATABASE_HOST y DATABASE_NAME."
    )
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}?{DATABASE_SSLMODE}"

# ========= Inicio de SQLAlchemy =========
engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    # Habilita el chequeo de salud de la conexión antes de usarla (Evita el error de conexión cerrada)
    pool_pre_ping=True,
    # Opcional: Recicla conexiones cada hora (3600s) para evitar timeouts del lado del servidor
    pool_recycle=3600,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# ========= Modelo de tabla =========
# ahora incluimos guild_id para poder filtrar por servidor
class JSONData(Base):
    __tablename__ = "json_data"
    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, index=True, nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


# Crear tabla si no existe
Base.metadata.create_all(bind=engine)


# ========= Modelos de entrada =========
class Payload(BaseModel):
    guild_id: str
    data: dict


# ========= Funciones auxiliares =========
def verify_github_signature(body: bytes, signature_header: str) -> bool:
    """Verifica la firma HMAC-SHA256 enviada por GitHub."""
    if not signature_header:
        return False

    sha_name, signature = signature_header.split("=", 1)
    if sha_name != "sha256":
        return False

    mac = hmac.new(GITHUB_SECRET.encode(), msg=body, digestmod=hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), signature)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ARRANQUE DE BOT
    yield
    # APAGADO DE BOT
    print("\n🚨 [LIFESPAN] Apagado iniciado.")
    try:
        if bot_instance.bot and bot_instance.bot.is_ready():
            # force=False: Si el webhook guardó hace poco, no se guardan datos.
            sent = await sync_all_guilds(bot_instance.bot, force=False)
            print(f"✅ [LIFESPAN] Apagado completado. Servidores sincronizados: {sent}")
        else:
            print("⚠️ Bot no listo, saltando guardado.")
    except Exception as e:
        print(f"❌ Error crítico en cierre: {e}")


# ========= Instancia FastAPI =========
app = FastAPI(lifespan=lifespan)


# ========= Endpoints =========
@app.post("/save-json")
# 1. Inyectamos la dependencia aquí. FastAPI llama a get_db, obtiene la sesión y te la da en 'db'
async def save_json_endpoint(
    payload: Payload, x_api_key: str = Header(None), db: Session = Depends(get_db)
):
    if API_KEY is None or x_api_key != API_KEY:
        print("Las claves no coinciden.")
        raise HTTPException(status_code=401, detail="Unauthorized")

    ts = None

    try:
        safe_data = stringify_keys(payload.data)
        if safe_data != payload.data:
            print(f"\033[93m[WEB][WARN] Sanitizado payload...\033[0m")

        record = JSONData(guild_id=payload.guild_id, data=safe_data)
        db.add(record)
        db.commit()
        db.refresh(record)

        ts = record.created_at
        print(f"\033[92m[WEB] ✅ Commit realizado...\033[0m")

    except Exception as e:
        db.rollback()
        print(f"\033[91m[WEB] ⚠️ Cambios revertidos...\033[0m")
        raise HTTPException(status_code=500, detail=f"No se pudo guardar el JSON: {e}")

    try:
        return {
            "status": "guardado",
            "guild": payload.guild_id,
            "timestamp": ts.isoformat() if ts else None,
        }
    except Exception as e:
        print(f"\033[93m[WEB][WARN] No se pudo construir la respuesta...\033[0m")
        return {"status": "guardado", "guild": payload.guild_id, "timestamp": None}


@app.post("/github-webhook")
async def github_webhook(request: Request):
    """Webhook que GitHub llama al hacer push. Dispara un volcado de stats automático."""
    # Verificar firma de GitHub
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not verify_github_signature(body, signature):
        raise HTTPException(status_code=401, detail="Firma de GitHub no válida.")

    payload = await request.json()

    # Verificar evento push
    event_type = request.headers.get("X-GitHub-Event")
    if event_type != "push":
        return {"status": "ignored", "reason": "not a push event"}

    # Ejecutar volcado
    print(
        f"\033[93m[GITHUB] Detectado push en GitHub. Volcado automático iniciado.\033[0m"
    )

    sent = await sync_all_guilds(bot_instance.bot, force=False)

    print(
        f"\033[93m[GITHUB] ✅ Volcado automático completado. Servidores sincronizados: {sent}\033[0m"
    )

    return {
        "status": "ok",
        "synced_guilds": sent,
        "repo": payload.get("repository", {}).get("full_name"),
        "ref": payload.get("ref"),
    }


@app.get("/stats/{gid}")
async def get_guild_stats(
    gid: str,
    x_api_key: str = Header(None),
    db: Session = Depends(get_db),
):
    if API_KEY is None or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    record = (
        db.query(JSONData)
        .filter_by(guild_id=gid)
        .order_by(JSONData.created_at.desc())
        .first()
    )

    if record:
        response_content = {
            "data": record.data,
            "created_at": (
                record.created_at.isoformat() if record.created_at else None
            ),
        }
        return response_content

    return {"error": "No hay datos guardados aún para este servidor."}
