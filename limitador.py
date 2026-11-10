"""Rate limiting sencillo en memoria.

Limitaciones conocidas:

- El contador vive en el proceso: con varios workers (o varias réplicas) cada
  uno lleva su propia cuenta, así que el límite real se multiplica. Para
  producción con varios workers hace falta un almacén compartido (Redis) o un
  proxy que limite antes de llegar a la app.
- Las claves se purgan periódicamente para que el diccionario no crezca sin
  fin, pero un reinicio del proceso reinicia todos los contadores.
"""

import ipaddress
import logging
import time
from typing import Sequence

from fastapi import HTTPException, Request, status

from config import config

logger = logging.getLogger("locker.limitador")

_intentos: dict[str, list[float]] = {}
_ultima_purga = 0.0
_PURGA_CADA_SEGUNDOS = 60
_VENTANA_MAXIMA = 3600


def _ahora() -> float:
    """Reloj aislado para poder simular el paso del tiempo en los tests."""
    return time.time()


def reiniciar() -> None:
    """Vacía todos los contadores (usado por los tests)."""
    global _ultima_purga
    _intentos.clear()
    _ultima_purga = 0.0


def _es_proxy_confiable(host: str) -> bool:
    if not host:
        return False
    try:
        direccion = ipaddress.ip_address(host)
    except ValueError:
        return False
    for red in config.proxies_confiables:
        try:
            if direccion in ipaddress.ip_network(red, strict=False):
                return True
        except ValueError:
            logger.warning("TRUSTED_PROXIES contiene una entrada inválida: %s", red)
    return False


def ip_cliente(request: Request) -> str:
    """IP real de la petición.

    Solo se usa ``X-Forwarded-For`` si la petición llega directamente desde un
    proxy incluido en ``TRUSTED_PROXIES``; en caso contrario se ignora (un
    cliente podría falsearla para saltarse el límite).
    """
    host = request.client.host if request.client else ""
    if not host:
        return "desconocido"
    if _es_proxy_confiable(host):
        reenviada = request.headers.get("x-forwarded-for", "")
        if reenviada:
            primera = reenviada.split(",")[0].strip()
            if primera:
                return primera
    return host


def _purgar(ahora: float) -> None:
    global _ultima_purga
    if ahora - _ultima_purga < _PURGA_CADA_SEGUNDOS:
        return
    _ultima_purga = ahora
    obsoletas = [
        clave
        for clave, marcas in _intentos.items()
        if not marcas or ahora - max(marcas) >= _VENTANA_MAXIMA
    ]
    for clave in obsoletas:
        del _intentos[clave]


def _limitar_clave(clave: str, maximo: int, ventana_segundos: int, ahora: float) -> None:
    marcas = [marca for marca in _intentos.get(clave, []) if ahora - marca < ventana_segundos]
    if len(marcas) >= maximo:
        _intentos[clave] = marcas
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos. Espera un momento e inténtalo de nuevo.",
        )
    marcas.append(ahora)
    _intentos[clave] = marcas


def limitar_peticiones(
    request: Request,
    accion: str,
    maximo: int,
    ventana_segundos: int = 60,
    claves_extra: Sequence[str] = (),
    incluir_ip: bool = True,
) -> None:
    """Aplica el límite por IP y, opcionalmente, por cada clave adicional.

    ``claves_extra`` permite añadir cubos independientes (por usuario, por
    correo...). Para limitar una única combinación usar ``incluir_ip=False`` y
    pasar la IP dentro de la clave.
    """
    ahora = _ahora()
    _purgar(ahora)

    claves = [f"{accion}:ip:{ip_cliente(request)}"] if incluir_ip else []
    claves.extend(f"{accion}:{clave}" for clave in claves_extra)
    for clave in claves:
        _limitar_clave(clave, maximo, ventana_segundos, ahora)
