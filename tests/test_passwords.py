PASSWORD = "secreto123"
EMOJIS_19 = "😀" * 19  # 19 caracteres, 76 bytes en UTF-8
TILDES_40 = "á" * 40  # 40 caracteres, 80 bytes en UTF-8


def registrar(cliente, password=PASSWORD, email="ana@ejemplo.com"):
    return cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": email, "password": password},
    )


def token_de(cliente, email="ana@ejemplo.com", password=PASSWORD):
    respuesta = cliente.post("/auth/login", json={"email": email, "password": password})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def cabeceras(token):
    return {"Authorization": f"Bearer {token}"}


def test_registro_acepta_72_bytes_y_rechaza_mas(cliente):
    assert registrar(cliente, "a" * 72, "exacto@ejemplo.com").status_code == 200

    # 73 caracteres ASCII: lo corta max_length.
    assert registrar(cliente, "a" * 73, "ascii@ejemplo.com").status_code == 422

    # Menos de 72 caracteres, pero más de 72 bytes: lo corta el validador de bytes.
    assert registrar(cliente, EMOJIS_19, "emojis@ejemplo.com").status_code == 422
    assert registrar(cliente, TILDES_40, "tildes@ejemplo.com").status_code == 422


def test_login_rechaza_passwords_de_mas_de_72_bytes(cliente):
    assert registrar(cliente).status_code == 200

    respuesta = cliente.post(
        "/auth/login", json={"email": "ana@ejemplo.com", "password": EMOJIS_19}
    )
    assert respuesta.status_code == 422


def test_cambio_de_password_valida_bytes_en_ambas(cliente):
    assert registrar(cliente).status_code == 200
    token = token_de(cliente)

    nueva_larga = cliente.put(
        "/auth/password",
        json={"password_actual": PASSWORD, "password_nueva": EMOJIS_19},
        headers=cabeceras(token),
    )
    assert nueva_larga.status_code == 422

    actual_larga = cliente.put(
        "/auth/password",
        json={"password_actual": TILDES_40, "password_nueva": "nuevaClave99"},
        headers=cabeceras(token),
    )
    assert actual_larga.status_code == 422

    # La contraseña no cambió.
    assert token_de(cliente)


def test_restablecer_valida_bytes(cliente):
    assert registrar(cliente).status_code == 200
    solicitud = cliente.post("/auth/recuperar", json={"email": "ana@ejemplo.com"})
    codigo = solicitud.json()["codigo_desarrollo"]

    respuesta = cliente.post(
        "/auth/restablecer",
        json={"email": "ana@ejemplo.com", "codigo": codigo, "password": EMOJIS_19},
    )
    assert respuesta.status_code == 422

    # El código sigue siendo válido porque el cambio no se aplicó.
    correcto = cliente.post(
        "/auth/restablecer",
        json={"email": "ana@ejemplo.com", "codigo": codigo, "password": "nuevaClave99"},
    )
    assert correcto.status_code == 200
