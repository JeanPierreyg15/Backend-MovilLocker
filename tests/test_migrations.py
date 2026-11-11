import sqlite3
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from database import Base
import models  # noqa: F401  (registra todas las tablas)

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
    assert {"icono", "nombre_normalizado"} <= columnas_tags
    assert token_version == (1,)
    assert nombre_tag == ("Dev",)
    assert version == ("0005_urls_canonicas",)


def test_migracion_resuelve_etiquetas_duplicadas_por_acentos(tmp_path, monkeypatch):
    ruta = tmp_path / "locker_duplicados.db"
    conexion = sqlite3.connect(ruta)
    conexion.executescript(ESQUEMA_ANTIGUO)
    conexion.executescript(
        """
        INSERT INTO tags (id, nombre, user_id) VALUES
            (2, 'Educación', 1),
            (3, 'EDUCACIÓN', 1),
            (4, 'Ñandú', 1),
            (5, 'ñandú', 1);
        """
    )
    conexion.close()

    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{ruta.as_posix()}")
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    # Idempotente: volver a ejecutar no debe fallar ni cambiar datos.
    command.upgrade(cfg, "head")

    conexion = sqlite3.connect(ruta)
    filas = conexion.execute(
        "SELECT id, nombre, nombre_normalizado FROM tags ORDER BY id"
    ).fetchall()
    conexion.close()

    normalizados = [fila[2] for fila in filas]
    assert len(normalizados) == len(set(normalizados)) == 5
    assert ("Educación", "educación") in {(fila[1], fila[2]) for fila in filas}
    assert ("EDUCACIÓN (2)", "educación (2)") in {(fila[1], fila[2]) for fila in filas}
    assert ("Ñandú", "ñandú") in {(fila[1], fila[2]) for fila in filas}
    assert ("ñandú (2)", "ñandú (2)") in {(fila[1], fila[2]) for fila in filas}


def test_migracion_fusiona_links_duplicados(tmp_path, monkeypatch):
    ruta = tmp_path / "locker_links_duplicados.db"
    conexion = sqlite3.connect(ruta)
    conexion.executescript(ESQUEMA_ANTIGUO)
    conexion.executescript(
        """
        INSERT INTO tags (id, nombre, user_id) VALUES (2, 'Ocio', 1);
        INSERT INTO links (id, url, titulo, user_id) VALUES
            (1, 'https://duplicado.dev', 'Primero', 1),
            (2, 'https://duplicado.dev', 'Segundo', 1),
            (3, 'https://otro.dev', 'Otro', 1);
        INSERT INTO link_tags (link_id, tag_id) VALUES (1, 1), (2, 2), (3, 1);
        """
    )
    conexion.close()

    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{ruta.as_posix()}")
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")

    conexion = sqlite3.connect(ruta)
    links = conexion.execute(
        "SELECT id, url, titulo FROM links ORDER BY id"
    ).fetchall()
    etiquetas = conexion.execute(
        "SELECT link_id, tag_id FROM link_tags ORDER BY link_id, tag_id"
    ).fetchall()
    indices_links = {fila[1] for fila in conexion.execute("PRAGMA index_list(links)")}
    indices_link_tags = {
        fila[1] for fila in conexion.execute("PRAGMA index_list(link_tags)")
    }
    version = conexion.execute("SELECT version_num FROM alembic_version").fetchone()
    conexion.close()

    assert links == [
        (1, "https://duplicado.dev", "Primero"),
        (3, "https://otro.dev", "Otro"),
    ]
    # Las etiquetas del duplicado se conservan en el link que queda.
    assert etiquetas == [(1, 1), (1, 2), (3, 1)]
    assert "uq_links_usuario_url" in indices_links
    assert "ix_links_user_created" in indices_links
    assert "ix_link_tags_tag_id" in indices_link_tags
    assert version == ("0005_urls_canonicas",)


def test_migracion_canonicaliza_urls_y_fusiona_duplicados(tmp_path, monkeypatch):
    ruta = tmp_path / "locker_urls_canonicas.db"
    conexion = sqlite3.connect(ruta)
    conexion.executescript(ESQUEMA_ANTIGUO)
    conexion.executescript(
        """
        INSERT INTO tags (id, nombre, user_id) VALUES (2, 'Ocio', 1);
        INSERT INTO links (id, url, titulo, user_id) VALUES
            (1, 'https://a.com/', 'Primero', 1),
            (2, 'https://a.com', 'Segundo', 1),
            (3, 'HTTPS://Example.COM/x#frag', 'Mayúsculas', 1),
            (4, 'http://otro.com:80/y', 'Puerto', 1);
        INSERT INTO link_tags (link_id, tag_id) VALUES (1, 1), (2, 2);
        """
    )
    conexion.close()

    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{ruta.as_posix()}")
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")

    conexion = sqlite3.connect(ruta)
    links = conexion.execute("SELECT id, url, titulo FROM links ORDER BY id").fetchall()
    etiquetas = conexion.execute(
        "SELECT link_id, tag_id FROM link_tags ORDER BY link_id, tag_id"
    ).fetchall()
    version = conexion.execute("SELECT version_num FROM alembic_version").fetchone()
    conexion.close()

    assert links == [
        (1, "https://a.com", "Primero"),
        (3, "https://example.com/x", "Mayúsculas"),
        (4, "http://otro.com/y", "Puerto"),
    ]
    assert etiquetas == [(1, 1), (1, 2)]
    assert version == ("0005_urls_canonicas",)


def test_esquema_migrado_coincide_con_los_modelos(tmp_path, monkeypatch):
    ruta = tmp_path / "locker_esquema.db"
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{ruta.as_posix()}")
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

    motor = create_engine(f"sqlite:///{ruta.as_posix()}")
    with motor.connect() as conexion:
        diferencias = compare_metadata(
            MigrationContext.configure(conexion, opts={"compare_type": True}),
            Base.metadata,
        )
    motor.dispose()

    assert diferencias == []


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
