import pytest

from schemas import LONGITUD_MAXIMA_URL, normalizar_url


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("react.dev", "https://react.dev"),
        ("localhost:3000", "https://localhost:3000"),
        ("example.com:8443/ruta", "https://example.com:8443/ruta"),
        ("http://localhost:3000", "http://localhost:3000"),
        ("  https://ejemplo.com/ruta  ", "https://ejemplo.com/ruta"),
        # El esquema es válido sin importar mayúsculas y se normaliza a minúsculas.
        ("HTTP://ejemplo.com", "http://ejemplo.com"),
        ("HTTPS://Ejemplo.com/Ruta", "https://ejemplo.com/Ruta"),
        # El host se guarda en minúsculas y la barra final redundante se quita.
        ("https://Ejemplo.COM", "https://ejemplo.com"),
        ("https://ejemplo.com/", "https://ejemplo.com"),
        ("https://ejemplo.com/ruta/", "https://ejemplo.com/ruta"),
        ("https://EJEMPLO.com:8443/Ruta/", "https://ejemplo.com:8443/Ruta"),
        ("https://ejemplo.com/?a=1", "https://ejemplo.com/?a=1"),
    ],
)
def test_normaliza_urls_sin_esquema_o_con_esquema(entrada, esperado):
    assert normalizar_url(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "javascript:alert(1)",
        "JaVaScRiPt:alert(1)",
        "data:text/html,<h1>x</h1>",
        "file:///etc/passwd",
        "vbscript:msgbox(1)",
        "blob:https://ejemplo.com/identificador",
        "mailto:ana@ejemplo.com",
        "tel:+51999999999",
        "ftp://ejemplo.com",
        "http://",
        "https://",
        "http:///ruta",
        "",
        "   ",
        "https://ejemplo.com/ruta con espacios",
        "https://" + "a" * LONGITUD_MAXIMA_URL,
    ],
)
def test_rechaza_urls_peligrosas_o_invalidas(entrada):
    with pytest.raises(ValueError):
        normalizar_url(entrada)
