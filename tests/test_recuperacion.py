import time

from fastapi import BackgroundTasks
from starlette.requests import Request

from config import config
from correo import enmascarar_email, enviar_codigo_recuperacion
from database import SessionLocal
from routers import auth as auth_router


def _peticion_local() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/recuperar",
            "headers": [],
            "client": ("127.0.0.1", 50000),
        }
    )


def test_recuperar_no_espera_al_envio_del_correo(cliente, monkeypatch):
    """El endpoint encola el SMTP y responde aunque el envío tarde 2 segundos."""
    assert cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": "ana@ejemplo.com", "password": "secreto123"},
    ).status_code == 200

    monkeypatch.setattr(config, "SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.setattr(config, "SMTP_FROM", "locker@ejemplo.com")

    llamadas = []

    def envio_lento(destinatario, codigo):
        llamadas.append((destinatario, codigo))
        time.sleep(2)
        return True

    monkeypatch.setattr(auth_router, "enviar_codigo_recuperacion", envio_lento)

    tareas = BackgroundTasks()
    db = SessionLocal()
    try:
        inicio = time.perf_counter()
        respuesta = auth_router.solicitar_recuperacion(
            auth_router.SolicitudRecuperacion(email="ana@ejemplo.com"),
            _peticion_local(),
            tareas,
            db,
        )
        duracion = time.perf_counter() - inicio
    finally:
        db.close()

    # La petición no espera al SMTP: el envío queda encolado.
    assert duracion < 1.0
    assert len(tareas.tasks) == 1
    assert "reset_token" not in respuesta
    assert llamadas == []  # aún no se ha ejecutado la tarea en segundo plano


def test_recuperar_responde_igual_exista_o_no_el_correo(cliente, monkeypatch):
    assert cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": "ana@ejemplo.com", "password": "secreto123"},
    ).status_code == 200

    monkeypatch.setattr(config, "SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.setattr(config, "SMTP_FROM", "locker@ejemplo.com")
    enviados = []
    monkeypatch.setattr(
        auth_router,
        "enviar_codigo_recuperacion",
        lambda destinatario, codigo: enviados.append(destinatario) or True,
    )

    existente = cliente.post("/auth/recuperar", json={"email": "ana@ejemplo.com"})
    inexistente = cliente.post("/auth/recuperar", json={"email": "nadie@ejemplo.com"})

    assert existente.status_code == inexistente.status_code == 200
    assert existente.json() == inexistente.json()
    assert "reset_token" not in existente.json()
    assert enviados == ["ana@ejemplo.com"]


def test_los_logs_no_incluyen_el_correo_completo(cliente, monkeypatch, caplog):
    monkeypatch.setattr(config, "SMTP_HOST", None)
    monkeypatch.setattr(config, "SMTP_FROM", None)

    with caplog.at_level("WARNING", logger="locker.correo"):
        assert enviar_codigo_recuperacion("ana@ejemplo.com", "123456") is False

    assert "ana@ejemplo.com" not in caplog.text
    assert enmascarar_email("ana@ejemplo.com") in caplog.text


def test_enmascarar_email_no_revela_la_parte_local():
    assert enmascarar_email("ana@ejemplo.com") == "a***@ejemplo.com"
    assert enmascarar_email("a@ejemplo.com") == "a***@ejemplo.com"
    assert enmascarar_email("sin-arroba") == "***"
    assert enmascarar_email("") == "***"
    assert "ana" not in enmascarar_email("ana@ejemplo.com")
