"""Añade la miniatura (imagen) a links

Guarda la URL de la miniatura de los links multimedia (YouTube, Vimeo,
Spotify...). En páginas normales queda nula y la app muestra el favicon.

Revision ID: 0007_imagen_links
Revises: 0006_foto_perfil
Create Date: 2026-11-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_imagen_links"
down_revision: Union[str, None] = "0006_foto_perfil"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columnas(tabla: str) -> set[str]:
    return {columna["name"] for columna in sa.inspect(op.get_bind()).get_columns(tabla)}


def upgrade() -> None:
    if "imagen" not in _columnas("links"):
        with op.batch_alter_table("links") as batch:
            batch.add_column(sa.Column("imagen", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    if "imagen" in _columnas("links"):
        with op.batch_alter_table("links") as batch:
            batch.drop_column("imagen")
