"""Vista previa de enlaces (web scraping ligero).

Descarga la página indicada y extrae título, descripción, imagen y nombre del
sitio a partir de <title> y de las etiquetas Open Graph / Twitter Card.

Solo usa la biblioteca estándar. Medidas de seguridad:

- Protección SSRF: el host se resuelve y se rechaza cualquier IP que no sea
  pública (loopback, red privada, link-local, metadatos de la nube...). Las
  redirecciones se siguen a mano para volver a validar cada salto.
- Tiempo de espera corto, máximo de redirecciones y de bytes descargados.
- Solo se procesan respuestas HTML.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from html import unescape
from urllib.parse import parse_qs, quote, urljoin, urlparse

TIEMPO_ESPERA_SEGUNDOS = 6
MAXIMO_BYTES = 1_000_000
MAXIMO_REDIRECCIONES = 4
LONGITUD_MAXIMA_TITULO = 200
LONGITUD_MAXIMA_DESCRIPCION = 300
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Mobile Safari/537.36 LockerPreview/1.0"
)


class ErrorVistaPrevia(Exception):
    """La página no se pudo consultar (red, tiempo de espera, no es HTML...)."""


class DestinoNoPermitido(ErrorVistaPrevia):
    """La URL apunta a una dirección no pública (posible SSRF)."""


@dataclass
class VistaPrevia:
    url: str
    titulo: str | None = None
    descripcion: str | None = None
    imagen: str | None = None
    sitio: str | None = None
    # Miniatura para la tarjeta del link: solo en sitios multimedia (videos,
    # música, reels...). En páginas normales queda None y se usa el favicon.
    miniatura: str | None = None


# ---------- Miniaturas de sitios multimedia ----------

# Dominios cuya og:image es la miniatura del contenido (y no un logo genérico).
DOMINIOS_MULTIMEDIA = {
    "youtube.com", "youtu.be", "vimeo.com", "dailymotion.com", "dai.ly",
    "twitch.tv", "tiktok.com", "instagram.com", "spotify.com", "soundcloud.com",
    "music.apple.com", "deezer.com", "bandcamp.com", "kick.com", "rumble.com",
    "facebook.com", "fb.watch", "pinterest.com", "flickr.com", "imgur.com",
    "behance.net", "dribbble.com",
}

_PATRON_ID_YOUTUBE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _dominio_base(host: str | None) -> str:
    host = (host or "").lower().removeprefix("www.").removeprefix("m.")
    return host


def _es_dominio_multimedia(host: str | None) -> bool:
    dominio = _dominio_base(host)
    return any(dominio == base or dominio.endswith("." + base) for base in DOMINIOS_MULTIMEDIA)


def id_video_youtube(url: str) -> str | None:
    """ID del video en youtube.com/watch?v=, youtu.be/, /shorts/, /embed/, /live/."""
    partes = urlparse(url)
    dominio = _dominio_base(partes.hostname)
    candidato = None
    if dominio == "youtu.be":
        candidato = partes.path.strip("/").split("/")[0]
    elif dominio == "youtube.com" or dominio.endswith(".youtube.com"):
        if partes.path == "/watch":
            candidato = parse_qs(partes.query).get("v", [None])[0]
        else:
            segmentos = partes.path.strip("/").split("/")
            if len(segmentos) >= 2 and segmentos[0] in {"shorts", "embed", "live", "v"}:
                candidato = segmentos[1]
    return candidato if candidato and _PATRON_ID_YOUTUBE.fullmatch(candidato) else None


def miniatura_youtube(url: str) -> str | None:
    """Miniatura por defecto del video (existe siempre, sin descargar la página)."""
    video = id_video_youtube(url)
    return f"https://i.ytimg.com/vi/{video}/hqdefault.jpg" if video else None


def _es_dominio_youtube(host: str | None) -> bool:
    dominio = _dominio_base(host)
    return dominio == "youtube.com" or dominio == "youtu.be" or dominio.endswith(".youtube.com")


def _es_url_youtube(url: str) -> bool:
    return _es_dominio_youtube(urlparse(url).hostname)


def _es_imagen_youtube(valor: str | None) -> bool:
    """Imagen alojada en los CDN de YouTube (no el favicon del sitio)."""
    host = _dominio_base(urlparse(valor or "").hostname)
    return any(
        host == base or host.endswith("." + base)
        for base in ("ytimg.com", "ggpht.com", "googleusercontent.com")
    )


def _parece_icono(valor: str | None) -> bool:
    ruta = urlparse(valor or "").path.lower()
    return ruta.endswith(".ico") or "favicon" in ruta


def elegir_miniatura(url: str, imagen: str | None, tipo_og: str | None) -> str | None:
    """Miniatura solo para contenido multimedia; None en páginas normales."""
    tipo = (tipo_og or "").lower()
    multimedia = _es_dominio_multimedia(urlparse(url).hostname) or tipo.startswith(("video", "music"))
    video = miniatura_youtube(url)
    if video:
        # En YouTube el og:image puede ser el favicon (páginas genéricas): solo
        # se usa si es una imagen real del video; si no, la del ID (existe siempre).
        if imagen and _es_imagen_youtube(imagen) and not _parece_icono(imagen):
            return imagen
        return video
    if imagen and multimedia and not _parece_icono(imagen):
        return imagen
    return None


# ---------- Validación del destino ----------

def _ip_publica(direccion: str) -> bool:
    try:
        ip = ipaddress.ip_address(direccion.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def validar_destino(url: str) -> None:
    """Lanza DestinoNoPermitido si la URL no es http(s) o resuelve a una IP no pública."""
    partes = urlparse(url)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise DestinoNoPermitido("La URL debe usar http o https")
    try:
        puerto = partes.port or (443 if partes.scheme == "https" else 80)
        resultados = socket.getaddrinfo(partes.hostname, puerto, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, ValueError) as error:
        raise ErrorVistaPrevia("No se encontró el sitio") from error
    if not resultados or not all(_ip_publica(r[4][0]) for r in resultados):
        raise DestinoNoPermitido("La URL apunta a una dirección no permitida")


# ---------- Descarga ----------

class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    """Hace que urllib devuelva el 3xx como HTTPError para validarlo a mano."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


