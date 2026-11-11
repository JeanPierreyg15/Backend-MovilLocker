"""Fase 2: rate limiting acotado, correo en segundo plano y CORS seguro."""

import time

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from config import Configuracion
from database import SessionLocal
from routers import auth

SECRET_KEY = "clave-de-pruebas-con-mas-de-32-caracteres-123456"


def _peticion(host="127.0.0.1"):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/recuperar",
            "headers": [],
            "client": (host, 50000),
        }
    )


def _registrar(cliente, email="ana@ejemplo.com"):
    respuesta = cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": email, "password": "secreto123"},
    )
    assert respuesta.status_code == 200, respuesta.text


# ---------- Rate limiting ----------


def test_rate_limit_sigue_bloqueando_al_superar_el_maximo():
    auth._intentos.clear()
    peticion = _peticion("10.0.0.1")

    auth.limitar_peticiones(peticion, "prueba", maximo=2)
    auth.limitar_peticiones(peticion, "prueba", maximo=2)

    with pytest.raises(HTTPException) as error:
        auth.limitar_peticiones(peticion, "prueba", maximo=2)

    assert error.value.status_code == 429


def test_rate_limit_elimina_clientes_inactivos():
    auth._intentos.clear()
    ahora = time.time()
    for indice in range(500):
        auth._intentos[f"antiguo:{indice}"] = [ahora - 3700]

    auth.limitar_peticiones(_peticion("10.0.0.2"), "login", maximo=20)

    assert not any(clave.startswith("antiguo:") for clave in auth._intentos)
    assert auth._intentos["login:10.0.0.2"]


# ---------- Correo en segundo plano ----------


def test_correo_de_recuperacion_se_programa_en_segundo_plano(cliente, monkeypatch):
    _registrar(cliente)
    enviados = []

    monkeypatch.setattr(
        auth,
        "enviar_codigo_recuperacion",
        lambda destinatario, codigo: enviados.append((destinatario, codigo)),
    )
    monkeypatch.setattr(auth.config, "SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.setattr(auth.config, "SMTP_FROM", "locker@ejemplo.com")
    monkeypatch.setattr(auth.config, "SMTP_USER", None)

    tareas = BackgroundTasks()
    db = SessionLocal()
    try:
        respuesta = auth.solicitar_recuperacion(
            auth.SolicitudRecuperacion(email="ana@ejemplo.com"),
            _peticion(),
            tareas,
            db,
        )
    finally:
        db.close()

    # La respuesta no espera al SMTP ni expone el código.
    assert "reset_token" not in respuesta
    assert enviados == []
    assert len(tareas.tasks) == 1

    tarea = tareas.tasks[0]
    tarea.func(*tarea.args, **tarea.kwargs)
    assert enviados[0][0] == "ana@ejemplo.com"
    assert enviados[0][1]


def test_sin_smtp_local_el_codigo_se_devuelve_sin_programar_correo(cliente, monkeypatch):
    _registrar(cliente)
    monkeypatch.setattr(auth.config, "SMTP_HOST", None)
    monkeypatch.setattr(auth.config, "SMTP_FROM", None)

    tareas = BackgroundTasks()
    db = SessionLocal()
    try:
        respuesta = auth.solicitar_recuperacion(
            auth.SolicitudRecuperacion(email="ana@ejemplo.com"),
            _peticion(),
            tareas,
            db,
        )
    finally:
        db.close()

    assert respuesta["reset_token"]
    assert tareas.tasks == []


# ---------- Configuración CORS ----------


def test_cors_rechaza_el_comodin():
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Configuracion(SECRET_KEY=SECRET_KEY, CORS_ORIGINS="http://localhost:5173,*")


def test_cors_normaliza_los_origenes():
    configuracion = Configuracion(
        SECRET_KEY=SECRET_KEY,
        CORS_ORIGINS=" http://localhost:5173 , https://locker.ejemplo.com ",
    )

    assert configuracion.origenes_cors == [
        "http://localhost:5173",
        "https://locker.ejemplo.com",
    ]
