from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import config
from database import Base, engine
import models
from routers import auth, links, tags

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Locker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origen.strip() for origen in config.CORS_ORIGINS.split(",") if origen.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/", tags=["General"])
def raiz():
    return {"message": "Bienvenido a la Locker API", "docs": "/docs"}


@app.get("/health", tags=["General"])
def health():
    """Endpoint de verificación de estado del servidor."""
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(links.router)
app.include_router(tags.router)
