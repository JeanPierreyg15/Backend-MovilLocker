"""Unicidad de (user_id, url) y limpieza de duplicados previos

Revision ID: 0003_urls_unicas
Revises: 0002_columnas_perfil
Create Date: 2026-11-10

Antes de crear la restricción se fusionan los duplicados existentes: se
conserva el link más antiguo (id menor) y se le añaden las etiquetas del resto.
"""

from typing import Sequence, Union
from urllib.parse import urlsplit, urlunsplit

from alembic import op
import sqlalchemy as sa

revision: str = "0003_urls_unicas"
down_revision: Union[str, None] = "0002_columnas_perfil"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalizar(url: str) -> str:
    """Misma idea que schemas.normalizar_url, sin depender del código actual."""
    try:
        partes = urlsplit(url)
        netloc = partes.netloc.lower()
        ruta = partes.path
        if not partes.query and not partes.fragment:
            if ruta == "/":
                ruta = ""
            elif ruta.endswith("/"):
                ruta = ruta[:-1]
        return urlunsplit(
            (partes.scheme.lower(), netloc, ruta, partes.query, partes.fragment)
        )
    except ValueError:
        return url


def _fusionar_duplicados(conexion) -> None:
    filas = conexion.execute(
        sa.text("SELECT id, user_id, url FROM links ORDER BY id")
    ).mappings().all()

    grupos: dict[tuple[int, str], list[int]] = {}
    for fila in filas:
        clave = (fila["user_id"], _normalizar(fila["url"]))
        grupos.setdefault(clave, []).append(fila["id"])

    for (_, url_normalizada), ids in grupos.items():
        conservar = ids[0]
        # También se normaliza la URL conservada: si no, la restricción exacta
        # (user_id, url) no protegería frente a variantes de mayúsculas/barra.
        conexion.execute(
            sa.text("UPDATE links SET url = :url WHERE id = :id"),
            {"url": url_normalizada, "id": conservar},
        )
        for duplicado in ids[1:]:
            etiquetas = conexion.execute(
                sa.text("SELECT tag_id FROM link_tags WHERE link_id = :duplicado"),
                {"duplicado": duplicado},
            ).scalars().all()
            for tag_id in etiquetas:
                ya_existe = conexion.execute(
                    sa.text(
                        "SELECT 1 FROM link_tags "
                        "WHERE link_id = :conservar AND tag_id = :tag_id"
                    ),
                    {"conservar": conservar, "tag_id": tag_id},
                ).first()
                if not ya_existe:
                    conexion.execute(
                        sa.text(
                            "INSERT INTO link_tags (link_id, tag_id) "
                            "VALUES (:conservar, :tag_id)"
                        ),
                        {"conservar": conservar, "tag_id": tag_id},
                    )
            conexion.execute(
                sa.text("DELETE FROM link_tags WHERE link_id = :duplicado"),
                {"duplicado": duplicado},
            )
            conexion.execute(
                sa.text("DELETE FROM links WHERE id = :duplicado"),
                {"duplicado": duplicado},
            )


def upgrade() -> None:
    _fusionar_duplicados(op.get_bind())
    with op.batch_alter_table("links") as batch:
        batch.create_unique_constraint(
            "uq_links_usuario_url", ["user_id", "url"]
        )


def downgrade() -> None:
    with op.batch_alter_table("links") as batch:
        batch.drop_constraint("uq_links_usuario_url", type_="unique")
