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


def test_cerrar_sesiones_invalida_los_tokens_anteriores(cliente):
    assert registrar(cliente).status_code == 200
    token_viejo = token_de(cliente)

    respuesta = cliente.post("/auth/cerrar-sesiones", headers=cabeceras(token_viejo))
    assert respuesta.status_code == 200
    token_nuevo = respuesta.json()["access_token"]
    assert token_nuevo != token_viejo

    # El token anterior deja de servir; el nuevo mantiene esta sesión.
    assert cliente.get("/auth/me", headers=cabeceras(token_viejo)).status_code == 401
    assert cliente.get("/auth/me", headers=cabeceras(token_nuevo)).status_code == 200


def test_cerrar_sesiones_exige_autenticacion(cliente):
    assert cliente.post("/auth/cerrar-sesiones").status_code == 401
