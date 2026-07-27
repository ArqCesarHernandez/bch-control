"""Fase 4: Compras y explosión de insumos.

Revision ID: c4a2d7e9f601
Revises: 8b6d4f2a1c90
Create Date: 2026-07-21

Los pagos históricos permanecen intactos. Sus nuevas referencias de Compras
quedan nulas hasta que un movimiento nuevo se capture desde el módulo.
"""

from alembic import op
import sqlalchemy as sa


revision = "c4a2d7e9f601"
down_revision = "8b6d4f2a1c90"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column("rfc", sa.String(length=13), nullable=True),
        sa.Column("contacto", sa.String(length=150), nullable=True),
        sa.Column("telefono", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=180), nullable=True),
        sa.Column("moneda", sa.String(length=3), server_default="MXN", nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("moneda = 'MXN'", name="ck_supplier_currency_mxn"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo"),
        sa.UniqueConstraint("nombre"),
    )
    op.create_index("ix_suppliers_codigo", "suppliers", ["codigo"], unique=True)
    op.create_index("ix_suppliers_nombre", "suppliers", ["nombre"], unique=True)
    op.create_index("ix_suppliers_rfc", "suppliers", ["rfc"], unique=False)

    op.create_table(
        "supply_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clave", sa.String(length=40), nullable=False),
        sa.Column("descripcion", sa.String(length=70), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("unidad", sa.String(length=3), nullable=False),
        sa.Column("clave_sat", sa.String(length=20), server_default="00000000", nullable=False),
        sa.Column("moneda", sa.String(length=3), server_default="MXN", nullable=False),
        sa.Column("precio_variable", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tipo IN ('MATERIAL','EQUIPO','MANO_OBRA','SUBCONTRATO','INDIRECTO')",
            name="ck_supply_item_type",
        ),
        sa.CheckConstraint("length(unidad) <= 3", name="ck_supply_item_unit_length"),
        sa.CheckConstraint("moneda = 'MXN'", name="ck_supply_item_currency_mxn"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clave"),
    )
    op.create_index("ix_supply_items_clave", "supply_items", ["clave"], unique=True)
    op.create_index("ix_supply_items_descripcion", "supply_items", ["descripcion"], unique=False)

    op.create_table(
        "budget_explosion_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("budget_item_id", sa.Integer(), nullable=False),
        sa.Column("supply_item_id", sa.Integer(), nullable=False),
        sa.Column("cantidad_presupuestada", sa.Numeric(precision=16, scale=4), nullable=False),
        sa.Column("precio_unitario_sin_iva", sa.Numeric(precision=16, scale=4), nullable=False),
        sa.Column("importe_presupuestado", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cantidad_presupuestada > 0", name="ck_explosion_budget_quantity"),
        sa.CheckConstraint("precio_unitario_sin_iva >= 0", name="ck_explosion_unit_price"),
        sa.CheckConstraint("importe_presupuestado >= 0", name="ck_explosion_budget_amount"),
        sa.ForeignKeyConstraint(["budget_item_id"], ["budget_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["centros_costo.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supply_item_id"], ["supply_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "budget_item_id", "supply_item_id",
            name="uq_explosion_project_budget_supply",
        ),
    )
    op.create_index("ix_budget_explosion_items_project_id", "budget_explosion_items", ["project_id"], unique=False)
    op.create_index("ix_budget_explosion_items_budget_item_id", "budget_explosion_items", ["budget_item_id"], unique=False)
    op.create_index("ix_budget_explosion_items_supply_item_id", "budget_explosion_items", ["supply_item_id"], unique=False)

    op.create_table(
        "purchase_requisitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("folio", sa.String(length=30), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("fecha_solicitud", sa.Date(), nullable=False),
        sa.Column("fecha_requerida", sa.Date(), nullable=False),
        sa.Column("estado", sa.String(length=15), server_default="BORRADOR", nullable=False),
        sa.Column("motivo", sa.String(length=240), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("requested_by_id", sa.Integer(), nullable=False),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "estado IN ('BORRADOR','SOLICITADA','APROBADA','RECHAZADA','PARCIAL','ATENDIDA','CANCELADA')",
            name="ck_purchase_requisition_status",
        ),
        sa.CheckConstraint("fecha_requerida >= fecha_solicitud", name="ck_purchase_requisition_dates"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["centros_costo.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("folio"),
    )
    op.create_index("ix_purchase_requisitions_folio", "purchase_requisitions", ["folio"], unique=True)
    op.create_index("ix_purchase_requisitions_project_id", "purchase_requisitions", ["project_id"], unique=False)

    op.create_table(
        "purchase_requisition_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("requisition_id", sa.Integer(), nullable=False),
        sa.Column("explosion_item_id", sa.Integer(), nullable=False),
        sa.Column("cantidad_solicitada", sa.Numeric(precision=16, scale=4), nullable=False),
        sa.Column("notas", sa.String(length=240), nullable=True),
        sa.CheckConstraint("cantidad_solicitada > 0", name="ck_requisition_line_quantity"),
        sa.ForeignKeyConstraint(["explosion_item_id"], ["budget_explosion_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requisition_id"], ["purchase_requisitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("requisition_id", "explosion_item_id", name="uq_requisition_explosion_item"),
    )

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("folio", sa.String(length=30), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("requisition_id", sa.Integer(), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("fecha_orden", sa.Date(), nullable=False),
        sa.Column("fecha_entrega_estimada", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(length=15), server_default="BORRADOR", nullable=False),
        sa.Column("moneda", sa.String(length=3), server_default="MXN", nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("issued_by_id", sa.Integer(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "estado IN ('BORRADOR','EMITIDA','PARCIAL','RECIBIDA','CANCELADA')",
            name="ck_purchase_order_status",
        ),
        sa.CheckConstraint("moneda = 'MXN'", name="ck_purchase_order_currency_mxn"),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["issued_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["centros_costo.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requisition_id"], ["purchase_requisitions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("folio"),
    )
    op.create_index("ix_purchase_orders_folio", "purchase_orders", ["folio"], unique=True)
    op.create_index("ix_purchase_orders_project_id", "purchase_orders", ["project_id"], unique=False)

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("requisition_line_id", sa.Integer(), nullable=True),
        sa.Column("explosion_item_id", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Numeric(precision=16, scale=4), nullable=False),
        sa.Column("precio_unitario_sin_iva", sa.Numeric(precision=16, scale=4), nullable=False),
        sa.Column("importe_sin_iva", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("notas", sa.String(length=240), nullable=True),
        sa.CheckConstraint("cantidad > 0", name="ck_purchase_order_line_quantity"),
        sa.CheckConstraint("precio_unitario_sin_iva >= 0", name="ck_purchase_order_line_price"),
        sa.CheckConstraint("importe_sin_iva >= 0", name="ck_purchase_order_line_amount"),
        sa.ForeignKeyConstraint(["explosion_item_id"], ["budget_explosion_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["purchase_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requisition_line_id"], ["purchase_requisition_lines.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "explosion_item_id", name="uq_order_explosion_item"),
    )

    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("folio", sa.String(length=30), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("documento_proveedor", sa.String(length=80), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("received_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["purchase_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["received_by_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("folio"),
    )
    op.create_index("ix_goods_receipts_folio", "goods_receipts", ["folio"], unique=True)

    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("order_line_id", sa.Integer(), nullable=False),
        sa.Column("cantidad_recibida", sa.Numeric(precision=16, scale=4), nullable=False),
        sa.Column("notas", sa.String(length=240), nullable=True),
        sa.CheckConstraint("cantidad_recibida > 0", name="ck_goods_receipt_line_quantity"),
        sa.ForeignKeyConstraint(["order_line_id"], ["purchase_order_lines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["receipt_id"], ["goods_receipts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_id", "order_line_id", name="uq_receipt_order_line"),
    )

    with op.batch_alter_table("additional_payments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("explosion_item_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("supplier_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("purchase_order_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_additional_payment_explosion", "budget_explosion_items",
            ["explosion_item_id"], ["id"], ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_additional_payment_supplier", "suppliers",
            ["supplier_id"], ["id"], ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_additional_payment_purchase_order", "purchase_orders",
            ["purchase_order_id"], ["id"], ondelete="SET NULL",
        )
        batch_op.create_index("ix_additional_payments_explosion_item_id", ["explosion_item_id"])
        batch_op.create_index("ix_additional_payments_supplier_id", ["supplier_id"])
        batch_op.create_index("ix_additional_payments_purchase_order_id", ["purchase_order_id"])


def downgrade():
    with op.batch_alter_table("additional_payments", schema=None) as batch_op:
        batch_op.drop_index("ix_additional_payments_purchase_order_id")
        batch_op.drop_index("ix_additional_payments_supplier_id")
        batch_op.drop_index("ix_additional_payments_explosion_item_id")
        batch_op.drop_constraint("fk_additional_payment_purchase_order", type_="foreignkey")
        batch_op.drop_constraint("fk_additional_payment_supplier", type_="foreignkey")
        batch_op.drop_constraint("fk_additional_payment_explosion", type_="foreignkey")
        batch_op.drop_column("purchase_order_id")
        batch_op.drop_column("supplier_id")
        batch_op.drop_column("explosion_item_id")

    op.drop_table("goods_receipt_lines")
    op.drop_index("ix_goods_receipts_folio", table_name="goods_receipts")
    op.drop_table("goods_receipts")
    op.drop_table("purchase_order_lines")
    op.drop_index("ix_purchase_orders_project_id", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_folio", table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_table("purchase_requisition_lines")
    op.drop_index("ix_purchase_requisitions_project_id", table_name="purchase_requisitions")
    op.drop_index("ix_purchase_requisitions_folio", table_name="purchase_requisitions")
    op.drop_table("purchase_requisitions")
    op.drop_index("ix_budget_explosion_items_supply_item_id", table_name="budget_explosion_items")
    op.drop_index("ix_budget_explosion_items_budget_item_id", table_name="budget_explosion_items")
    op.drop_index("ix_budget_explosion_items_project_id", table_name="budget_explosion_items")
    op.drop_table("budget_explosion_items")
    op.drop_index("ix_supply_items_descripcion", table_name="supply_items")
    op.drop_index("ix_supply_items_clave", table_name="supply_items")
    op.drop_table("supply_items")
    op.drop_index("ix_suppliers_rfc", table_name="suppliers")
    op.drop_index("ix_suppliers_nombre", table_name="suppliers")
    op.drop_index("ix_suppliers_codigo", table_name="suppliers")
    op.drop_table("suppliers")
