from fastapi.testclient import TestClient

from main import app


def registrar(cliente, email="ana@ejemplo.com", password="secreto123"):
    return cliente.post(
        "/auth/register", json={"nombre": "Ana", "email": email, "password": password}
    )


def login(cliente, email="ana@ejemplo.com", password="secreto123"):
    return cliente.post("/auth/login", json={"email": email, "password": password})


def token_de(cliente, email="ana@ejemplo.com", password="secreto123"):
    respuesta = login(cliente, email, password)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def cabeceras(token):
    return {"Authorization": f"Bearer {token}"}


def crear_tag(cliente, token, nombre="Dev", icono="💻"):
    return cliente.post("/tags/", json={"nombre": nombre, "icono": icono}, headers=cabeceras(token))


# ---------- Autenticación ----------

def test_registro_login_y_me(cliente):
    assert registrar(cliente).status_code == 200
    respuesta = login(cliente)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["access_token"]
    assert cuerpo["usuario"]["email"] == "ana@ejemplo.com"  # el login ya trae el usuario

    me = cliente.get("/auth/me", headers=cabeceras(cuerpo["access_token"]))
    assert me.status_code == 200
    assert me.json()["nombre"] == "Ana"


def test_registro_normaliza_email_y_valida_password(cliente):
    assert registrar(cliente, email="ANA@Ejemplo.COM").status_code == 200
    # El email quedó normalizado a minúsculas
    assert login(cliente, email="ana@ejemplo.com").status_code == 200

    respuesta = cliente.post(
        "/auth/register",
        json={"nombre": "X", "email": "b@ejemplo.com", "password": "corta"},
    )
    assert respuesta.status_code == 422  # password < 8


def test_login_incorrecto(cliente):
    registrar(cliente)
    assert login(cliente, password="incorrecta").status_code == 401


