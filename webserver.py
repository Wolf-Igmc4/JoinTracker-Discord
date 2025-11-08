# webserver.py

import os
from datetime import datetime
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, Integer, JSON, TIMESTAMP, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from pydantic import BaseModel
from src.utils.helpers import stringify_keys

# ---------------- Cargar variables de entorno ----------------
load_dotenv()  # carga .env
API_KEY = os.getenv("API_KEY")

POSTGRES_USER = os.getenv("DATABASE_USER")
POSTGRES_PASSWORD = os.getenv("DATABASE_PASSWORD")
POSTGRES_HOST = os.getenv("DATABASE_HOST")
POSTGRES_PORT = os.getenv("DATABASE_PORT", "5432")
POSTGRES_DB = os.getenv("DATABASE_NAME")

if not all([POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_DB]):
    raise ValueError(
        "Faltan variables de entorno de la base de datos. "
        "Asegúrate de tener DATABASE_USER, DATABASE_PASSWORD, DATABASE_HOST y DATABASE_NAME."
    )

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# ---------------- SQLAlchemy Setup ----------------
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# ---------------- Modelo de tabla ----------------
# ahora incluimos guild_id para poder filtrar por servidor
class JSONData(Base):
    __tablename__ = "json_data"
    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, index=True, nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


# crear tabla si no existe
Base.metadata.create_all(bind=engine)

# ---------------- Instancia FastAPI ----------------
app = FastAPI()


# ---------------- Modelos de entrada ----------------
class Payload(BaseModel):
    guild_id: str
    data: dict


# ---------------- Endpoints ----------------
@app.post("/save-json")
async def save_json_endpoint(payload: Payload, x_api_key: str = Header(None)):
    # Verificación de la clave API para autenticar al cliente y prevenir accesos no autorizados
    if API_KEY is None or x_api_key != API_KEY:
        print("Las claves no coinciden.")
        raise HTTPException(status_code=401, detail="Unauthorized")

    session = SessionLocal()
    ts = None  # Timestamp del registro creado
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


@app.get("/stats/{guild_id}")
async def get_guild_stats(guild_id: str, x_api_key: str = Header(None)):
    """
    Devuelve el último JSON guardado para el servidor indicado.
    Protegido por API key (x-api-key).
    """
    if API_KEY is None or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    session = SessionLocal()
    try:
        record = (
            session.query(JSONData)
            .filter_by(guild_id=guild_id)
            .order_by(JSONData.created_at.desc())
            .first()
        )
        if record:
            return JSONResponse(content=record.data)
        return {"error": "No hay datos guardados aún para este servidor."}
    finally:
        session.close()
