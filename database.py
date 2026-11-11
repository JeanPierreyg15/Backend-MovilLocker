from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import config


class Base(DeclarativeBase):
    """Clase base moderna de SQLAlchemy 2.0 para los modelos."""


def _argumentos_sqlite() -> dict:
    return {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}


engine = create_engine(config.DATABASE_URL, connect_args=_argumentos_sqlite())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


if config.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _activar_claves_foraneas(conexion_dbapi, _registro):
        """SQLite ignora las FK (y sus ON DELETE CASCADE) si no se activan por conexión."""
        cursor = conexion_dbapi.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            # WAL permite leer mientras se escribe (varias peticiones a la vez).
            cursor.execute("PRAGMA journal_mode=WAL")
            # En vez de fallar al instante si la BD está ocupada, espera 5 s.
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


def get_db():
    """Entrega una sesión de BD por petición y siempre la cierra / deshace en error."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
