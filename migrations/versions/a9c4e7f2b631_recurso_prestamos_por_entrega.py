"""Recurso de préstamos por entrega y obra histórica.

Revision ID: a9c4e7f2b631
Revises: f4b8c2d9e671
Create Date: 2026-07-24

``metodo_entrega`` y ``company_id`` ya existían. Esta revisión agrega
únicamente la fotografía de obra necesaria para que un préstamo no cambie de
centro de costo cuando el trabajador sea reasignado.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a9c4e7f2b631"
down_revision = "f4b8c2d9e671"
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
    with op.batch_alter_table("loans", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("project_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_loans_project_id",
            "centros_costo",
            ["project_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_loans_project_id",
            ["project_id"],
            unique=False,
        )

    op.execute(
        sa.text(
            """
            UPDATE loans
            SET project_id = (
                SELECT employees.project_id
                FROM employees
                WHERE employees.id = loans.employee_id
            )
            WHERE project_id IS NULL
            """
        )
    )
    _set_sqlite_foreign_keys(True)


def _assert_downgrade_safe() -> None:
    """Evita perder la obra histórica después de una reasignación."""

    changed = op.get_bind().execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM loans
            JOIN employees ON employees.id = loans.employee_id
            WHERE loans.project_id IS NOT NULL
              AND (
                    employees.project_id IS NULL
                    OR employees.project_id <> loans.project_id
                  )
            """
        )
    ).scalar()
    if int(changed or 0):
        raise RuntimeError(
            "Existen préstamos cuya obra histórica ya difiere de la obra "
            "actual del trabajador; la revisión anterior no puede "
            "representarlos sin pérdida de trazabilidad."
        )


def downgrade() -> None:
    _assert_downgrade_safe()
    _set_sqlite_foreign_keys(False)
    with op.batch_alter_table("loans", schema=None) as batch_op:
        batch_op.drop_index("ix_loans_project_id")
        batch_op.drop_constraint(
            "fk_loans_project_id",
            type_="foreignkey",
        )
        batch_op.drop_column("project_id")
    _set_sqlite_foreign_keys(True)

