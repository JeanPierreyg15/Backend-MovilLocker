"""Canonicaliza las URLs de links y fusiona los duplicados resultantes

Hasta ahora `https://a.com` y `https://a.com/` se guardaban como links
distintos, y el host conservaba mayúsculas. Esta migración re-normaliza las
URLs existentes (esquema/host en minúsculas, sin puerto por defecto, sin
fragmento y sin la / final de la raíz) y fusiona los duplicados que aparezcan,
conservando el link más antiguo y uniendo sus etiquetas.

Es idempotente: se puede ejecutar varias veces sin cambiar nada.

Revision ID: 0005_urls_canonicas
Revises: 0004_integridad_links
Create Date: 2026-11-11
"""

from typing import Sequence, Union
from urllib.parse import urlparse, urlunparse

from alembic import op
import sqlalchemy as sa

revision: str = "0005_urls_canonicas"
down_revision: Union[str, None] = "0004_integridad_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDICE_URL_UNICA = "uq_links_usuario_url"


def _tablas() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _url_canonica(valor: str) -> str:
    """Misma canonicalización que schemas.normalizar_url, sin depender del código."""
    texto = (valor or "").strip()
    if not texto:
        return texto
    try:
        url = urlparse(texto)
        if url.scheme not in ("http", "https") or not url.hostname:
            return texto

        esquema = url.scheme.lower()
        host = url.hostname.lower()
        puerto = url.port
        if (esquema == "http" and puerto == 80) or (esquema == "https" and puerto == 443):
            puerto = None

        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        netloc = f"{host}:{puerto}" if puerto else host

        ruta = url.path or ""
        if ruta == "/":
            ruta = ""

        return urlunparse((esquema, netloc, ruta, url.params, url.query, ""))
    except ValueError:
        return texto


def _quitar_indice_unico() -> bool:
    """Suelta el índice único para poder re-normalizar sin chocar con él."""
    for indice in sa.inspect(op.get_bind()).get_indexes("links"):
        if indice.get("name") == INDICE_URL_UNICA:
            op.drop_index(INDICE_URL_UNICA, table_name="links")
            return True
    return False


def _fusionar_links_duplicados() -> None:
    conexion = op.get_bind()
    filas = conexion.execute(
        sa.text("SELECT id, user_id, url FROM links ORDER BY user_id, url, id")
    ).fetchall()

    conservados: dict[tuple[int, str], int] = {}
    for link_id, user_id, url in filas:
        clave = (user_id, url)
        if clave not in conservados:
            conservados[clave] = link_id
            continue

        keep_id = conservados[clave]
        etiquetas_keep = {
            tag_id
            for (tag_id,) in conexion.execute(
                sa.text("SELECT tag_id FROM link_tags WHERE link_id = :id"),
                {"id": keep_id},
            )
        }
        for (tag_id,) in conexion.execute(
            sa.text("SELECT tag_id FROM link_tags WHERE link_id = :id"),
            {"id": link_id},
        ):
            if tag_id not in etiquetas_keep:
                conexion.execute(
                    sa.text(
                        "INSERT INTO link_tags (link_id, tag_id) VALUES (:link_id, :tag_id)"
                    ),
                    {"link_id": keep_id, "tag_id": tag_id},
                )
                etiquetas_keep.add(tag_id)

        conexion.execute(
            sa.text("DELETE FROM link_tags WHERE link_id = :id"), {"id": link_id}
        )
        conexion.execute(sa.text("DELETE FROM links WHERE id = :id"), {"id": link_id})


def upgrade() -> None:
    if "links" not in _tablas():
        return

    habia_indice = _quitar_indice_unico()

    conexion = op.get_bind()
    filas = conexion.execute(sa.text("SELECT id, url FROM links")).fetchall()
    for link_id, url in filas:
        canonica = _url_canonica(url)
        if canonica != url:
            conexion.execute(
                sa.text("UPDATE links SET url = :url WHERE id = :id"),
                {"url": canonica, "id": link_id},
            )

    _fusionar_links_duplicados()

    if habia_indice:
        op.create_index(INDICE_URL_UNICA, "links", ["user_id", "url"], unique=True)


def downgrade() -> None:
    # La canonicalización no se puede revertir sin conocer la URL original.
    pass
