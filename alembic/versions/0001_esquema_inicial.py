"""Esquema inicial (versión previa a bio/token_version/icono)

Revision ID: 0001_esquema_inicial
Revises:
Create Date: 2026-11-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_esquema_inicial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existe_tabla(nombre: str) -> bool:
    return nombre in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # Idempotente: una base de datos creada con create_all() ya tiene las
    # tablas, así que se conserva y solo se añaden las columnas nuevas en 0002.
    if not _existe_tabla("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("nombre", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("hashed_password", sa.String(), nullable=False),
            sa.Column("avatar_color", sa.String(length=7), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_users_id", "users", ["id"], unique=False)
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if not _existe_tabla("links"):
        op.create_table(
            "links",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("url", sa.String(), nullable=False),
            sa.Column("titulo", sa.String(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_links_id", "links", ["id"], unique=False)
        op.create_index("ix_links_user_id", "links", ["user_id"], unique=False)

    if not _existe_tabla("tags"):
        op.create_table(
            "tags",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("nombre", sa.String(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", "nombre", name="uq_tags_usuario_nombre"),
        )
        op.create_index("ix_tags_id", "tags", ["id"], unique=False)
        op.create_index("ix_tags_nombre", "tags", ["nombre"], unique=False)

    if not _existe_tabla("link_tags"):
        op.create_table(
            "link_tags",
            sa.Column("link_id", sa.Integer(), nullable=False),
            sa.Column("tag_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("link_id", "tag_id"),
        )


def downgrade() -> None:
    op.drop_table("link_tags")
    op.drop_index("ix_tags_nombre", table_name="tags")
    op.drop_index("ix_tags_id", table_name="tags")
    op.drop_table("tags")
    op.drop_index("ix_links_user_id", table_name="links")
    op.drop_index("ix_links_id", table_name="links")
    op.drop_table("links")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
