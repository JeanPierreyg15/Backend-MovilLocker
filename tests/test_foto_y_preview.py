"""Foto de perfil y vista previa de enlaces (web scraping)."""

import pytest

import scraper

FOTO_VALIDA = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"


def _cabeceras(cliente):
    cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": "ana@ejemplo.com", "password": "secreto123"},
    )
    respuesta = cliente.post(
        "/auth/login", json={"email": "ana@ejemplo.com", "password": "secreto123"}
    )
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


# ---------- Foto de perfil ----------

def test_subir_y_quitar_foto_de_perfil(cliente):
    cabeceras = _cabeceras(cliente)

    respuesta = cliente.put("/auth/foto", json={"imagen": FOTO_VALIDA}, headers=cabeceras)
    assert respuesta.status_code == 200
    assert respuesta.json()["avatar_imagen"] == FOTO_VALIDA
    assert cliente.get("/auth/me", headers=cabeceras).json()["avatar_imagen"] == FOTO_VALIDA

    respuesta = cliente.delete("/auth/foto", headers=cabeceras)
    assert respuesta.status_code == 200
    assert respuesta.json()["avatar_imagen"] is None


@pytest.mark.parametrize(
    "imagen",
    [
        "https://ejemplo.com/foto.jpg",
        "data:text/html;base64,PGgxPmhvbGE8L2gxPg==",
        "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
        "data:image/png;base64," + "A" * 600_000,
    ],
    ids=["url-externa", "html", "svg", "demasiado-grande"],
)
def test_foto_rechaza_formatos_no_validos(cliente, imagen):
    cabeceras = _cabeceras(cliente)
    respuesta = cliente.put("/auth/foto", json={"imagen": imagen}, headers=cabeceras)
    assert respuesta.status_code == 422


def test_foto_requiere_sesion(cliente):
    assert cliente.put("/auth/foto", json={"imagen": FOTO_VALIDA}).status_code == 401


# ---------- Extracción de metadatos ----------

HTML_OG = """
<html><head>
<meta charset="utf-8">
<title>  Título del &lt;title&gt;  </title>
<meta property="og:title" content="Título Open Graph">
<meta property="og:description" content="Una descripción   con   espacios">
<meta property="og:image" content="/img/portada.png">
<meta property="og:site_name" content="Mi Sitio">
</head><body></body></html>
"""


def test_extrae_open_graph_y_resuelve_imagen_relativa():
    vista = scraper.extraer_metadatos(HTML_OG, "https://ejemplo.com/articulo")
    assert vista.titulo == "Título Open Graph"
    assert vista.descripcion == "Una descripción con espacios"
    assert vista.imagen == "https://ejemplo.com/img/portada.png"
    assert vista.sitio == "Mi Sitio"


def test_usa_title_si_no_hay_open_graph():
    html = "<html><head><title>Solo &amp; title</title><link rel='icon' href='/favicon.ico'></head></html>"
    vista = scraper.extraer_metadatos(html, "https://ejemplo.com")
    assert vista.titulo == "Solo & title"
    assert vista.imagen == "https://ejemplo.com/favicon.ico"
    assert vista.sitio == "ejemplo.com"


def test_ignora_imagenes_con_esquemas_peligrosos():
    html = '<meta property="og:image" content="javascript:alert(1)">'
    assert scraper.extraer_metadatos(html, "https://ejemplo.com").imagen is None


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8000/", "http://localhost/", "http://10.0.0.5/", "http://169.254.169.254/latest"],
)
def test_validar_destino_bloquea_direcciones_internas(url):
    with pytest.raises(scraper.DestinoNoPermitido):
        scraper.validar_destino(url)


# ---------- Endpoint /links/preview ----------

def test_preview_devuelve_metadatos(cliente, monkeypatch):
    cabeceras = _cabeceras(cliente)
    llamadas = []

    def falso(url):
        llamadas.append(url)
        return scraper.VistaPrevia(url=url, titulo="Hola", descripcion="Desc", imagen="https://e.com/i.png", sitio="E")

    monkeypatch.setattr(scraper, "obtener_vista_previa", falso)
    respuesta = cliente.get("/links/preview", params={"url": "Ejemplo.com/"}, headers=cabeceras)

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "url": "https://ejemplo.com",
        "titulo": "Hola",
        "descripcion": "Desc",
        "imagen": "https://e.com/i.png",
        "sitio": "E",
    }
    # Se scrapea la URL ya normalizada.
    assert llamadas == ["https://ejemplo.com"]


def test_preview_sin_conexion_responde_vacio(cliente, monkeypatch):
    cabeceras = _cabeceras(cliente)

    def falla(url):
        raise scraper.ErrorVistaPrevia("caído")

    monkeypatch.setattr(scraper, "obtener_vista_previa", falla)
    respuesta = cliente.get("/links/preview", params={"url": "https://caido.dev"}, headers=cabeceras)

    assert respuesta.status_code == 200
    assert respuesta.json()["titulo"] is None
    assert respuesta.json()["sitio"] == "caido.dev"


def test_preview_rechaza_localhost(cliente):
    cabeceras = _cabeceras(cliente)
    respuesta = cliente.get("/links/preview", params={"url": "http://127.0.0.1:8000/docs"}, headers=cabeceras)
    assert respuesta.status_code == 400


def test_preview_rechaza_esquemas_no_http(cliente):
    cabeceras = _cabeceras(cliente)
    respuesta = cliente.get("/links/preview", params={"url": "javascript:alert(1)"}, headers=cabeceras)
    assert respuesta.status_code == 400


def test_preview_requiere_sesion(cliente):
    assert cliente.get("/links/preview", params={"url": "https://a.com"}).status_code == 401
