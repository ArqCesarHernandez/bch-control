"""Multiobra, reservas de requisición y cotizaciones consolidadas.

Revision ID: f4b8c2d9e671
Revises: e3a7b9c1d245
Create Date: 2026-07-24

La tabla ``user_projects`` ya era muchos-a-muchos en Fase 5. Esta revisión
conserva esa relación, materializa el acceso global de los compradores y añade
únicamente los datos que no podían representarse en el esquema anterior.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f4b8c2d9e671"
down_revision = "e3a7b9c1d245"
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


def _backfill_delivery_permissions() -> None:
    """Inserta el módulo nuevo sin tocar filas personalizadas existentes."""

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO permisos
                (usuario_id, modulo, puede_ver, puede_crear, puede_editar,
                 puede_eliminar, puede_aprobar, puede_emitir, puede_cancelar,
                 puede_pagar, puede_conciliar)
            SELECT
                usuario.id,
                'direcciones_entrega',
                CASE
                    WHEN usuario.rol IN ('admin', 'comprador') THEN 1
                    ELSE 0
                END,
                CASE WHEN usuario.rol = 'admin' THEN 1 ELSE 0 END,
                CASE
                    WHEN usuario.rol IN ('admin', 'comprador') THEN 1
                    ELSE 0
                END,
                CASE WHEN usuario.rol = 'admin' THEN 1 ELSE 0 END,
                CASE WHEN usuario.rol = 'admin' THEN 1 ELSE 0 END,
                CASE WHEN usuario.rol = 'admin' THEN 1 ELSE 0 END,
                CASE WHEN usuario.rol = 'admin' THEN 1 ELSE 0 END,
                CASE WHEN usuario.rol = 'admin' THEN 1 ELSE 0 END,
                CASE WHEN usuario.rol = 'admin' THEN 1 ELSE 0 END
            FROM usuarios AS usuario
            WHERE NOT EXISTS (
                SELECT 1
                FROM permisos AS permiso
                WHERE permiso.usuario_id = usuario.id
                  AND permiso.modulo = 'direcciones_entrega'
            )
            """
        )
    )


def _assign_all_projects_to_buyers() -> None:
    """Mantiene la tabla de alcance coherente con el acceso global del rol."""

    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO user_projects (user_id, project_id)
            SELECT usuario.id, obra.id
            FROM usuarios AS usuario
            CROSS JOIN centros_costo AS obra
            WHERE usuario.rol = 'comprador'
              AND obra.tipo = 'obra'
              AND NOT EXISTS (
                  SELECT 1
                  FROM user_projects AS asignacion
                  WHERE asignacion.user_id = usuario.id
                    AND asignacion.project_id = obra.id
              )
            """
        )
    )


def _backfill_quotation_traceability() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO quotation_requisitions
                (quotation_id, requisition_id)
            SELECT quotation.id, quotation.requisition_id
            FROM quotations AS quotation
            WHERE NOT EXISTS (
                SELECT 1
                FROM quotation_requisitions AS relation
                WHERE relation.quotation_id = quotation.id
                  AND relation.requisition_id = quotation.requisition_id
            )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE quotation_lines
            SET supply_item_id = (
                SELECT explosion.supply_item_id
                FROM purchase_requisition_lines AS requisition_line
                JOIN budget_explosion_items AS explosion
                  ON explosion.id = requisition_line.explosion_item_id
                WHERE requisition_line.id =
                      quotation_lines.requisition_line_id
            )
            WHERE supply_item_id IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO quotation_line_sources
                (quotation_line_id, requisition_line_id, cantidad)
            SELECT line.id, line.requisition_line_id, line.cantidad
            FROM quotation_lines AS line
            WHERE NOT EXISTS (
                SELECT 1
                FROM quotation_line_sources AS source
                WHERE source.quotation_line_id = line.id
                  AND source.requisition_line_id =
                      line.requisition_line_id
            )
            """
        )
    )


