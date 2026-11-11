"""Regresión: URLs sin esquema con puerto y URLs peligrosas."""

import pytest

from schemas import normalizar_url


@pytest.mark.parametrize(
    "entrada, esperada",
    [
        ("localhost:3000", "https://localhost:3000"),
        ("midominio.com:8080/ruta", "https://midominio.com:8080/ruta"),
        ("midominio.com:8080?x=1", "https://midominio.com:8080?x=1"),
        ("midominio.com:8080#inicio", "https://midominio.com:8080#inicio"),
        ("https://ejemplo.com/ruta", "https://ejemplo.com/ruta"),
        ("http://localhost:8000", "http://localhost:8000"),
        ("react.dev", "https://react.dev"),
    ],
)
def test_normaliza_urls_validas(entrada, esperada):
    assert normalizar_url(entrada) == esperada


@pytest.mark.parametrize(
    "entrada",
    [
        "javascript:alert(1)",
        "data:text/html,<h1>x</h1>",
        "file:///etc/passwd",
        "mailto:ana@ejemplo.com",
        "ftp://ejemplo.com/archivo",
        "https://user@",
        "https://.",
        "http://.",
        "https://",
        "",
        "   ",
        "https://ejemplo.com/" + "x" * 2048,
    ],
)
def test_rechaza_urls_invalidas(entrada):
    with pytest.raises(ValueError):
        normalizar_url(entrada)


def test_limite_de_2048_caracteres():
    url = "https://ejemplo.com/" + "x" * (2048 - len("https://ejemplo.com/"))
    assert normalizar_url(url) == url

    with pytest.raises(ValueError, match="2048"):
        normalizar_url(url + "x")
