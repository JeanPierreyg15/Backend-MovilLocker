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


# ---------- Miniaturas ----------

@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?t=10",
        "https://m.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
    ],
)
def test_miniatura_youtube_sin_descargar(url):
    assert scraper.miniatura_youtube(url) == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"


def test_miniatura_youtube_ignora_urls_sin_video():
    assert scraper.miniatura_youtube("https://www.youtube.com/@canal") is None
    assert scraper.miniatura_youtube("https://ejemplo.com/watch?v=dQw4w9WgXcQ") is None


def test_miniatura_solo_en_sitios_multimedia():
    html_video = '<meta property="og:image" content="https://i.vimeocdn.com/v.jpg?f=webp&amp;amp;r=us">'
    vista = scraper.extraer_metadatos(html_video, "https://vimeo.com/123")
    assert vista.miniatura == "https://i.vimeocdn.com/v.jpg?f=webp&r=us"

    # og:type video en un dominio cualquiera también cuenta como multimedia.
    html_tipo = '<meta property="og:type" content="video.other"><meta property="og:image" content="https://cdn.x/v.jpg">'
    assert scraper.extraer_metadatos(html_tipo, "https://videos.ejemplo.com/1").miniatura == "https://cdn.x/v.jpg"

    # Página normal: hay og:image pero no se usa como miniatura (se verá el favicon).
    vista_normal = scraper.extraer_metadatos(HTML_OG, "https://ejemplo.com/articulo")
    assert vista_normal.imagen is not None
    assert vista_normal.miniatura is None


def test_link_guarda_y_actualiza_la_miniatura(cliente):
    cabeceras = _cabeceras(cliente)
    miniatura = "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"

    creado = cliente.post(
        "/links/",
        json={"url": "https://youtu.be/dQw4w9WgXcQ", "titulo": "Video", "imagen": miniatura},
        headers=cabeceras,
    )
    assert creado.status_code == 200
    assert creado.json()["imagen"] == miniatura

    actualizado = cliente.put(
        f"/links/{creado.json()['id']}",
        json={"url": "https://ejemplo.com", "titulo": "Normal", "imagen": None},
        headers=cabeceras,
    )
    assert actualizado.json()["imagen"] is None

    rechazado = cliente.post(
        "/links/",
        json={"url": "https://otro.com", "titulo": "X", "imagen": "javascript:alert(1)"},
        headers=cabeceras,
    )
    assert rechazado.status_code == 422


def test_preview_sin_conexion_conserva_miniatura_de_youtube(cliente, monkeypatch):
    cabeceras = _cabeceras(cliente)

    def falla(url):
        raise scraper.ErrorVistaPrevia("bloqueado")

    monkeypatch.setattr(scraper, "obtener_vista_previa", falla)
    respuesta = cliente.get(
        "/links/preview", params={"url": "https://youtu.be/dQw4w9WgXcQ"}, headers=cabeceras
    )
    assert respuesta.json()["miniatura"] == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"


HTML_YOUTUBE_GENERICO = """
<html><head>
<title>YouTube</title>
<meta property="og:title" content="YouTube">
<meta property="og:description" content="Comparte videos con tus amigos, familiares y el resto del mundo">
<meta property="og:image" content="https://m.youtube.com/static/favicon.ico">
</head></html>
"""


def test_youtube_generico_usa_oembed_para_el_titulo_real(monkeypatch):
    monkeypatch.setattr(
        scraper, "_descargar_html", lambda url: (url, HTML_YOUTUBE_GENERICO)
    )
    monkeypatch.setattr(
        scraper,
        "_descargar_json",
        lambda url: {
            "title": "Rick Astley - Never Gonna Give You Up",
            "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        },
    )

    vista = scraper.obtener_vista_previa("https://m.youtube.com/watch?v=dQw4w9WgXcQ")

    assert vista.titulo == "Rick Astley - Never Gonna Give You Up"
    assert vista.descripcion is None
    assert vista.sitio == "YouTube"
    assert vista.miniatura == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"


def test_youtube_generico_sin_oembed_no_inventa_titulo(monkeypatch):
    monkeypatch.setattr(
        scraper, "_descargar_html", lambda url: (url, HTML_YOUTUBE_GENERICO)
    )

    def sin_oembed(url):
        raise scraper.ErrorVistaPrevia("404")

    monkeypatch.setattr(scraper, "_descargar_json", sin_oembed)

    vista = scraper.obtener_vista_previa("https://m.youtube.com/watch?v=dQw4w9WgXcQ")

    assert vista.titulo is None
    assert vista.descripcion is None
    # Nunca el favicon del sitio: la miniatura fiable sale del ID del video.
    assert vista.miniatura == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"


def test_youtube_generico_no_usa_el_favicon_como_miniatura():
    vista = scraper.extraer_metadatos(
        HTML_YOUTUBE_GENERICO, "https://m.youtube.com/watch?v=dQw4w9WgXcQ"
    )
    assert vista.imagen == "https://m.youtube.com/static/favicon.ico"
    assert vista.miniatura == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"


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
        "miniatura": None,
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
