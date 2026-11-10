import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import config
from database import Base, engine, get_db
import models  # noqa: F401  (registra los modelos antes de create_all)
from routers import auth, links, tags

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("locker")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Locker API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.origenes_cors,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/", tags=["General"])
def raiz():
    return {"message": "Bienvenido a la Locker API", "docs": "/docs"}


@app.get("/health", tags=["General"])
def health(db: Session = Depends(get_db)):
    """Healthcheck real: comprueba también que la base de datos responde."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


app.include_router(auth.router)
app.include_router(links.router)
app.include_router(tags.router)

logger.info("Locker API iniciada (debug=%s)", config.DEBUG)