_abridor = urllib.request.build_opener(_SinRedirecciones)


def _descargar_html(url: str) -> tuple[str, str]:
    """Devuelve (url_final, html). Sigue redirecciones validando cada salto."""
    actual = url
    for _ in range(MAXIMO_REDIRECCIONES + 1):
        validar_destino(actual)
        peticion = urllib.request.Request(
            actual,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                "Accept-Language": "es,en;q=0.8",
                "Accept-Encoding": "identity",
            },
        )
        try:
            with _abridor.open(peticion, timeout=TIEMPO_ESPERA_SEGUNDOS) as respuesta:
                tipo = respuesta.headers.get_content_type() or ""
                if "html" not in tipo:
                    raise ErrorVistaPrevia("La página no es HTML")
                cuerpo = respuesta.read(MAXIMO_BYTES)
                charset = respuesta.headers.get_content_charset() or _charset_meta(cuerpo) or "utf-8"
                try:
                    texto = cuerpo.decode(charset, errors="replace")
                except LookupError:
                    texto = cuerpo.decode("utf-8", errors="replace")
                return respuesta.geturl() or actual, texto
        except urllib.error.HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                destino = error.headers.get("Location")
                if not destino:
                    raise ErrorVistaPrevia("Redirección sin destino") from None
                actual = urljoin(actual, destino)
                continue
            raise ErrorVistaPrevia(f"El sitio respondió {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            raise ErrorVistaPrevia("No se pudo conectar con el sitio") from error
    raise ErrorVistaPrevia("Demasiadas redirecciones")


def _charset_meta(cuerpo: bytes) -> str | None:
    coincidencia = re.search(rb"<meta[^>]+charset=[\"']?([A-Za-z0-9_-]+)", cuerpo[:4096], re.IGNORECASE)
    return coincidencia.group(1).decode("ascii") if coincidencia else None


def _descargar_json(url: str) -> dict:
    """Descarga una respuesta JSON pequeña (p. ej. el oEmbed de YouTube)."""
    peticion = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with _abridor.open(peticion, timeout=TIEMPO_ESPERA_SEGUNDOS) as respuesta:
            cuerpo = respuesta.read(MAXIMO_BYTES)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise ErrorVistaPrevia("No se pudo consultar el servicio") from error
    try:
        datos = json.loads(cuerpo.decode("utf-8", errors="replace"))
    except (UnicodeError, ValueError) as error:
        raise ErrorVistaPrevia("Respuesta no válida") from error
    if not isinstance(datos, dict):
        raise ErrorVistaPrevia("Respuesta no válida")
    return datos


# ---------- Análisis del HTML ----------

class _ExtractorMetadatos(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.titulo_partes: list[str] = []
        self.icono: str | None = None
        self._en_titulo = False
        self._titulo_listo = False

    def handle_starttag(self, tag, attrs):
        atributos = {clave.lower(): (valor or "") for clave, valor in attrs}
        if tag == "meta":
            clave = (atributos.get("property") or atributos.get("name") or "").strip().lower()
            contenido = atributos.get("content", "").strip()
            if clave and contenido and clave not in self.meta:
                self.meta[clave] = contenido
        elif tag == "title" and not self._titulo_listo:
            self._en_titulo = True
        elif tag == "link" and self.icono is None:
            rel = atributos.get("rel", "").lower().split()
            if "icon" in rel or "apple-touch-icon" in rel:
                self.icono = atributos.get("href") or None

    def handle_endtag(self, tag):
        if tag == "title" and self._en_titulo:
            self._en_titulo = False
            self._titulo_listo = True

    def handle_data(self, data):
        if self._en_titulo:
            self.titulo_partes.append(data)


def _limpiar(texto: str | None, maximo: int) -> str | None:
    if not texto:
        return None
    limpio = re.sub(r"\s+", " ", texto).strip()
    if not limpio:
        return None
    if len(limpio) > maximo:
        limpio = limpio[: maximo - 1].rstrip() + "…"
    return limpio


def _url_absoluta(base: str, valor: str | None) -> str | None:
    if not valor:
        return None
    # Algunos sitios (p. ej. Vimeo) escapan dos veces: "...?f=webp&amp;region=us".
    absoluta = urljoin(base, unescape(valor.strip()))
    return absoluta if urlparse(absoluta).scheme in ("http", "https") else None


def extraer_metadatos(html: str, url_base: str) -> VistaPrevia:
    extractor = _ExtractorMetadatos()
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:  # noqa: BLE001  HTML muy roto: nos quedamos con lo leído
        pass
    meta = extractor.meta

    titulo = (
        meta.get("og:title")
        or meta.get("twitter:title")
        or "".join(extractor.titulo_partes)
    )
    descripcion = (
        meta.get("og:description")
        or meta.get("twitter:description")
        or meta.get("description")
    )
    imagen = (
        meta.get("og:image:secure_url")
        or meta.get("og:image")
        or meta.get("og:image:url")
        or meta.get("twitter:image")
        or meta.get("twitter:image:src")
        or extractor.icono
    )
    sitio = meta.get("og:site_name") or meta.get("application-name") or urlparse(url_base).hostname
    imagen_absoluta = _url_absoluta(url_base, imagen)

    return VistaPrevia(
        url=url_base,
        titulo=_limpiar(titulo, LONGITUD_MAXIMA_TITULO),
        descripcion=_limpiar(descripcion, LONGITUD_MAXIMA_DESCRIPCION),
        imagen=imagen_absoluta,
        sitio=_limpiar(sitio, 80),
        miniatura=elegir_miniatura(url_base, imagen_absoluta, meta.get("og:type")),
    )


def obtener_vista_previa(url: str) -> VistaPrevia:
    """Descarga la URL y devuelve sus metadatos. Lanza ErrorVistaPrevia si falla."""
    url_final, html = _descargar_html(url)
    vista = extraer_metadatos(html, url_final)
    # Se devuelve la URL pedida (la que se guardará), no la final tras redirecciones.
    vista.url = url
    if _es_url_youtube(url) and (_es_pagina_generica_youtube(url, vista) or not vista.titulo):
        vista = _completar_con_oembed(url, vista)
    vista.miniatura = vista.miniatura or miniatura_youtube(url)
    return vista


def _es_pagina_generica_youtube(url: str, vista: VistaPrevia) -> bool:
    """YouTube responde con su portada (título "YouTube" y descripción genérica)
    cuando el ID no existe, el video es privado o sirve una página de consentimiento."""
    if not _es_url_youtube(url):
        return False
    titulo = (vista.titulo or "").strip().casefold()
    descripcion = (vista.descripcion or "").casefold()
    generica = any(
        pista in descripcion for pista in ("comparte", "enjoy", "share", "teile")
    )
    return titulo in {"youtube", "youtube - inicio", "youtube - home", "youtube - reproduce"} and (
        not descripcion or generica
    )


def _completar_con_oembed(url: str, vista: VistaPrevia) -> VistaPrevia:
    """Pide los datos del video al oEmbed de YouTube.

    A diferencia del HTML, oEmbed devuelve el título y la miniatura reales aunque
    YouTube sirva la portada. Si tampoco responde (ID inválido o video no
    disponible), se descartan los metadatos genéricos para no autocompletar un
    título falso como "YouTube".
    """
    oembed = _vista_previa_oembed(url)
    if oembed:
        vista.titulo = oembed.titulo
        vista.descripcion = oembed.descripcion
        vista.imagen = oembed.imagen
        vista.sitio = "YouTube"
        vista.miniatura = oembed.miniatura
        return vista
    vista.titulo = None
    vista.descripcion = None
    vista.sitio = vista.sitio or "YouTube"
    vista.miniatura = miniatura_youtube(url)
    return vista


def _vista_previa_oembed(url: str) -> VistaPrevia | None:
    if not id_video_youtube(url):
        return None
    try:
        datos = _descargar_json(
            f"https://www.youtube.com/oembed?format=json&url={quote(url, safe='')}"
        )
    except ErrorVistaPrevia:
        return None
    titulo = datos.get("title")
    titulo = _limpiar(titulo, LONGITUD_MAXIMA_TITULO) if isinstance(titulo, str) else None
    if not titulo:
        return None
    miniatura = datos.get("thumbnail_url")
    miniatura = (
        _url_absoluta("https://www.youtube.com", miniatura)
        if isinstance(miniatura, str)
        else None
    )
    return VistaPrevia(
        url=url,
        titulo=titulo,
        sitio="YouTube",
        imagen=miniatura,
        miniatura=miniatura or miniatura_youtube(url),
    )
