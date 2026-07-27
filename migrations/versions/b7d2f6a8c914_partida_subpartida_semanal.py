"""Partida y subpartida por línea de nómina.

Revision ID: b7d2f6a8c914
Revises: a9c4e7f2b631
Create Date: 2026-07-24

La columna histórica ``budget_item_id`` se conserva como ítem efectivo para
compatibilidad. Las nuevas columnas separan la partida raíz de la subpartida y
permiten que un borrador recién creado quede pendiente de asignación hasta su
primer guardado explícito.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b7d2f6a8c914"
down_revision = "a9c4e7f2b631"
branch_labels = None
depends_on = None


def _set_sqlite_foreign_keys(enabled: bool) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    with op.get_context().autocommit_block():
        bind.exec_driver_sql(
            f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}"
        )


def upgrade() -> None:
    _set_sqlite_foreign_keys(False)
    with op.batch_alter_table("payroll_lines", schema=None) as batch_op:
        batch_op.alter_column(
            "budget_item_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column("partida_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("subpartida_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_payroll_lines_partida_id",
            "budget_items",
            ["partida_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_payroll_lines_subpartida_id",
            "budget_items",
            ["subpartida_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_payroll_lines_partida_id",
            ["partida_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_payroll_lines_subpartida_id",
            ["subpartida_id"],
            unique=False,
        )

    # Se preserva exactamente el ítem efectivo histórico. Si era una
    # subpartida, su padre queda como partida; si era raíz, no se inventa hijo.
    op.execute(
        sa.text(
            """
            UPDATE payroll_lines
            SET partida_id = (
                    SELECT CASE
                               WHEN budget_items.parent_id IS NULL
                                   THEN budget_items.id
                               ELSE budget_items.parent_id
                           END
                    FROM budget_items
                    WHERE budget_items.id = payroll_lines.budget_item_id
                ),
                subpartida_id = (
                    SELECT CASE
                               WHEN budget_items.parent_id IS NULL
                                   THEN NULL
                               ELSE budget_items.id
                           END
                    FROM budget_items
                    WHERE budget_items.id = payroll_lines.budget_item_id
                )
            WHERE budget_item_id IS NOT NULL
            """
        )
    )

    # El formulario ya restringía préstamos nuevos. La normalización cubre
    # registros históricos antes de fijar también la regla en base de datos.
    op.execute(
        sa.text(
            """
            UPDATE loans
            SET metodo_entrega = CASE
                WHEN UPPER(TRIM(COALESCE(metodo_entrega, ''))) = 'EFECTIVO'
                    THEN 'EFECTIVO'
                WHEN TRIM(COALESCE(metodo_entrega, '')) = ''
                    THEN 'EFECTIVO'
                ELSE 'TRANSFERENCIA'
            END
            """
        )
    )
    with op.batch_alter_table("loans", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_loan_delivery_method",
            "metodo_entrega IN ('EFECTIVO','TRANSFERENCIA')",
        )
    _set_sqlite_foreign_keys(True)


def _restore_effective_budget_item() -> None:
    op.execute(
        sa.text(
            """
            UPDATE payroll_lines
            SET budget_item_id = COALESCE(
                subpartida_id,
                partida_id,
                budget_item_id
            )
            """
        )
    )


def _assert_downgrade_safe() -> None:
    missing = op.get_bind().execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM payroll_lines
            WHERE budget_item_id IS NULL
            """
        )
    ).scalar()
    if int(missing or 0):
        raise RuntimeError(
            "Existen borradores con trabajadores sin partida. Asigna una "
            "partida o elimina esas líneas antes de regresar a la revisión "
            "anterior."
        )


def downgrade() -> None:
    _restore_effective_budget_item()
    _assert_downgrade_safe()
    _set_sqlite_foreign_keys(False)
    with op.batch_alter_table("loans", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_loan_delivery_method",
            type_="check",
        )
    with op.batch_alter_table("payroll_lines", schema=None) as batch_op:
        batch_op.drop_index("ix_payroll_lines_subpartida_id")
        batch_op.drop_index("ix_payroll_lines_partida_id")
        batch_op.drop_constraint(
            "fk_payroll_lines_subpartida_id",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_payroll_lines_partida_id",
            type_="foreignkey",
        )
        batch_op.drop_column("subpartida_id")
        batch_op.drop_column("partida_id")
        batch_op.alter_column(
            "budget_item_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
    _set_sqlite_foreign_keys(True)
