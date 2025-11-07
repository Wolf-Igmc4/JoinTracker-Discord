# webserver.py

import os
from sqlalchemy.exc import OperationalError
from datetime import datetime
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, Integer, JSON, TIMESTAMP, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from pydantic import BaseModel

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
    if API_KEY is None or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    session = SessionLocal()
    try:
        print(
            "[DEBUG][WEB] type(payload.guild_id):",
            type(payload.guild_id),
            "guild_id:",
            payload.guild_id,
        )

        record = JSONData(guild_id=payload.guild_id, data=payload.data)
        session.add(record)
        session.commit()

        ts = record.created_at

        print(f"[WEB] Guardados los datos del servidor {payload.guild_id}. Fecha: {ts}")

        return {
            "status": "guardado",
            "guild": payload.guild_id,
            "timestamp": ts.isoformat(),
        }

    except Exception as e:
        session.rollback()
        return {"error": f"No se pudo guardar el JSON: {e}"}
    finally:
        session.close()


@app.get("/stats/{guild_id}")
async def get_guild_stats(guild_id: str, x_api_key: str = Header(None)):
    """
    Devuelve el último JSON guardado para la guild indicada.
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
        return {"error": "no hay datos guardados aún para esta guild"}
    finally:
        session.close()
