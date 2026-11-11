"""Regresión: bcrypt trunca a 72 bytes, no a 72 caracteres."""

from schemas import UserLogin


def _registrar(cliente, email="ana@ejemplo.com", password="secreto123"):
    return cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": email, "password": password},
    )


def _login(cliente, email="ana@ejemplo.com", password="secreto123"):
    return cliente.post("/auth/login", json={"email": email, "password": password})


def test_registro_limita_la_contrasena_en_bytes(cliente):
    # 40 "ñ" son 80 bytes: bcrypt los truncaría en silencio.
    assert _registrar(cliente, password="ñ" * 40).status_code == 422
    assert _registrar(cliente, email="ok@ejemplo.com", password="a" * 72).status_code == 200
    assert _registrar(cliente, email="larga@ejemplo.com", password="a" * 73).status_code == 422


def test_cambio_de_password_limita_en_bytes(cliente):
    assert _registrar(cliente).status_code == 200
    token = _login(cliente).json()["access_token"]

    respuesta = cliente.put(
        "/auth/password",
        json={"password_actual": "secreto123", "password_nueva": "ñ" * 40},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 422


def test_restablecer_limita_en_bytes_y_usa_esquema_pydantic(cliente):
    assert _registrar(cliente).status_code == 200
    solicitud = cliente.post("/auth/recuperar", json={"email": "ana@ejemplo.com"}).json()

    respuesta = cliente.post(
        "/auth/restablecer",
        json={"token": solicitud["reset_token"], "password": "ñ" * 40},
    )
    assert respuesta.status_code == 422
    # El error de validación se normaliza como lista (1.9), no como el 422
    # manual con un único string de la versión anterior.
    assert isinstance(respuesta.json()["detail"], list)


def test_login_no_rechaza_por_longitud_para_no_romper_cuentas_antiguas():
    # El login debe validar credenciales, no la política de creación.
    datos = UserLogin(email="ana@ejemplo.com", password="a" * 100)
    assert datos.password == "a" * 100
