import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from passlib.context import CryptContext
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from database import get_db
from main import app

RAIZ = Path(__file__).resolve().parents[1]
PASSWORD = "secreto123"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Esquema REAL de la primera versión: lo generaba Base.metadata.create_all()
# antes de añadir ondelete="CASCADE", bio, token_version e icono. Las claves
# foráneas son simples (sin ON DELETE CASCADE), que es justo el caso que
# rompía el borrado de cuenta.
ESQUEMA_ANTIGUO = """
CREATE TABLE users (
    id INTEGER NOT NULL,
    nombre VARCHAR NOT NULL,
    email VARCHAR NOT NULL,
    hashed_password VARCHAR NOT NULL,
    avatar_color VARCHAR(7),
    created_at DATETIME,
    PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE INDEX ix_users_id ON users (id);
CREATE TABLE links (
    id INTEGER NOT NULL,
    url VARCHAR NOT NULL,
    titulo VARCHAR NOT NULL,
    user_id INTEGER NOT NULL,
    created_at DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE INDEX ix_links_id ON links (id);
CREATE INDEX ix_links_user_id ON links (user_id);
CREATE TABLE tags (
    id INTEGER NOT NULL,
    nombre VARCHAR NOT NULL,
    user_id INTEGER NOT NULL,
    created_at DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT uq_tags_usuario_nombre UNIQUE (user_id, nombre),
    FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE INDEX ix_tags_id ON tags (id);
CREATE INDEX ix_tags_nombre ON tags (nombre);
CREATE TABLE link_tags (
    link_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (link_id, tag_id),
    FOREIGN KEY(link_id) REFERENCES links (id),
    FOREIGN KEY(tag_id) REFERENCES tags (id)
);
"""


def _crear_base_antigua(ruta: Path) -> None:
    conexion = sqlite3.connect(ruta)
    conexion.executescript(ESQUEMA_ANTIGUO)
    conexion.execute(
        "INSERT INTO users (id, nombre, email, hashed_password) VALUES (?, ?, ?, ?)",
        (1, "Ana", "ana@ejemplo.com", pwd_context.hash(PASSWORD)),
    )
    conexion.execute(
        "INSERT INTO links (id, url, titulo, user_id) VALUES (1, 'https://react.dev', 'React', 1)"
    )
    conexion.execute("INSERT INTO tags (id, nombre, user_id) VALUES (1, 'Dev', 1)")
    conexion.execute("INSERT INTO link_tags (link_id, tag_id) VALUES (1, 1)")
    conexion.commit()
    conexion.close()


def _migrar(ruta: Path, monkeypatch) -> Config:
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{ruta.as_posix()}")
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    return cfg


def test_migracion_actualiza_una_base_de_datos_antigua(tmp_path, monkeypatch):
    ruta = tmp_path / "locker_antigua.db"
    _crear_base_antigua(ruta)
    cfg = _migrar(ruta, monkeypatch)

    conexion = sqlite3.connect(ruta)
    columnas_users = {fila[1] for fila in conexion.execute("PRAGMA table_info(users)")}
    columnas_tags = {fila[1] for fila in conexion.execute("PRAGMA table_info(tags)")}
    token_version = conexion.execute("SELECT token_version FROM users WHERE id = 1").fetchone()
    nombre_tag = conexion.execute("SELECT nombre FROM tags WHERE id = 1").fetchone()
    url_link = conexion.execute("SELECT url FROM links WHERE id = 1").fetchone()
    version = conexion.execute("SELECT version_num FROM alembic_version").fetchone()
    conexion.close()

    esperado = ScriptDirectory.from_config(cfg).get_current_head()

    # Se añadieron las columnas sin perder los datos existentes.
    assert {"bio", "token_version"} <= columnas_users
    assert "icono" in columnas_tags
    assert token_version == (1,)
    assert nombre_tag == ("Dev",)
    assert url_link == ("https://react.dev",)
    assert version == (esperado,)


def test_migracion_crea_una_base_de_datos_nueva(tmp_path, monkeypatch):
    ruta = tmp_path / "locker_nueva.db"
    _migrar(ruta, monkeypatch)

    conexion = sqlite3.connect(ruta)
    tablas = {fila[0] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    columnas_users = {fila[1] for fila in conexion.execute("PRAGMA table_info(users)")}
    columnas_tags = {fila[1] for fila in conexion.execute("PRAGMA table_info(tags)")}
    conexion.close()

    assert {"users", "links", "tags", "link_tags", "alembic_version"} <= tablas
    assert {"bio", "token_version"} <= columnas_users
    assert "icono" in columnas_tags


def test_borrar_cuenta_via_api_tras_migrar_una_base_antigua(tmp_path, monkeypatch):
    """La cuenta se borra aunque la BD venga de la v1 con FK sin CASCADE.

    Sin quitar ``passive_deletes=True`` de las relaciones de ``User``, SQLite
    conserva los links/tags (la FK no tiene ON DELETE CASCADE) y el DELETE
    termina en IntegrityError (500).
    """
    ruta = tmp_path / "locker_v1.db"
    _crear_base_antigua(ruta)
    _migrar(ruta, monkeypatch)

    engine = create_engine(f"sqlite:///{ruta.as_posix()}")

    @event.listens_for(engine, "connect")
    def _activar_fk(conexion_dbapi, _registro):
        conexion_dbapi.execute("PRAGMA foreign_keys=ON")

    Session = sessionmaker(bind=engine)

    def _sesion_de_prueba():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _sesion_de_prueba
    try:
        with TestClient(app, client=("127.0.0.1", 50000)) as cliente:
            login = cliente.post(
                "/auth/login", json={"email": "ana@ejemplo.com", "password": PASSWORD}
            )
            assert login.status_code == 200, login.text
            token = login.json()["access_token"]

            borrado = cliente.request(
                "DELETE",
                "/auth/cuenta",
                json={"password": PASSWORD},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert borrado.status_code == 204, borrado.text
    finally:
        app.dependency_overrides.pop(get_db, None)

    with engine.connect() as conexion:
        for tabla in ("users", "links", "tags", "link_tags"):
            assert conexion.execute(text(f"SELECT count(*) FROM {tabla}")).scalar() == 0, tabla
    engine.dispose()
