"""Regresión: el nombre del perfil se limpia en el servidor."""


def _token(cliente):
    cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": "ana@ejemplo.com", "password": "secreto123"},
    )
    respuesta = cliente.post(
        "/auth/login", json={"email": "ana@ejemplo.com", "password": "secreto123"}
    )
    return respuesta.json()["access_token"]


def test_perfil_rechaza_nombre_solo_con_espacios(cliente):
    token = _token(cliente)

    respuesta = cliente.put(
        "/auth/perfil",
        json={"nombre": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 422


def test_perfil_hace_trim_del_nombre_y_la_bio(cliente):
    token = _token(cliente)

    respuesta = cliente.put(
        "/auth/perfil",
        json={"nombre": "  Ana María  ", "bio": "  Guardo links  "},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Ana María"
    assert respuesta.json()["bio"] == "Guardo links"
