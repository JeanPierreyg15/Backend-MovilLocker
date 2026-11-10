"""Regresión: borrar un usuario debe funcionar aunque la BD antigua tenga
claves foráneas sin ON DELETE CASCADE (las creaba la versión previa)."""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from models import Link, Tag, User

ESQUEMA_SIN_CASCADA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    nombre VARCHAR NOT NULL,
    email VARCHAR NOT NULL,
    hashed_password VARCHAR NOT NULL,
    avatar_color VARCHAR(7),
    bio TEXT,
    token_version INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME
);
CREATE TABLE links (
    id INTEGER PRIMARY KEY,
    url VARCHAR NOT NULL,
    titulo VARCHAR NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at DATETIME
);
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    nombre VARCHAR NOT NULL,
    icono VARCHAR(16),
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at DATETIME
);
CREATE TABLE link_tags (
    link_id INTEGER NOT NULL REFERENCES links(id),
    tag_id INTEGER NOT NULL REFERENCES tags(id),
    PRIMARY KEY (link_id, tag_id)
);
CREATE TABLE password_resets (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    codigo_hash VARCHAR NOT NULL,
    expira_at DATETIME NOT NULL,
    intentos INTEGER NOT NULL DEFAULT 0,
    usado BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME
);
INSERT INTO users (id, nombre, email, hashed_password) VALUES (1, 'Ana', 'ana@ejemplo.com', 'hash');
INSERT INTO links (id, url, titulo, user_id) VALUES (1, 'https://react.dev', 'React', 1);
INSERT INTO tags (id, nombre, user_id) VALUES (1, 'Dev', 1);
INSERT INTO link_tags (link_id, tag_id) VALUES (1, 1);
"""


def test_borrar_usuario_sin_cascada_en_la_bd(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'antigua.db').as_posix()}")

    @event.listens_for(engine, "connect")
    def _activar_fk(conexion_dbapi, _registro):
        conexion_dbapi.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as conexion:
        for sentencia in ESQUEMA_SIN_CASCADA.split(";"):
            if sentencia.strip():
                conexion.execute(text(sentencia))

    Session = sessionmaker(bind=engine)
    with Session() as db:
        usuario = db.get(User, 1)
        assert db.get(Link, 1) is not None
        assert db.get(Tag, 1) is not None
        db.delete(usuario)
        db.commit()

    with engine.connect() as conexion:
        assert conexion.execute(text("SELECT count(*) FROM users")).scalar() == 0
        assert conexion.execute(text("SELECT count(*) FROM links")).scalar() == 0
        assert conexion.execute(text("SELECT count(*) FROM tags")).scalar() == 0
        assert conexion.execute(text("SELECT count(*) FROM link_tags")).scalar() == 0
    engine.dispose()
