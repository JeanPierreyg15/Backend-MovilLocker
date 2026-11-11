"""Refuerza la integridad de links e índices de consulta

- Índice en link_tags.tag_id (la PK no acelera las búsquedas por etiqueta).
- Índice compuesto links(user_id, created_at) para el listado paginado.
- URL única por usuario también en la base de datos (antes solo se comprobaba
  en el router, así que dos peticiones simultáneas podían duplicarla).
  Los duplicados existentes se fusionan: se conserva el link más antiguo y se
  le añaden las etiquetas de los repetidos.

Revision ID: 0004_integridad_links
Revises: 0003_tags_normalizadas
Create Date: 2026-11-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_integridad_links"
down_revision: Union[str, None] = "0003_tags_normalizadas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDICE_TAG = "ix_link_tags_tag_id"
INDICE_LISTADO = "ix_links_user_created"
INDICE_URL_UNICA = "uq_links_usuario_url"


def _tablas() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indices(tabla: str) -> list[dict]:
    return sa.inspect(op.get_bind()).get_indexes(tabla)


def _tiene_indice(tabla: str, nombre: str, columnas: Sequence[str]) -> bool:
    esperadas = tuple(columnas)
    return any(
        indice.get("name") == nombre or tuple(indice.get("column_names") or ()) == esperadas
        for indice in _indices(tabla)
    )


def _tiene_unico(tabla: str, columnas: Sequence[str]) -> bool:
    esperadas = tuple(columnas)
    inspector = sa.inspect(op.get_bind())
    for restriccion in inspector.get_unique_constraints(tabla):
        if tuple(restriccion.get("column_names") or ()) == esperadas:
            return True
    return any(
        indice.get("unique") and tuple(indice.get("column_names") or ()) == esperadas
        for indice in _indices(tabla)
    )


def _fusionar_links_duplicados() -> None:
    """Conserva el link más antiguo de cada (usuario, url) y une sus etiquetas."""
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
    tablas = _tablas()

    if "link_tags" in tablas and not _tiene_indice("link_tags", INDICE_TAG, ["tag_id"]):
        op.create_index(INDICE_TAG, "link_tags", ["tag_id"], unique=False)

    if "links" in tablas:
        if not _tiene_indice("links", INDICE_LISTADO, ["user_id", "created_at"]):
            op.create_index(
                INDICE_LISTADO, "links", ["user_id", "created_at"], unique=False
            )

        if not _tiene_unico("links", ["user_id", "url"]):
            _fusionar_links_duplicados()
            op.create_index(
                INDICE_URL_UNICA, "links", ["user_id", "url"], unique=True
            )


def downgrade() -> None:
    tablas = _tablas()
    if "links" in tablas:
        for indice in _indices("links"):
            if indice.get("name") == INDICE_URL_UNICA:
                op.drop_index(INDICE_URL_UNICA, table_name="links")
                break
        for indice in _indices("links"):
            if indice.get("name") == INDICE_LISTADO:
                op.drop_index(INDICE_LISTADO, table_name="links")
                break

    if "link_tags" in tablas:
        for indice in _indices("link_tags"):
            if indice.get("name") == INDICE_TAG:
                op.drop_index(INDICE_TAG, table_name="link_tags")
                break
