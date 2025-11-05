# bot/webserver.py
import os
from sqlalchemy.exc import OperationalError
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, Integer, JSON, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from src.utils.json_manager import load_json

# ---------------- Cargar variables de entorno ----------------
load_dotenv()

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

# ---------------- Crear motor y sesión ----------------
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# ---------------- Modelo de tabla ----------------
class JSONData(Base):
    __tablename__ = "json_data"
    id = Column(Integer, primary_key=True, index=True)
    data = Column(JSON, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


# Crear tablas si no existen
Base.metadata.create_all(bind=engine)

# ---------------- Instancia FastAPI ----------------
app = FastAPI()


# ---------------- Endpoints ----------------
@app.post("/save-json")
async def save_json_endpoint(request: Request):
    """
    Guarda el JSON del bot en PostgreSQL.
    Espera un query param opcional ?filename=datos.json para indicar qué JSON guardar.
    """
    filename = request.query_params.get("filename", "datos.json")
    data = load_json(filename)
    if not data:
        return JSONResponse({"error": "JSON vacío o no encontrado"})

    session = SessionLocal()
    try:
        record = JSONData(data=data)
        session.add(record)
        session.commit()
        return {"status": "guardado", "timestamp": datetime.utcnow()}
    except Exception as e:
        session.rollback()
        return {"error": f"No se pudo guardar el JSON: {e}"}
    finally:
        session.close()


@app.get("/download-json")
async def download_json_endpoint():
    session = SessionLocal()
    try:
        try:
            record = (
                session.query(JSONData).order_by(JSONData.created_at.desc()).first()
            )
        except OperationalError as e:
            print(f"[DB][ERROR] OperationalError: {e}")
            return JSONResponse({"error": "DB error, try later"}, status_code=503)
        if record:
            return JSONResponse(content=record.data)
        return {"error": "No hay datos guardados"}
    finally:
        session.close()
