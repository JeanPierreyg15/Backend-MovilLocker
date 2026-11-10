import limitador
from config import config

PASSWORD = "secreto123"


def registrar(cliente, email):
    return cliente.post(
        "/auth/register",
        json={"nombre": "Persona", "email": email, "password": PASSWORD},
    )


def login(cliente, email, password=PASSWORD):
    return cliente.post("/auth/login", json={"email": email, "password": password})


def token_de(cliente, email):
    respuesta = login(cliente, email)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def cabeceras(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_devuelve_429_al_superar_el_limite(cliente):
    for indice in range(10):
        assert registrar(cliente, f"persona{indice}@ejemplo.com").status_code == 200

    respuesta = registrar(cliente, "otra@ejemplo.com")
    assert respuesta.status_code == 429
    assert "Demasiados intentos" in respuesta.json()["detail"]


def test_la_ventana_del_limite_se_reinicia(cliente, monkeypatch):
    reloj = {"ahora": 1_000_000.0}
    monkeypatch.setattr(limitador, "_ahora", lambda: reloj["ahora"])

    for indice in range(10):
        assert registrar(cliente, f"ventana{indice}@ejemplo.com").status_code == 200
    assert registrar(cliente, "bloqueada@ejemplo.com").status_code == 429

    reloj["ahora"] += 61

    assert registrar(cliente, "despues@ejemplo.com").status_code == 200


def test_login_limita_por_ip_y_correo_sin_bloquear_otras_cuentas(cliente):
    assert registrar(cliente, "ana@ejemplo.com").status_code == 200
    assert registrar(cliente, "beto@ejemplo.com").status_code == 200

    for _ in range(10):
        assert login(cliente, "ana@ejemplo.com", "incorrecta").status_code == 401

    assert login(cliente, "ana@ejemplo.com", "incorrecta").status_code == 429

    # Otra cuenta desde la misma IP no queda bloqueada por los intentos de Ana.
    assert login(cliente, "beto@ejemplo.com").status_code == 200


def test_password_limita_por_usuario_autenticado(cliente):
    assert registrar(cliente, "ana@ejemplo.com").status_code == 200
    token = token_de(cliente, "ana@ejemplo.com")

    for _ in range(5):
        respuesta = cliente.put(
            "/auth/password",
            json={"password_actual": "incorrecta", "password_nueva": "nuevaClave99"},
            headers=cabeceras(token),
        )
        assert respuesta.status_code == 400

    respuesta = cliente.put(
        "/auth/password",
        json={"password_actual": PASSWORD, "password_nueva": "nuevaClave99"},
        headers=cabeceras(token),
    )
    assert respuesta.status_code == 429


def test_cuenta_limita_por_usuario_autenticado(cliente):
    assert registrar(cliente, "ana@ejemplo.com").status_code == 200
    token = token_de(cliente, "ana@ejemplo.com")

    for _ in range(5):
        respuesta = cliente.request(
            "DELETE",
            "/auth/cuenta",
            json={"password": "incorrecta"},
            headers=cabeceras(token),
        )
        assert respuesta.status_code == 400

    respuesta = cliente.request(
        "DELETE",
        "/auth/cuenta",
        json={"password": PASSWORD},
        headers=cabeceras(token),
    )
    assert respuesta.status_code == 429

    # La cuenta sigue existiendo: el límite evitó el borrado.
    assert login(cliente, "ana@ejemplo.com").status_code == 200


def test_x_forwarded_for_se_ignora_si_el_origen_no_es_proxy_confiable(cliente, monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXIES", "")

    for indice in range(10):
        respuesta = cliente.post(
            "/auth/recuperar",
            json={"email": f"xff{indice}@ejemplo.com"},
            headers={"X-Forwarded-For": f"203.0.113.{indice + 1}"},
        )
        assert respuesta.status_code == 200

    # Aunque cada petición traiga una IP distinta, todas cuentan para la misma
    # IP real (127.0.0.1): la cabecera se ignoró.
    respuesta = cliente.post(
        "/auth/recuperar",
        json={"email": "xff-final@ejemplo.com"},
        headers={"X-Forwarded-For": "203.0.113.99"},
    )
    assert respuesta.status_code == 429


def test_x_forwarded_for_se_usa_con_proxy_confiable(cliente, monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXIES", "127.0.0.1")

    for _ in range(10):
        respuesta = cliente.post(
            "/auth/recuperar",
            json={"email": "proxy@ejemplo.com"},
            headers={"X-Forwarded-For": "198.51.100.7"},
        )
        assert respuesta.status_code == 200

    bloqueada = cliente.post(
        "/auth/recuperar",
        json={"email": "proxy@ejemplo.com"},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    assert bloqueada.status_code == 429

    otra_ip = cliente.post(
        "/auth/recuperar",
        json={"email": "proxy@ejemplo.com"},
        headers={"X-Forwarded-For": "198.51.100.8"},
    )
    assert otra_ip.status_code == 200
