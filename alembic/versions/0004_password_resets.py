"""Códigos de recuperación de contraseña

Revision ID: 0004_password_resets
Revises: 0003_urls_unicas
Create Date: 2026-11-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_password_resets"
down_revision: Union[str, None] = "0003_urls_unicas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existe_tabla(nombre: str) -> bool:
    return nombre in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # Idempotente: una base creada con create_all() ya tiene la tabla.
    if _existe_tabla("password_resets"):
        return
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("codigo_hash", sa.String(), nullable=False),
        sa.Column("expira_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("usado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_password_resets_id", "password_resets", ["id"], unique=False
    )
    op.create_index(
        "ix_password_resets_user_id", "password_resets", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_password_resets_user_id", table_name="password_resets")
    op.drop_index("ix_password_resets_id", table_name="password_resets")
    op.drop_table("password_resets")
