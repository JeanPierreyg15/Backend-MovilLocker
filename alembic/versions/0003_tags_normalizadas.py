"""Añade tags.nombre_normalizado y resuelve etiquetas duplicadas

Revision ID: 0003_tags_normalizadas
Revises: 0002_columnas_perfil
Create Date: 2026-11-11
"""

from typing import Sequence, Union
import unicodedata

from alembic import op
import sqlalchemy as sa

revision: str = "0003_tags_normalizadas"
down_revision: Union[str, None] = "0002_columnas_perfil"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOMBRE_CONSTRAINT = "uq_tags_usuario_nombre_normalizado"


def _columnas(tabla: str) -> set[str]:
    return {columna["name"] for columna in sa.inspect(op.get_bind()).get_columns(tabla)}


def _constraints(tabla: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(tabla)
        if constraint["name"]
    }


def _normalizar(nombre: str) -> str:
    return unicodedata.normalize("NFKC", (nombre or "").strip()).casefold()


def _resolver_duplicados() -> None:
    """Rellena la columna nueva y renombra duplicados existentes."""
    conexion = op.get_bind()
    filas = conexion.execute(
        sa.text("SELECT id, user_id, nombre FROM tags ORDER BY id")
    ).fetchall()

    usados: dict[tuple[int, str], int] = {}
    for tag_id, user_id, nombre in filas:
        base = _normalizar(nombre) or "etiqueta"
        candidato = base
        sufijo = 2
        while (user_id, candidato) in usados:
            candidato = f"{base} ({sufijo})"
            sufijo += 1

        nombre_final = nombre
        if candidato != base:
            nombre_final = f"{(nombre or '').strip()} ({sufijo - 1})"
            # El nuevo nombre también debe ser único tal cual.
            while conexion.execute(
                sa.text(
                    "SELECT 1 FROM tags WHERE user_id = :user_id AND nombre = :nombre AND id != :id"
                ),
                {"user_id": user_id, "nombre": nombre_final, "id": tag_id},
            ).first():
                sufijo += 1
                nombre_final = f"{(nombre or '').strip()} ({sufijo - 1})"
            candidato = _normalizar(nombre_final)

        usados[(user_id, candidato)] = tag_id
        conexion.execute(
            sa.text(
                "UPDATE tags SET nombre = :nombre, nombre_normalizado = :normalizado WHERE id = :id"
            ),
            {"nombre": nombre_final, "normalizado": candidato, "id": tag_id},
        )


def upgrade() -> None:
    if "nombre_normalizado" not in _columnas("tags"):
        with op.batch_alter_table("tags") as batch:
            batch.add_column(sa.Column("nombre_normalizado", sa.String(), nullable=True))

    # Idempotente: también rellena filas nulas si una ejecución anterior falló.
    faltantes = op.get_bind().execute(
        sa.text("SELECT count(*) FROM tags WHERE nombre_normalizado IS NULL OR nombre_normalizado = ''")
    ).scalar()
    if faltantes:
        _resolver_duplicados()

    with op.batch_alter_table("tags") as batch:
        batch.alter_column(
            "nombre_normalizado",
            existing_type=sa.String(),
            nullable=False,
        )

    if NOMBRE_CONSTRAINT not in _constraints("tags"):
        with op.batch_alter_table("tags") as batch:
            batch.create_unique_constraint(
                NOMBRE_CONSTRAINT, ["user_id", "nombre_normalizado"]
            )


def downgrade() -> None:
    if NOMBRE_CONSTRAINT in _constraints("tags"):
        with op.batch_alter_table("tags") as batch:
            batch.drop_constraint(NOMBRE_CONSTRAINT, type_="unique")

    if "nombre_normalizado" in _columnas("tags"):
        with op.batch_alter_table("tags") as batch:
            batch.drop_column("nombre_normalizado")
