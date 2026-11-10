from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from config import config


class Base(DeclarativeBase):
    """Clase base moderna de SQLAlchemy 2.0 para los modelos."""


def _argumentos_sqlite() -> dict:
    if config.DATABASE_URL.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine = create_engine(config.DATABASE_URL, connect_args=_argumentos_sqlite())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
