"""Añade bio y token_version a users, e icono a tags

Revision ID: 0002_columnas_perfil
Revises: 0001_esquema_inicial
Create Date: 2026-11-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_columnas_perfil"
down_revision: Union[str, None] = "0001_esquema_inicial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columnas(tabla: str) -> set[str]:
    return {columna["name"] for columna in sa.inspect(op.get_bind()).get_columns(tabla)}


def upgrade() -> None:
    columnas_users = _columnas("users")
    if "bio" not in columnas_users or "token_version" not in columnas_users:
        # batch_alter_table hace la migración compatible con SQLite.
        with op.batch_alter_table("users") as batch:
            if "bio" not in columnas_users:
                batch.add_column(sa.Column("bio", sa.Text(), nullable=True))
            if "token_version" not in columnas_users:
                batch.add_column(
                    sa.Column("token_version", sa.Integer(), nullable=False, server_default="1")
                )

    if "icono" not in _columnas("tags"):
        with op.batch_alter_table("tags") as batch:
            batch.add_column(sa.Column("icono", sa.String(length=16), nullable=True))


def downgrade() -> None:
    columnas_users = _columnas("users")
    with op.batch_alter_table("users") as batch:
        if "token_version" in columnas_users:
            batch.drop_column("token_version")
        if "bio" in columnas_users:
            batch.drop_column("bio")

    if "icono" in _columnas("tags"):
        with op.batch_alter_table("tags") as batch:
            batch.drop_column("icono")
