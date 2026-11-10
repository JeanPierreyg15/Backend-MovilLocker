import logging

from fastapi.testclient import TestClient

from main import app


def test_error_inesperado_devuelve_json_generico_sin_detalles(cliente, caplog):
    def fallar():
        raise RuntimeError("detalle interno: token=abc123")

    app.add_api_route("/_error_prueba", fallar, methods=["GET"])
    try:
        with caplog.at_level(logging.ERROR, logger="locker"):
            with TestClient(
                app,
                client=("127.0.0.1", 50000),
                raise_server_exceptions=False,
            ) as boom:
                respuesta = boom.get("/_error_prueba")
    finally:
        app.router.routes = [
            ruta
            for ruta in app.router.routes
            if getattr(ruta, "path", None) != "/_error_prueba"
        ]

    assert respuesta.status_code == 500
    assert respuesta.json() == {"detail": "Error interno del servidor"}
    assert "detalle interno" not in respuesta.text
    assert "Traceback" not in respuesta.text
    # La traza sí queda en el log del servidor.
    assert "Error no controlado" in caplog.text


def test_el_log_de_peticiones_no_incluye_tokens_ni_cuerpos(cliente, caplog):
    with caplog.at_level(logging.INFO, logger="locker"):
        respuesta = cliente.post(
            "/auth/login",
            json={"email": "nadie@ejemplo.com", "password": "clave-secreta-123"},
            headers={"Authorization": "Bearer token-secreto-abc"},
        )

    assert respuesta.status_code == 401
    assert "POST /auth/login -> 401" in caplog.text
    assert "clave-secreta-123" not in caplog.text
    assert "token-secreto-abc" not in caplog.text
