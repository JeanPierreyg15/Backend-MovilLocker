import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import config
from database import get_db
import models  # noqa: F401  (registra los modelos para las migraciones)
from routers import auth, links, tags

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("locker")

RAIZ = Path(__file__).resolve().parent


def _ruta_lock_migraciones() -> Path:
    """Lock junto a la base SQLite (compartido por los workers del mismo host)."""
    prefijo = "sqlite:///"
    if config.DATABASE_URL.startswith(prefijo):
        ruta_db = config.DATABASE_URL[len(prefijo):]
        if ruta_db and ruta_db != ":memory:":
            return Path(ruta_db).resolve().parent / ".locker-migraciones.lock"
    return RAIZ / ".locker-migraciones.lock"


def _bloquear_migraciones(ruta: Path):
    """Lock exclusivo entre procesos (msvcrt en Windows, fcntl en POSIX)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    archivo = open(ruta, "a+", encoding="utf-8")
    try:
        archivo.write(" ")
        archivo.flush()
        archivo.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(archivo.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(archivo.fileno(), fcntl.LOCK_EX)
    except Exception:
        archivo.close()
        raise
    return archivo


def _desbloquear_migraciones(archivo) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            archivo.seek(0)
            msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(archivo.fileno(), fcntl.LOCK_UN)
    finally:
        archivo.close()


def ejecutar_migraciones() -> None:
    """Aplica `alembic upgrade head` al arrancar la app.

    El lock evita que varios workers arranquen la migración a la vez. Aun así,
    en producción se recomienda desactivar ``AUTO_MIGRATE`` y ejecutar
    ``alembic upgrade head`` como paso único de despliegue.
    """
    archivo_lock = _bloquear_migraciones(_ruta_lock_migraciones())
    try:
        cfg = AlembicConfig(str(RAIZ / "alembic.ini"))
        cfg.set_main_option("script_location", str(RAIZ / "alembic"))
        cfg.attributes["configure_logger"] = False  # no pisar el logging de uvicorn
        command.upgrade(cfg, "head")
    finally:
        _desbloquear_migraciones(archivo_lock)


def _origen_local(origen: str) -> bool:
    partes = urlparse(origen)
    if partes.scheme == "capacitor":
        return True
    return partes.hostname in {"localhost", "127.0.0.1", "::1"}


def auditar_configuracion() -> None:
    """Advertencias ruidosas para configuraciones peligrosas."""
    if config.DEBUG:
        no_locales = [origen for origen in config.origenes_cors if not _origen_local(origen)]
        if no_locales:
            logger.warning(
                "!!! DEBUG=true con orígenes CORS no locales (%s). "
                "En producción DEBUG debe ser false.",
                ", ".join(no_locales),
            )
        if not config.smtp_configurado:
            logger.warning(
                "DEBUG=true sin SMTP: el código de recuperación solo se devuelve "
                "a peticiones desde loopback."
            )
    elif not config.smtp_configurado:
        logger.warning(
            "SMTP no configurado: la recuperación de contraseña no podrá enviar "
            "correos en producción. Define SMTP_HOST y SMTP_FROM (o SMTP_USER)."
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if config.AUTO_MIGRATE:
        try:
            ejecutar_migraciones()
        except Exception as error:
            # Mejor no arrancar que servir una API con el esquema roto.
            logger.exception("No se pudieron aplicar las migraciones de la base de datos")
            raise RuntimeError(
                "No se pudieron aplicar las migraciones. Revisa el log o ejecuta "
                "`alembic upgrade head` manualmente."
            ) from error
    auditar_configuracion()
    logger.info("Locker API iniciada (debug=%s, migraciones=%s)", config.DEBUG, config.AUTO_MIGRATE)
    yield


app = FastAPI(title="Locker API", version="1.2.0", lifespan=lifespan)


@app.middleware("http")
async def registrar_peticion(request: Request, call_next):
    """Log de una línea por petición, sin cuerpos ni cabeceras sensibles."""
    inicio = time.perf_counter()
    try:
        respuesta = await call_next(request)
    except Exception:
        duracion = (time.perf_counter() - inicio) * 1000
        logger.error(
            "Petición %s %s falló tras %.1f ms",
            request.method,
            request.url.path,
            duracion,
        )
        raise
    duracion = (time.perf_counter() - inicio) * 1000
    logger.info(
        "%s %s -> %s (%.1f ms)",
        request.method,
        request.url.path,
        respuesta.status_code,
        duracion,
    )
    return respuesta


@app.exception_handler(Exception)
async def manejar_error_inesperado(request: Request, exc: Exception):
    """Registra la traza y devuelve un JSON genérico, sin filtrar detalles."""
    logger.exception(
        "Error no controlado en %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"},
    )


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
