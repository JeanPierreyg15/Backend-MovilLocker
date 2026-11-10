import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

RAIZ = Path(__file__).resolve().parents[1]

ESQUEMA_ANTIGUO = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    nombre VARCHAR NOT NULL,
    email VARCHAR NOT NULL,
    hashed_password VARCHAR NOT NULL,
    avatar_color VARCHAR(7),
    created_at DATETIME
);
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE TABLE links (
    id INTEGER PRIMARY KEY,
    url VARCHAR NOT NULL,
    titulo VARCHAR NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at DATETIME
);
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    nombre VARCHAR NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at DATETIME,
    CONSTRAINT uq_tags_usuario_nombre UNIQUE (user_id, nombre)
);
CREATE TABLE link_tags (
    link_id INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (link_id, tag_id)
);
INSERT INTO users (id, nombre, email, hashed_password) VALUES
    (1, 'Ana', 'ana@ejemplo.com', 'hash');
INSERT INTO tags (id, nombre, user_id) VALUES (1, 'Dev', 1);
"""


def test_migracion_actualiza_una_base_de_datos_antigua(tmp_path, monkeypatch):
    ruta = tmp_path / "locker_antigua.db"
    conexion = sqlite3.connect(ruta)
    conexion.executescript(ESQUEMA_ANTIGUO)
    conexion.close()

    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{ruta.as_posix()}")
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

    conexion = sqlite3.connect(ruta)
    columnas_users = {fila[1] for fila in conexion.execute("PRAGMA table_info(users)")}
    columnas_tags = {fila[1] for fila in conexion.execute("PRAGMA table_info(tags)")}
    token_version = conexion.execute("SELECT token_version FROM users WHERE id = 1").fetchone()
    nombre_tag = conexion.execute("SELECT nombre FROM tags WHERE id = 1").fetchone()
    version = conexion.execute("SELECT version_num FROM alembic_version").fetchone()
    conexion.close()

    # Se añadieron las columnas sin perder los datos existentes.
    assert {"bio", "token_version"} <= columnas_users
    assert "icono" in columnas_tags
    assert token_version == (1,)
    assert nombre_tag == ("Dev",)
    assert version == ("0002_columnas_perfil",)


def test_migracion_crea_una_base_de_datos_nueva(tmp_path, monkeypatch):
    ruta = tmp_path / "locker_nueva.db"

    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{ruta.as_posix()}")
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

    conexion = sqlite3.connect(ruta)
    tablas = {fila[0] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    columnas_users = {fila[1] for fila in conexion.execute("PRAGMA table_info(users)")}
    columnas_tags = {fila[1] for fila in conexion.execute("PRAGMA table_info(tags)")}
    conexion.close()

    assert {"users", "links", "tags", "link_tags", "alembic_version"} <= tablas
    assert {"bio", "token_version"} <= columnas_users
    assert "icono" in columnas_tags