def _backfill_draft_reservations() -> None:
    """Reserva borradores y conceptos especiales todavía pendientes."""

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE budget_explosion_items
            SET cantidad_reservada_borrador = COALESCE(
                (
                    SELECT SUM(line.cantidad_solicitada)
                    FROM purchase_requisition_lines AS line
                    JOIN purchase_requisitions AS requisition
                      ON requisition.id = line.requisition_id
                    WHERE line.explosion_item_id =
                          budget_explosion_items.id
                      AND line.estado_linea = 'PENDIENTE'
                      AND requisition.estado IN (
                          'BORRADOR',
                          'PENDIENTE_AUTORIZACION',
                          'PARCIAL'
                      )
                ),
                0
            )
            """
        )
    )


def upgrade() -> None:
    _set_sqlite_foreign_keys(False)

    with op.batch_alter_table("centros_costo", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "direccion_entrega",
                sa.String(length=500),
                nullable=True,
            )
        )

    with op.batch_alter_table(
        "budget_explosion_items", schema=None
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "cantidad_reservada_borrador",
                sa.Numeric(precision=16, scale=4),
                server_default="0",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_explosion_draft_reserved_quantity",
            "cantidad_reservada_borrador >= 0",
        )

    with op.batch_alter_table("quotations", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_quotation_requisition_supplier",
            type_="unique",
        )

    with op.batch_alter_table("quotation_lines", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("supply_item_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_quotation_lines_supply_item_id",
            "supply_items",
            ["supply_item_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "ix_quotation_lines_supply_item_id",
        "quotation_lines",
        ["supply_item_id"],
        unique=False,
    )

    op.create_table(
        "quotation_requisitions",
        sa.Column("quotation_id", sa.Integer(), nullable=False),
        sa.Column("requisition_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["quotation_id"],
            ["quotations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            ["purchase_requisitions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("quotation_id", "requisition_id"),
    )

    op.create_table(
        "quotation_line_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quotation_line_id", sa.Integer(), nullable=False),
        sa.Column("requisition_line_id", sa.Integer(), nullable=False),
        sa.Column(
            "cantidad",
            sa.Numeric(precision=16, scale=4),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cantidad > 0",
            name="ck_quotation_line_source_quantity",
        ),
        sa.ForeignKeyConstraint(
            ["quotation_line_id"],
            ["quotation_lines.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requisition_line_id"],
            ["purchase_requisition_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "quotation_line_id",
            "requisition_line_id",
            name="uq_quotation_line_source",
        ),
    )
    op.create_index(
        "ix_quotation_line_sources_quotation_line_id",
        "quotation_line_sources",
        ["quotation_line_id"],
        unique=False,
    )
    op.create_index(
        "ix_quotation_line_sources_requisition_line_id",
        "quotation_line_sources",
        ["requisition_line_id"],
        unique=False,
    )

    with op.batch_alter_table("purchase_orders", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "direccion_entrega",
                sa.String(length=500),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "direccion_entrega_confirmada_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "direccion_entrega_confirmada_por_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_purchase_orders_direccion_confirmada_por_id",
            "usuarios",
            ["direccion_entrega_confirmada_por_id"],
            ["id"],
            ondelete="SET NULL",
        )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE purchase_orders
            SET direccion_entrega = (
                SELECT obra.direccion_entrega
                FROM centros_costo AS obra
                WHERE obra.id = purchase_orders.project_id
            )
            WHERE direccion_entrega IS NULL
            """
        )
    )
    _backfill_quotation_traceability()
    _backfill_draft_reservations()
    _backfill_delivery_permissions()
    _assign_all_projects_to_buyers()
    _set_sqlite_foreign_keys(True)


def _assert_downgrade_safe() -> None:
    bind = op.get_bind()
    checks = (
        (
            """
            SELECT COUNT(*)
            FROM (
                SELECT quotation_id
                FROM quotation_requisitions
                GROUP BY quotation_id
                HAVING COUNT(*) > 1
            ) AS consolidated
            """,
            "Existen cotizaciones consolidadas que la revisión anterior no "
            "puede representar.",
        ),
        (
            """
            SELECT COUNT(*)
            FROM quotation_requisitions AS relation
            JOIN quotations AS quotation
              ON quotation.id = relation.quotation_id
            WHERE relation.requisition_id <> quotation.requisition_id
            """,
            "Existen vínculos de cotización hacia requisiciones adicionales.",
        ),
        (
            """
            SELECT COUNT(*)
            FROM (
                SELECT quotation_line_id
                FROM quotation_line_sources
                GROUP BY quotation_line_id
                HAVING COUNT(*) > 1
            ) AS grouped_lines
            """,
            "Existen materiales consolidados con más de una requisición fuente.",
        ),
        (
            """
            SELECT COUNT(*)
            FROM (
                SELECT requisition_id, supplier_id
                FROM quotations
                GROUP BY requisition_id, supplier_id
                HAVING COUNT(*) > 1
            ) AS duplicates
            """,
            "Existen varias cotizaciones del mismo proveedor para una "
            "requisición.",
        ),
        (
            """
            SELECT COUNT(*)
            FROM centros_costo
            WHERE direccion_entrega IS NOT NULL
              AND TRIM(direccion_entrega) <> ''
            """,
            "Existen direcciones de entrega que la revisión anterior no "
            "puede conservar.",
        ),
        (
            """
            SELECT COUNT(*)
            FROM purchase_orders
            WHERE direccion_entrega_confirmada_at IS NOT NULL
               OR direccion_entrega_confirmada_por_id IS NOT NULL
            """,
            "Existen confirmaciones de dirección de entrega que la revisión "
            "anterior no puede conservar.",
        ),
    )
    for sql, message in checks:
        if int(bind.execute(sa.text(sql)).scalar() or 0):
            raise RuntimeError(message)


def downgrade() -> None:
    _assert_downgrade_safe()
    _set_sqlite_foreign_keys(False)

    op.execute(
        sa.text(
            """
            DELETE FROM permisos
            WHERE modulo = 'direcciones_entrega'
            """
        )
    )

    with op.batch_alter_table("purchase_orders", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_purchase_orders_direccion_confirmada_por_id",
            type_="foreignkey",
        )
        batch_op.drop_column("direccion_entrega_confirmada_por_id")
        batch_op.drop_column("direccion_entrega_confirmada_at")
        batch_op.drop_column("direccion_entrega")

    op.drop_index(
        "ix_quotation_line_sources_requisition_line_id",
        table_name="quotation_line_sources",
    )
    op.drop_index(
        "ix_quotation_line_sources_quotation_line_id",
        table_name="quotation_line_sources",
    )
    op.drop_table("quotation_line_sources")
    op.drop_table("quotation_requisitions")

    op.drop_index(
        "ix_quotation_lines_supply_item_id",
        table_name="quotation_lines",
    )
    with op.batch_alter_table("quotation_lines", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_quotation_lines_supply_item_id",
            type_="foreignkey",
        )
        batch_op.drop_column("supply_item_id")

    with op.batch_alter_table("quotations", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_quotation_requisition_supplier",
            ["requisition_id", "supplier_id"],
        )

    with op.batch_alter_table(
        "budget_explosion_items", schema=None
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_explosion_draft_reserved_quantity",
            type_="check",
        )
        batch_op.drop_column("cantidad_reservada_borrador")

    with op.batch_alter_table("centros_costo", schema=None) as batch_op:
        batch_op.drop_column("direccion_entrega")

    _set_sqlite_foreign_keys(True)
