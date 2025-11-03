import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, Integer, JSON, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from dotenv import load_dotenv
from bot.utils.json_manager import load_json

# ---------------- Cargar .env ----------------
load_dotenv()

# ---------------- Configuración Postgres ----------------
POSTGRES_USER = os.getenv("DATABASE_USER")
POSTGRES_PASSWORD = os.getenv("DATABASE_PASSWORD")
POSTGRES_HOST = os.getenv("DATABASE_HOST")
POSTGRES_PORT = os.getenv("DATABASE_PORT", "5432")
POSTGRES_DB = os.getenv("DATABASE_NAME")

# Validar variables
if not all([POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_DB]):
    raise ValueError(
        "Faltan variables de entorno de la base de datos. "
        "Revisa tu .env y asegúrate de tener DATABASE_USER, DATABASE_PASSWORD, DATABASE_HOST y DATABASE_NAME definidos."
    )

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# ---------------- Crear motor y sesión ----------------
try:
    engine = create_engine(DATABASE_URL, echo=False, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
except Exception as e:
    raise ConnectionError(f"No se pudo conectar a PostgreSQL: {e}")

Base = declarative_base()


# ---------------- Modelo ----------------
class JSONData(Base):
    __tablename__ = "json_data"
    id = Column(Integer, primary_key=True, index=True)
    data = Column(JSON, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


# ---------------- Crear tablas ----------------
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    raise RuntimeError(f"Error creando tablas en PostgreSQL: {e}")

# ---------------- FastAPI ----------------
app = FastAPI()


@app.post("/save-json")
async def save_json_endpoint():
    data = load_json()  # tu función existente
    if not data:
        return {"error": "JSON vacío o no encontrado"}

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
        record = session.query(JSONData).order_by(JSONData.created_at.desc()).first()
        if record:
            return JSONResponse(content=record.data)
        return {"error": "No hay datos guardados"}
    finally:
        session.close()
