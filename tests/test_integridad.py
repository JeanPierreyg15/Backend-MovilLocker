"""La base de datos también protege la integridad de los links."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from database import SessionLocal, engine
from models import Link


def _registrar(cliente, email="ana@ejemplo.com"):
    respuesta = cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": email, "password": "secreto123"},
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _token(cliente, email="ana@ejemplo.com"):
    respuesta = cliente.post(
        "/auth/login", json={"email": email, "password": "secreto123"}
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def _cabeceras(token):
    return {"Authorization": f"Bearer {token}"}


def test_la_bd_rechaza_una_url_duplicada_del_mismo_usuario(cliente):
    usuario = _registrar(cliente)
    token = _token(cliente)
    creado = cliente.post(
        "/links/",
        json={"url": "https://duplicado.dev", "titulo": "Primero"},
        headers=_cabeceras(token),
    )
    assert creado.status_code == 200

    db = SessionLocal()
    try:
        db.add(
            Link(
                url="https://duplicado.dev",
                titulo="Segundo",
                user_id=usuario["id"],
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_la_misma_url_puede_guardarla_otro_usuario(cliente):
    _registrar(cliente, email="ana@ejemplo.com")
    _registrar(cliente, email="beto@ejemplo.com")
    token_ana = _token(cliente, email="ana@ejemplo.com")
    token_beto = _token(cliente, email="beto@ejemplo.com")

    for token in (token_ana, token_beto):
        respuesta = cliente.post(
            "/links/",
            json={"url": "https://compartido.dev", "titulo": "Compartido"},
            headers=_cabeceras(token),
        )
        assert respuesta.status_code == 200, respuesta.text


def test_existen_los_indices_de_consulta():
    inspector = inspect(engine)

    indices_links = inspector.get_indexes("links")
    assert any(
        tuple(indice.get("column_names") or ()) == ("user_id", "created_at")
        for indice in indices_links
    )
    assert any(
        indice.get("unique")
        and tuple(indice.get("column_names") or ()) == ("user_id", "url")
        or indice.get("name") == "uq_links_usuario_url"
        for indice in indices_links
    ) or any(
        tuple(restriccion.get("column_names") or ()) == ("user_id", "url")
        for restriccion in inspector.get_unique_constraints("links")
    )

    assert any(
        tuple(indice.get("column_names") or ()) == ("tag_id",)
        for indice in inspector.get_indexes("link_tags")
    )
