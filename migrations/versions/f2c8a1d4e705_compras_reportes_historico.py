"""Completa Compras: histórico, reportes, anticipos y catálogos compartidos.

Revision ID: f2c8a1d4e705
Revises: d7f4a8c2b913
Create Date: 2026-07-21
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "f2c8a1d4e705"
down_revision = "d7f4a8c2b913"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    created_at = datetime.now(timezone.utc)

    supplier_supply_items = op.create_table(
        "supplier_supply_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("supply_item_id", sa.Integer(), nullable=False),
        sa.Column("precio_historico", sa.Numeric(16, 4), nullable=False),
        sa.Column("fecha_ultima_compra", sa.Date(), nullable=True),
        sa.Column(
            "origen",
            sa.String(length=20),
            server_default="IMPORTACION",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "precio_historico >= 0", name="ck_supplier_supply_historical_price"
        ),
        sa.CheckConstraint(
            "origen IN ('IMPORTACION','ORDEN_COMPRA')",
            name="ck_supplier_supply_source",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supply_item_id"], ["supply_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "supplier_id", "supply_item_id", name="uq_supplier_supply_item"
        ),
    )
    op.create_index(
        "ix_supplier_supply_items_supplier_id",
        "supplier_supply_items",
        ["supplier_id"],
    )
    op.create_index(
        "ix_supplier_supply_items_supply_item_id",
        "supplier_supply_items",
        ["supply_item_id"],
    )

    # Clasifica el insumo importado en una obra (o catálogo general) sin crear
    # un renglón presupuestal de cantidad ficticia.
    op.create_table(
        "supply_project_catalog",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("budget_item_id", sa.Integer(), nullable=False),
        sa.Column("supply_item_id", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["centros_costo.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["budget_item_id"], ["budget_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["supply_item_id"], ["supply_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "supply_item_id", name="uq_supply_project_catalog"
        ),
    )
    op.create_index(
        "ix_supply_project_catalog_project_id",
        "supply_project_catalog",
        ["project_id"],
    )
    op.create_index(
        "ix_supply_project_catalog_supply_item_id",
        "supply_project_catalog",
        ["supply_item_id"],
    )

    # Aprovecha las OC que ya se hayan capturado desde que se instaló d7f4...
    # y conserva el precio más reciente por proveedor e insumo.
    bind.execute(
        sa.text(
            """
            INSERT INTO supplier_supply_items
                (supplier_id, supply_item_id, precio_historico,
                 fecha_ultima_compra, origen, created_at, updated_at)
            SELECT po.supplier_id, bei.supply_item_id,
                   pol.precio_unitario_sin_iva, po.fecha_orden,
                   'ORDEN_COMPRA', :created_at, :created_at
              FROM purchase_order_lines pol
              JOIN purchase_orders po ON po.id = pol.order_id
              JOIN budget_explosion_items bei ON bei.id = pol.explosion_item_id
             WHERE po.estado NOT IN ('BORRADOR','CANCELADA')
               AND pol.id = (
                    SELECT pol2.id
                      FROM purchase_order_lines pol2
                      JOIN purchase_orders po2 ON po2.id = pol2.order_id
                      JOIN budget_explosion_items bei2
                        ON bei2.id = pol2.explosion_item_id
                     WHERE po2.supplier_id = po.supplier_id
                       AND bei2.supply_item_id = bei.supply_item_id
                       AND po2.estado NOT IN ('BORRADOR','CANCELADA')
                     ORDER BY po2.fecha_orden DESC, pol2.id DESC
                     LIMIT 1
               )
            """
        ),
        {"created_at": created_at},
    )

    op.add_column(
        "purchase_orders",
        sa.Column("payment_due_notified_on", sa.Date(), nullable=True),
    )

    if is_sqlite:
        op.execute(
            "ALTER TABLE additional_payments ADD COLUMN "
            "purchase_order_line_id INTEGER REFERENCES "
            "purchase_order_lines(id)"
        )
    else:
        op.add_column(
            "additional_payments",
            sa.Column("purchase_order_line_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_additional_payment_order_line",
            "additional_payments",
            "purchase_order_lines",
            ["purchase_order_line_id"],
            ["id"],
        )
    op.create_index(
        "ix_additional_payments_purchase_order_line_id",
        "additional_payments",
        ["purchase_order_line_id"],
    )

    # Solo se rellena cuando la coincidencia OC + insumo identifica un único
    # renglón; cualquier caso ambiguo permanece como histórico sin inventar un
    # vínculo.
    bind.execute(
        sa.text(
            """
            UPDATE additional_payments
               SET purchase_order_line_id = (
                    SELECT MIN(pol.id)
                      FROM purchase_order_lines pol
                     WHERE pol.order_id = additional_payments.purchase_order_id
                       AND pol.explosion_item_id = additional_payments.explosion_item_id
               )
             WHERE purchase_order_id IS NOT NULL
               AND explosion_item_id IS NOT NULL
               AND (
                    SELECT COUNT(*)
                      FROM purchase_order_lines pol
                     WHERE pol.order_id = additional_payments.purchase_order_id
                       AND pol.explosion_item_id = additional_payments.explosion_item_id
               ) = 1
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE additional_payments
               SET payment_method_id = (
                    SELECT pm.id FROM payment_methods pm
                     WHERE UPPER(pm.nombre) = UPPER(additional_payments.metodo_pago)
                     LIMIT 1
               )
             WHERE payment_method_id IS NULL
            """
        )
    )

    for table_name, legacy_column, fk_name, index_name in [
        (
            "loans",
            "metodo_entrega",
            "fk_loans_payment_method",
            "ix_loans_payment_method_id",
        ),
        (
            "subcontract_payments",
            "metodo_pago",
            "fk_subcontract_payments_payment_method",
            "ix_subcontract_payments_payment_method_id",
        ),
        (
            "office_expenses",
            "metodo_pago",
            "fk_office_expenses_payment_method",
            "ix_office_expenses_payment_method_id",
        ),
    ]:
        if is_sqlite:
            op.execute(
                f"ALTER TABLE {table_name} ADD COLUMN "
                "payment_method_id INTEGER REFERENCES "
                "payment_methods(id)"
            )
        else:
            op.add_column(
                table_name,
                sa.Column("payment_method_id", sa.Integer(), nullable=True),
            )
            op.create_foreign_key(
                fk_name,
                table_name,
                "payment_methods",
                ["payment_method_id"],
                ["id"],
            )
        op.create_index(index_name, table_name, ["payment_method_id"])
        bind.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                   SET payment_method_id = (
                        SELECT pm.id FROM payment_methods pm
                         WHERE UPPER(pm.nombre) = UPPER({table_name}.{legacy_column})
                         LIMIT 1
                   )
                """
            )
        )

    op.create_table(
        "supplier_advance_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_order_id", sa.Integer(), nullable=False),
        sa.Column("source_order_line_id", sa.Integer(), nullable=False),
        sa.Column("target_order_id", sa.Integer(), nullable=True),
        sa.Column("target_order_line_id", sa.Integer(), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("payment_method_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=12), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("monto", sa.Numeric(14, 2), nullable=False),
        sa.Column("referencia", sa.String(length=120), nullable=True),
        sa.Column("notas", sa.String(length=500), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tipo IN ('APLICACION','REEMBOLSO')", name="ck_supplier_advance_type"
        ),
        sa.CheckConstraint("monto > 0", name="ck_supplier_advance_amount"),
        sa.CheckConstraint(
            "(tipo = 'APLICACION' AND target_order_id IS NOT NULL "
            "AND target_order_line_id IS NOT NULL) OR "
            "(tipo = 'REEMBOLSO' AND target_order_id IS NULL "
            "AND target_order_line_id IS NULL)",
            name="ck_supplier_advance_target",
        ),
        sa.ForeignKeyConstraint(
            ["source_order_id"], ["purchase_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_order_line_id"],
            ["purchase_order_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_order_id"], ["purchase_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_order_line_id"],
            ["purchase_order_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["payment_method_id"], ["payment_methods.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_supplier_advance_movements_source_order_id",
        "supplier_advance_movements",
        ["source_order_id"],
    )
    op.create_index(
        "ix_supplier_advance_movements_supplier_id",
        "supplier_advance_movements",
        ["supplier_id"],
    )
    op.create_index(
        "ix_supplier_advance_movements_fecha",
        "supplier_advance_movements",
        ["fecha"],
    )

    op.create_table(
        "purchase_alert_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column(
            "requisiciones_vencidas",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "entregas_vencidas", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "pagos_por_vencer", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fecha"),
    )
    op.create_index(
        "ix_purchase_alert_runs_fecha",
        "purchase_alert_runs",
        ["fecha"],
        unique=True,
    )


def downgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.drop_index("ix_purchase_alert_runs_fecha", table_name="purchase_alert_runs")
    op.drop_table("purchase_alert_runs")

    op.drop_index(
        "ix_supplier_advance_movements_fecha",
        table_name="supplier_advance_movements",
    )
    op.drop_index(
        "ix_supplier_advance_movements_supplier_id",
        table_name="supplier_advance_movements",
    )
    op.drop_index(
        "ix_supplier_advance_movements_source_order_id",
        table_name="supplier_advance_movements",
    )
    op.drop_table("supplier_advance_movements")

    for table_name, fk_name, index_name in [
        (
            "office_expenses",
            "fk_office_expenses_payment_method",
            "ix_office_expenses_payment_method_id",
        ),
        (
            "subcontract_payments",
            "fk_subcontract_payments_payment_method",
            "ix_subcontract_payments_payment_method_id",
        ),
        (
            "loans",
            "fk_loans_payment_method",
            "ix_loans_payment_method_id",
        ),
    ]:
        op.drop_index(index_name, table_name=table_name)
        if not is_sqlite:
            op.drop_constraint(fk_name, table_name, type_="foreignkey")
        op.drop_column(table_name, "payment_method_id")

    op.drop_index(
        "ix_additional_payments_purchase_order_line_id",
        table_name="additional_payments",
    )
    if not is_sqlite:
        op.drop_constraint(
            "fk_additional_payment_order_line",
            "additional_payments",
            type_="foreignkey",
        )
    op.drop_column("additional_payments", "purchase_order_line_id")

    op.drop_column("purchase_orders", "payment_due_notified_on")

    op.drop_index(
        "ix_supply_project_catalog_supply_item_id",
        table_name="supply_project_catalog",
    )
    op.drop_index(
        "ix_supply_project_catalog_project_id",
        table_name="supply_project_catalog",
    )
    op.drop_table("supply_project_catalog")

    op.drop_index(
        "ix_supplier_supply_items_supply_item_id", table_name="supplier_supply_items"
    )
    op.drop_index(
        "ix_supplier_supply_items_supplier_id", table_name="supplier_supply_items"
    )
    op.drop_table("supplier_supply_items")
