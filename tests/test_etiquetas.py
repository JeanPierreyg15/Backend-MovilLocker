"""Regresión: etiquetas duplicadas por mayúsculas y acentos (SQLite lower())."""


def _registrar(cliente, email="ana@ejemplo.com"):
    respuesta = cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": email, "password": "secreto123"},
    )
    assert respuesta.status_code == 200, respuesta.text


def _token(cliente, email="ana@ejemplo.com"):
    respuesta = cliente.post("/auth/login", json={"email": email, "password": "secreto123"})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def _cabeceras(token):
    return {"Authorization": f"Bearer {token}"}


def _crear_tag(cliente, token, nombre):
    return cliente.post("/tags/", json={"nombre": nombre, "icono": "🏷️"}, headers=_cabeceras(token))


def test_no_permite_etiquetas_duplicadas_con_acentos_y_mayusculas(cliente):
    _registrar(cliente)
    token = _token(cliente)

    assert _crear_tag(cliente, token, "Educación").status_code == 200
    assert _crear_tag(cliente, token, "EDUCACIÓN").status_code == 400

    assert _crear_tag(cliente, token, "Ñandú").status_code == 200
    assert _crear_tag(cliente, token, "ñandú").status_code == 400


def test_renombrar_a_una_etiqueta_existente_ignora_acentos_y_mayusculas(cliente):
    _registrar(cliente)
    token = _token(cliente)

    assert _crear_tag(cliente, token, "Educación").status_code == 200
    otra = _crear_tag(cliente, token, "Otra").json()

    respuesta = cliente.put(
        f"/tags/{otra['id']}",
        json={"nombre": "EDUCACIÓN", "icono": "🏷️"},
        headers=_cabeceras(token),
    )
    assert respuesta.status_code == 400
