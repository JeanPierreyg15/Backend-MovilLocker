"""Los 422 deben ser legibles, en español y sin prefijos técnicos de Pydantic."""

import json


def _texto_detalle(respuesta):
    return json.dumps(respuesta.json()["detail"], ensure_ascii=False)


def test_error_de_url_es_legible_y_en_espanol(cliente):
    cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": "ana@ejemplo.com", "password": "secreto123"},
    )
    token = cliente.post(
        "/auth/login", json={"email": "ana@ejemplo.com", "password": "secreto123"}
    ).json()["access_token"]

    respuesta = cliente.post(
        "/links/",
        json={"url": "javascript:alert(1)", "titulo": "X"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 422
    detalle = _texto_detalle(respuesta)
    assert "La URL debe usar http o https" in detalle
    assert "Value error" not in detalle
    assert "String should" not in detalle


def test_error_de_password_larga_es_legible(cliente):
    respuesta = cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": "ana@ejemplo.com", "password": "ñ" * 40},
    )

    assert respuesta.status_code == 422
    assert isinstance(respuesta.json()["detail"], list)
    detalle = _texto_detalle(respuesta)
    assert "72 bytes" in detalle
    assert "Value error" not in detalle


def test_error_de_campo_obligatorio_en_espanol(cliente):
    respuesta = cliente.post("/auth/register", json={"email": "ana@ejemplo.com"})

    assert respuesta.status_code == 422
    detalle = _texto_detalle(respuesta)
    assert "obligatorio" in detalle.lower()
    assert "Field required" not in detalle