def test_perfil_actualiza_nombre_bio_y_avatar(cliente):
    registrar(cliente)
    token = token_de(cliente)
    respuesta = cliente.put(
        "/auth/perfil",
        json={"nombre": "Ana María", "bio": "Guardo links", "avatar_color": "#7c3aed"},
        headers=cabeceras(token),
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Ana María"
    assert cuerpo["bio"] == "Guardo links"
    assert cuerpo["avatar_color"] == "#7c3aed"


def test_avatar_color_invalido(cliente):
    registrar(cliente)
    token = token_de(cliente)
    respuesta = cliente.put(
        "/auth/perfil", json={"avatar_color": "rojo"}, headers=cabeceras(token)
    )
    assert respuesta.status_code == 422


# ---------- Links ----------

def test_crud_links_y_urls_invalidas(cliente):
    registrar(cliente)
    token = token_de(cliente)
    tag = crear_tag(cliente, token).json()

    creado = cliente.post(
        "/links/",
        json={"url": "react.dev", "titulo": "React", "tag_ids": [tag["id"]]},
        headers=cabeceras(token),
    )
    assert creado.status_code == 200
    link = creado.json()
    assert link["url"] == "https://react.dev"  # normalizada
    assert link["tags"][0]["nombre"] == "Dev"
    assert link["created_at"] is not None
    # SQLite no guarda zona: el backend debe serializar UTC con sufijo Z.
    assert link["created_at"].endswith("Z"), link["created_at"]

    # Duplicado por usuario
    duplicado = cliente.post(
        "/links/", json={"url": "https://react.dev", "titulo": "Otra vez"}, headers=cabeceras(token)
    )
    assert duplicado.status_code == 400

    # Esquema peligroso rechazado
    peligroso = cliente.post(
        "/links/", json={"url": "javascript:alert(1)", "titulo": "X"}, headers=cabeceras(token)
    )
    assert peligroso.status_code == 422

    # Editar
    editado = cliente.put(
        f"/links/{link['id']}",
        json={"url": "https://react.dev/docs", "titulo": "Docs", "tag_ids": []},
        headers=cabeceras(token),
    )
    assert editado.status_code == 200
    assert editado.json()["titulo"] == "Docs"

    # Listar
    lista = cliente.get("/links/", headers=cabeceras(token))
    assert lista.status_code == 200
    assert len(lista.json()) == 1

    # Eliminar
    assert cliente.delete(f"/links/{link['id']}", headers=cabeceras(token)).status_code == 204


def test_paginacion_y_conteo_real_de_links(cliente):
    registrar(cliente)
    token = token_de(cliente)

    for i in range(105):
        respuesta = cliente.post(
            "/links/",
            json={"url": f"https://ejemplo.com/{i}", "titulo": f"Ejemplo {i}"},
            headers=cabeceras(token),
        )
        assert respuesta.status_code == 200, respuesta.text

    # El listado por defecto sigue limitado a 100...
    primera = cliente.get("/links/", headers=cabeceras(token)).json()
    assert len(primera) == 100
    # ...pero /links/count revela el total real y la paginación alcanza el resto.
    assert cliente.get("/links/count", headers=cabeceras(token)).json() == {"count": 105}
    segunda = cliente.get("/links/?skip=100&limit=100", headers=cabeceras(token)).json()
    assert len(segunda) == 5


def test_etiquetas_incluyen_conteo_real_de_links(cliente):
    registrar(cliente)
    token = token_de(cliente)
    tag = crear_tag(cliente, token).json()

    for i in range(3):
        cliente.post(
            "/links/",
            json={"url": f"https://contador.com/{i}", "titulo": f"C {i}", "tag_ids": [tag["id"]]},
            headers=cabeceras(token),
        )

    etiquetas = cliente.get("/tags/", headers=cabeceras(token)).json()
    assert etiquetas[0]["links_count"] == 3
    assert cliente.get("/tags/count", headers=cabeceras(token)).json() == {"count": 1}


def test_aislamiento_entre_usuarios(cliente):
    registrar(cliente, email="ana@ejemplo.com")
    registrar(cliente, email="beto@ejemplo.com")
    token_ana = token_de(cliente, email="ana@ejemplo.com")
    token_beto = token_de(cliente, email="beto@ejemplo.com", password="secreto123")

    link = cliente.post(
        "/links/", json={"url": "https://python.org", "titulo": "Python"}, headers=cabeceras(token_ana)
    ).json()

    # Beto no ve ni borra el link de Ana
    assert cliente.get("/links/", headers=cabeceras(token_beto)).json() == []
    assert cliente.delete(f"/links/{link['id']}", headers=cabeceras(token_beto)).status_code == 404


# ---------- Etiquetas ----------

def test_etiquetas_por_usuario_y_renombrado(cliente):
    registrar(cliente, email="ana@ejemplo.com")
    registrar(cliente, email="beto@ejemplo.com")
    token_ana = token_de(cliente, email="ana@ejemplo.com")
    token_beto = token_de(cliente, email="beto@ejemplo.com")

    # Misma etiqueta para dos usuarios distintos: permitido
    assert crear_tag(cliente, token_ana, "Trabajo").status_code == 200
    assert crear_tag(cliente, token_beto, "Trabajo").status_code == 200

    # Duplicada (sin distinguir mayúsculas) para el mismo usuario: rechazada
    assert crear_tag(cliente, token_ana, "trabajo").status_code == 400

    tag = crear_tag(cliente, token_ana, "Ocio").json()
    renombrada = cliente.put(
        f"/tags/{tag['id']}", json={"nombre": "Diversión", "icono": "🎮"}, headers=cabeceras(token_ana)
    )
    assert renombrada.status_code == 200
    assert renombrada.json()["nombre"] == "Diversión"

    assert cliente.delete(f"/tags/{tag['id']}", headers=cabeceras(token_ana)).status_code == 204


# ---------- Recuperación de contraseña ----------

def test_flujo_completo_de_recuperacion(cliente):
    registrar(cliente, password="secreto123")
    token_sesion = token_de(cliente, password="secreto123")

    solicitud = cliente.post("/auth/recuperar", json={"email": "ana@ejemplo.com"})
    assert solicitud.status_code == 200
    codigo = solicitud.json().get("codigo_desarrollo")  # solo en DEBUG
    assert codigo and len(codigo) == 8 and codigo.isdigit()

    # El código no sirve como token de sesión.
    assert cliente.get("/auth/me", headers=cabeceras(codigo)).status_code == 401

    cambio = cliente.post(
        "/auth/restablecer",
        json={"email": "ana@ejemplo.com", "codigo": codigo, "password": "nuevaClave99"},
    )
    assert cambio.status_code == 200

    # Usar el mismo código otra vez falla (monouso).
    reuso = cliente.post(
        "/auth/restablecer",
        json={"email": "ana@ejemplo.com", "codigo": codigo, "password": "otraClave99"},
    )
    assert reuso.status_code == 400

    # La sesión anterior quedó invalidada y la nueva contraseña funciona
    assert cliente.get("/auth/me", headers=cabeceras(token_sesion)).status_code == 401
    assert login(cliente, password="secreto123").status_code == 401
    assert login(cliente, password="nuevaClave99").status_code == 200


def test_recuperacion_no_revela_correos_inexistentes(cliente):
    respuesta = cliente.post("/auth/recuperar", json={"email": "nadie@ejemplo.com"})
    assert respuesta.status_code == 200
    assert "codigo_desarrollo" not in respuesta.json()


def test_codigo_no_se_expone_fuera_de_loopback(cliente):
    """Aunque DEBUG=true, una petición externa nunca recibe el código."""
    registrar(cliente)

    with TestClient(app, client=("203.0.113.10", 50000)) as externo:
        respuesta = externo.post("/auth/recuperar", json={"email": "ana@ejemplo.com"})

    assert respuesta.status_code == 200
    assert "codigo_desarrollo" not in respuesta.json()

    # Detrás de un proxy, una petición reenviada tampoco cuenta como local.
    with_proxy = cliente.post(
        "/auth/recuperar",
        json={"email": "ana@ejemplo.com"},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert "codigo_desarrollo" not in with_proxy.json()


def test_cambio_de_password_invalida_sesiones(cliente):
    registrar(cliente)
    token_viejo = token_de(cliente)

    respuesta = cliente.put(
        "/auth/password",
        json={"password_actual": "secreto123", "password_nueva": "secreto456"},
        headers=cabeceras(token_viejo),
    )
    assert respuesta.status_code == 200
    token_nuevo = respuesta.json()["access_token"]

    assert cliente.get("/auth/me", headers=cabeceras(token_viejo)).status_code == 401
    assert cliente.get("/auth/me", headers=cabeceras(token_nuevo)).status_code == 200


# ---------- Eliminar cuenta ----------

def test_eliminar_cuenta_exige_password_y_borra_todo(cliente):
    registrar(cliente)
    token = token_de(cliente)
    tag = crear_tag(cliente, token).json()
    cliente.post(
        "/links/", json={"url": "https://x.dev", "titulo": "X", "tag_ids": [tag["id"]]},
        headers=cabeceras(token),
    )

    assert cliente.request(
        "DELETE", "/auth/cuenta", json={"password": "mala"}, headers=cabeceras(token)
    ).status_code == 400

    assert cliente.request(
        "DELETE", "/auth/cuenta", json={"password": "secreto123"}, headers=cabeceras(token)
    ).status_code == 204

    assert login(cliente).status_code == 401


# ---------- General ----------

def test_health(cliente):
    respuesta = cliente.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok", "database": "ok"}
