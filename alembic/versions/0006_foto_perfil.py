"""Añade la foto de perfil (avatar_imagen) a users

La imagen se guarda como data URL (data:image/jpeg;base64,...) ya reducida en
el cliente, de modo que no hace falta un almacenamiento de archivos aparte.

Revision ID: 0006_foto_perfil
Revises: 0005_urls_canonicas
Create Date: 2026-11-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_foto_perfil"
down_revision: Union[str, None] = "0005_urls_canonicas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columnas(tabla: str) -> set[str]:
    return {columna["name"] for columna in sa.inspect(op.get_bind()).get_columns(tabla)}


def upgrade() -> None:
    if "avatar_imagen" not in _columnas("users"):
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("avatar_imagen", sa.Text(), nullable=True))


def downgrade() -> None:
    if "avatar_imagen" in _columnas("users"):
        with op.batch_alter_table("users") as batch:
            batch.drop_column("avatar_imagen")
