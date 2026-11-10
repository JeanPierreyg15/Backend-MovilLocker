import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from routers import links as links_router

RAIZ = Path(__file__).resolve().parents[1]
PASSWORD = "secreto123"


def registrar(cliente):
    return cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": "ana@ejemplo.com", "password": PASSWORD},
    )


def token_de(cliente):
    respuesta = cliente.post(
        "/auth/login", json={"email": "ana@ejemplo.com", "password": PASSWORD}
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def cabeceras(token):
    return {"Authorization": f"Bearer {token}"}


def crear(cliente, token, url, titulo="Ejemplo"):
    return cliente.post(
        "/links/", json={"url": url, "titulo": titulo}, headers=cabeceras(token)
    )


def test_duplicado_con_mayusculas_y_barra_final(cliente):
    assert registrar(cliente).status_code == 200
    token = token_de(cliente)

    primero = crear(cliente, token, "https://Ejemplo.COM")
    assert primero.status_code == 200
    assert primero.json()["url"] == "https://ejemplo.com"

    # Distinta capitalización + barra final: misma URL normalizada.
    duplicado = crear(cliente, token, "https://ejemplo.com/", "Otra vez")
    assert duplicado.status_code == 400
    assert duplicado.json()["detail"] == "Ese enlace ya está guardado"


def test_duplicado_de_ruta_con_y_sin_barra_final(cliente):
    assert registrar(cliente).status_code == 200
    token = token_de(cliente)

    assert crear(cliente, token, "https://ejemplo.com/ruta/").status_code == 200
    duplicado = crear(cliente, token, "https://ejemplo.com/ruta")
    assert duplicado.status_code == 400
    assert duplicado.json()["detail"] == "Ese enlace ya está guardado"


def test_carrera_simulada_devuelve_400_en_vez_de_500(cliente, monkeypatch):
    """Si dos peticiones pasan la comprobación a la vez, la BD decide."""
    assert registrar(cliente).status_code == 200
    token = token_de(cliente)
    assert crear(cliente, token, "https://ejemplo.com").status_code == 200

    # Simula que la comprobación previa no ve el duplicado (otra petición se
    # adelantó entre el SELECT y el INSERT).
    monkeypatch.setattr(links_router, "_buscar_duplicado", lambda *args, **kwargs: None)

    respuesta = crear(cliente, token, "https://EJEMPLO.com/")
    assert respuesta.status_code == 400
    assert respuesta.json()["detail"] == "Ese enlace ya está guardado"


def _config_alembic(ruta: Path, monkeypatch) -> Config:
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{ruta.as_posix()}")
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "alembic"))
    cfg.attributes["configure_logger"] = False
    return cfg


def test_migracion_fusiona_duplicados_y_crea_la_restriccion(tmp_path, monkeypatch):
    ruta = tmp_path / "duplicados.db"
    cfg = _config_alembic(ruta, monkeypatch)
    command.upgrade(cfg, "0002_columnas_perfil")

    conexion = sqlite3.connect(ruta)
    conexion.executescript(
        """
        INSERT INTO users (id, nombre, email, hashed_password, token_version)
        VALUES (1, 'Ana', 'ana@ejemplo.com', 'hash', 1);
        INSERT INTO tags (id, nombre, user_id) VALUES (1, 'Dev', 1), (2, 'Trabajo', 1);
        INSERT INTO links (id, url, titulo, user_id) VALUES
            (1, 'https://Ejemplo.com/', 'Antiguo', 1),
            (2, 'https://ejemplo.com', 'Duplicado', 1),
            (3, 'https://ejemplo.com/ruta/', 'Ruta', 1),
            (4, 'https://ejemplo.com/ruta', 'Ruta duplicada', 1);
        INSERT INTO link_tags (link_id, tag_id) VALUES (1, 1), (2, 2), (3, 2), (4, 1);
        """
    )
    conexion.commit()
    conexion.close()

    command.upgrade(cfg, "head")

    conexion = sqlite3.connect(ruta)
    links = conexion.execute("SELECT id, url FROM links ORDER BY id").fetchall()
    etiquetas_link_1 = conexion.execute(
        "SELECT tag_id FROM link_tags WHERE link_id = 1 ORDER BY tag_id"
    ).fetchall()
    etiquetas_link_3 = conexion.execute(
        "SELECT tag_id FROM link_tags WHERE link_id = 3 ORDER BY tag_id"
    ).fetchall()

    # Se conserva el más antiguo de cada grupo, con la URL ya normalizada, y
    # sus etiquetas se fusionan.
    assert links == [
        (1, "https://ejemplo.com"),
        (3, "https://ejemplo.com/ruta"),
    ]
    assert etiquetas_link_1 == [(1,), (2,)]
    assert etiquetas_link_3 == [(1,), (2,)]

    # La restricción ya impide insertar otro duplicado a nivel de BD.
    try:
        conexion.execute(
            "INSERT INTO links (id, url, titulo, user_id) "
            "VALUES (5, 'https://ejemplo.com', 'Otro', 1)"
        )
        conexion.commit()
    except sqlite3.IntegrityError:
        paso = True
    else:
        paso = False
    finally:
        conexion.close()

    assert paso, "La restricción única (user_id, url) no se creó"
