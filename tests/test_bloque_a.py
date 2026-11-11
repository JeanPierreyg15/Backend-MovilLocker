"""Bloque A: rate limiting, URLs canónicas, recuperación en debug y correo."""

import logging

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

from database import SessionLocal
from routers import auth
from schemas import normalizar_url


def _peticion(host="127.0.0.1", headers=None):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/recuperar",
            "headers": headers or [],
            "client": (host, 50000),
        }
    )


def _registrar(cliente, email="ana@ejemplo.com", password="secreto123"):
    respuesta = cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": email, "password": password},
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta


def _token(cliente, email="ana@ejemplo.com", password="secreto123"):
    respuesta = cliente.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


# ---------- A1: rate limiting ----------


def test_registro_tiene_limite_por_ip(cliente, monkeypatch):
    monkeypatch.setattr(auth.config, "LIMITE_REGISTRO", 2)

    _registrar(cliente, "uno@ejemplo.com")
    _registrar(cliente, "dos@ejemplo.com")
    respuesta = cliente.post(
        "/auth/register",
        json={"nombre": "Tres", "email": "tres@ejemplo.com", "password": "secreto123"},
    )

    assert respuesta.status_code == 429
    assert "Demasiados intentos" in respuesta.json()["detail"]


def test_login_limita_por_ip_y_correo(cliente, monkeypatch):
    _registrar(cliente)
    monkeypatch.setattr(auth.config, "LIMITE_LOGIN", 2)

    for _ in range(2):
        respuesta = cliente.post(
            "/auth/login", json={"email": "ana@ejemplo.com", "password": "mala"}
        )
        assert respuesta.status_code == 401

    bloqueado = cliente.post(
        "/auth/login", json={"email": "ana@ejemplo.com", "password": "mala"}
    )
    assert bloqueado.status_code == 429

    # Otro correo desde la misma IP conserva su propio contador.
    otro = cliente.post(
        "/auth/login", json={"email": "otro@ejemplo.com", "password": "mala"}
    )
    assert otro.status_code == 401


def test_cambiar_password_tiene_limite(cliente, monkeypatch):
    _registrar(cliente)
    token = _token(cliente)
    monkeypatch.setattr(auth.config, "LIMITE_CAMBIAR_PASSWORD", 1)

    cabeceras = {"Authorization": f"Bearer {token}"}
    datos = {"password_actual": "mala", "password_nueva": "nuevaClave123"}

    primera = cliente.put("/auth/password", json=datos, headers=cabeceras)
    segunda = cliente.put("/auth/password", json=datos, headers=cabeceras)

    assert primera.status_code == 400
    assert segunda.status_code == 429


def test_eliminar_cuenta_tiene_limite(cliente, monkeypatch):
    _registrar(cliente)
    token = _token(cliente)
    monkeypatch.setattr(auth.config, "LIMITE_ELIMINAR_CUENTA", 1)

    cabeceras = {"Authorization": f"Bearer {token}"}
    primera = cliente.request(
        "DELETE", "/auth/cuenta", json={"password": "mala"}, headers=cabeceras
    )
    segunda = cliente.request(
        "DELETE", "/auth/cuenta", json={"password": "mala"}, headers=cabeceras
    )

    assert primera.status_code == 400
    assert segunda.status_code == 429


def test_restablecer_tiene_limite(cliente, monkeypatch):
    monkeypatch.setattr(auth.config, "LIMITE_RESTABLECER", 1)

    primera = cliente.post(
        "/auth/restablecer", json={"token": "invalido", "password": "secreto123"}
    )
    segunda = cliente.post(
        "/auth/restablecer", json={"token": "invalido", "password": "secreto123"}
    )

    assert primera.status_code == 400
    assert segunda.status_code == 429


def test_x_forwarded_for_se_ignora_sin_proxies_confiables(monkeypatch):
    auth._intentos.clear()
    monkeypatch.setattr(auth.config, "TRUSTED_PROXIES", "")
    peticion = _peticion("10.0.0.1", headers=[(b"x-forwarded-for", b"1.2.3.4")])

    auth.limitar_peticiones(peticion, "prueba", maximo=5)

    assert auth._intentos["prueba:10.0.0.1"]


def test_x_forwarded_for_se_usa_con_proxy_confiable(monkeypatch):
    auth._intentos.clear()
    monkeypatch.setattr(auth.config, "TRUSTED_PROXIES", "10.0.0.1")
    peticion = _peticion(
        "10.0.0.1", headers=[(b"x-forwarded-for", b"1.2.3.4, 10.0.0.1")]
    )

    auth.limitar_peticiones(peticion, "prueba", maximo=5)

    assert auth._intentos["prueba:1.2.3.4"]


# ---------- A2: URL canónica ----------


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [
        ("https://a.com/", "https://a.com"),
        ("https://a.com", "https://a.com"),
        ("HTTPS://Example.COM/a", "https://example.com/a"),
        ("http://a.com:80/x", "http://a.com/x"),
        ("https://a.com:443/x", "https://a.com/x"),
        ("https://a.com:8443/x", "https://a.com:8443/x"),
        ("https://a.com/x#fragmento", "https://a.com/x"),
        ("https://a.com/#fragmento", "https://a.com"),
        ("https://a.com/x?b=2", "https://a.com/x?b=2"),
        ("a.com", "https://a.com"),
    ],
)
def test_normalizar_url_canonicaliza(entrada, esperada):
    assert normalizar_url(entrada) == esperada


# ---------- A5: recuperación en debug desde fuera de loopback ----------


def test_debug_registra_el_codigo_fuera_de_loopback(cliente, monkeypatch, caplog):
    _registrar(cliente)
    monkeypatch.setattr(auth.config, "SMTP_HOST", None)
    monkeypatch.setattr(auth.config, "SMTP_FROM", None)
    monkeypatch.setattr(auth.config, "DEBUG", True)

    tareas = BackgroundTasks()
    db = SessionLocal()
    try:
        with caplog.at_level(logging.WARNING, logger="locker.auth"):
            respuesta = auth.solicitar_recuperacion(
                auth.SolicitudRecuperacion(email="ana@ejemplo.com"),
                _peticion("10.0.0.5"),
                tareas,
                db,
            )
    finally:
        db.close()

    assert "reset_token" not in respuesta
    assert tareas.tasks == []
    assert "Código de recuperación" in caplog.text
    assert "ana@ejemplo.com" in caplog.text


# ---------- A6: mensaje de correo inválido ----------


def test_correo_invalido_siempre_responde_en_español(cliente):
    respuesta = cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": "a@b", "password": "secreto123"},
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"][0]["msg"] == "El correo electrónico no es válido."


# ---------- A4: configuración y SQLite ----------


def test_env_file_se_resuelve_junto_al_proyecto():
    from config import RAIZ_PROYECTO

    ruta = auth.config.model_config["env_file"]
    assert ruta.is_absolute()
    assert ruta == RAIZ_PROYECTO / ".env"


def test_sqlite_activa_wal_y_busy_timeout(cliente):
    from sqlalchemy import text

    db = SessionLocal()
    try:
        assert db.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert db.execute(text("PRAGMA busy_timeout")).scalar() == 5000
    finally:
        db.close()
