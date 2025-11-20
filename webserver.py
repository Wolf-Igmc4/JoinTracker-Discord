# webserver.py

import os
import hmac
import hashlib
from datetime import datetime
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, JSON, TIMESTAMP, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import src.bot_instance as bot_instance
from src.utils.helpers import stringify_keys, sync_all_guilds

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
engine = create_engine(DATABASE_URL, echo=False, future=True)
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


# crear tabla si no existe
Base.metadata.create_all(bind=engine)

# ========= Instancia FastAPI =========
app = FastAPI()


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ARRANQUE DE BOT
    yield
    # APAGADO DE BOT
    print("\n🚨 [LIFESPAN] Apagado iniciado. Verificando datos pendientes...")
    try:
        if bot_instance.bot and bot_instance.bot.is_ready():
            # force=False: Si el webhook guardó hace poco, no se guardan datos.
            await sync_all_guilds(bot_instance.bot, force=False)
        else:
            print("⚠️ Bot no listo, saltando guardado.")
    except Exception as e:
        print(f"❌ Error crítico en cierre: {e}")


app = FastAPI(lifespan=lifespan)


# ========= Endpoints =========
@app.post("/save-json")
async def save_json_endpoint(payload: Payload, x_api_key: str = Header(None)):
    # Verificación de la clave API para autenticar al cliente y prevenir accesos no autorizados
    if API_KEY is None or x_api_key != API_KEY:
        print("Las claves no coinciden.")
        raise HTTPException(status_code=401, detail="Unauthorized")

    session = SessionLocal()
    ts = None  # Timestamp del registro
    try:
        # Sanitización de las claves del JSON para garantizar que sean cadenas
        safe_data = stringify_keys(payload.data)
        if safe_data != payload.data:
            print(
                f"\033[93m[WEB][WARN] Sanitizado payload.data para servidor {payload.guild_id} (claves no-str convertidas).\033[0m"
            )

        # Creación y adición del registro a la sesión de la base de datos
        record = JSONData(guild_id=payload.guild_id, data=safe_data)
        session.add(record)
        session.commit()
        ts = record.created_at
        print(
            f"\033[92m[WEB] ✅ Commit realizado: datos del servidor {payload.guild_id} guardados correctamente. Fecha: {ts}\033[0m"
        )

    except Exception as e:
        # En caso de error, revertir cambios para mantener la integridad de la base de datos
        session.rollback()
        print(
            f"\033[91m[WEB] ⚠️ Cambios revertidos para servidor {payload.guild_id} debido a error: {e}\033[0m"
        )
        raise HTTPException(status_code=500, detail=f"No se pudo guardar el JSON: {e}")

    finally:
        # Cierre de la sesión de base de datos para liberar recursos
        session.close()

    # Construcción de la respuesta JSON fuera del bloque try principal
    # Garantiza que la respuesta no afecte el guardado de los datos
    try:
        return {
            "status": "guardado",
            "guild": payload.guild_id,
            "timestamp": ts.isoformat() if ts else None,
        }
    except Exception as e:
        # Fallback de respuesta en caso de error; los datos ya están persistidos
        print(
            f"\033[93m[WEB][WARN] No se pudo construir la respuesta JSON para {payload.guild_id}: {e}\033[0m"
        )
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
async def get_guild_stats(gid: str, x_api_key: str = Header(None)):
    """
    Devuelve el último JSON guardado junto con su timestamp.
    Estructura de respuesta: {"data": {...}, "created_at": "ISO_TIMESTAMP"}
    """
    if API_KEY is None or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    session = SessionLocal()
    try:
        record = (
            session.query(JSONData)
            .filter_by(guild_id=gid)
            .order_by(JSONData.created_at.desc())
            .first()
        )
        if record:
            # Construimos una respuesta compuesta (Wrapper)
            response_content = {
                "data": record.data,
                # Serializamos la fecha a formato ISO 8601 (string) para el JSON
                "created_at": (
                    record.created_at.isoformat() if record.created_at else None
                ),
            }
            return JSONResponse(content=response_content)

        return {"error": "No hay datos guardados aún para este servidor."}
    finally:
        session.close()
