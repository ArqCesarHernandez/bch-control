"""Compras Fase 4 final: autorizaciones, cotizaciones, crédito y SMNC.

Revision ID: d7f4a8c2b913
Revises: c4a2d7e9f601
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


revision = "d7f4a8c2b913"
down_revision = "c4a2d7e9f601"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    created_at = datetime.now(timezone.utc)

    # La integración de Nóminas ya rellenó estos dos campos. En SQLite habían
    # quedado anulables por una limitación de la migración original.
    with op.batch_alter_table("centros_costo", schema=None) as batch_op:
        batch_op.alter_column(
            "codigo", existing_type=sa.String(length=40), nullable=False
        )
        batch_op.alter_column(
            "created_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )

    # Roles nuevos.
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_constraint("ck_usuarios_rol", type_="check")
        batch_op.create_check_constraint(
            "ck_usuarios_rol",
            "rol IN ('admin','capturista','comprador','costos')",
        )

    # Catálogo compartido de métodos de pago.
    payment_methods = op.create_table(
        "payment_methods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=80), nullable=False),
        sa.Column("descripcion", sa.String(length=240), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )
    op.bulk_insert(
        payment_methods,
        [
            {"nombre": "TRANSFERENCIA", "descripcion": "Transferencia bancaria", "activo": True, "created_at": created_at},
            {"nombre": "CHEQUE", "descripcion": "Cheque", "activo": True, "created_at": created_at},
            {"nombre": "EFECTIVO", "descripcion": "Efectivo", "activo": True, "created_at": created_at},
            {"nombre": "TARJETA DE CRÉDITO", "descripcion": "Tarjeta de crédito", "activo": True, "created_at": created_at},
            {"nombre": "TARJETA DE DÉBITO", "descripcion": "Tarjeta de débito", "activo": True, "created_at": created_at},
            {"nombre": "CONTADO", "descripcion": "Pago de contado", "activo": True, "created_at": created_at},
            {"nombre": "CRÉDITO 30 DÍAS", "descripcion": "Crédito a 30 días", "activo": True, "created_at": created_at},
            {"nombre": "CRÉDITO 60 DÍAS", "descripcion": "Crédito a 60 días", "activo": True, "created_at": created_at},
            {"nombre": "CRÉDITO 90 DÍAS", "descripcion": "Crédito a 90 días", "activo": True, "created_at": created_at},
        ],
    )

    with op.batch_alter_table("suppliers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("company_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("tiene_credito", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(
            sa.Column("limite_credito", sa.Numeric(14, 2), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("dias_credito", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.create_foreign_key(
            "fk_suppliers_company", "companies", ["company_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_check_constraint(
            "ck_supplier_credit_limit", "limite_credito >= 0"
        )
        batch_op.create_check_constraint(
            "ck_supplier_credit_days", "dias_credito >= 0"
        )
        batch_op.create_check_constraint(
            "ck_supplier_credit_configuration",
            "tiene_credito = 0 OR (limite_credito > 0 AND dias_credito > 0)",
        )

    with op.batch_alter_table("supply_items", schema=None) as batch_op:
        batch_op.drop_constraint("ck_supply_item_unit_length", type_="check")
        batch_op.alter_column(
            "descripcion",
            existing_type=sa.String(length=70),
            type_=sa.String(length=180),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "unidad",
            existing_type=sa.String(length=3),
            type_=sa.String(length=20),
            existing_nullable=False,
        )

    with op.batch_alter_table("budget_explosion_items", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("origen", sa.String(length=20), server_default="EXPLOSION", nullable=False)
        )
        batch_op.create_check_constraint(
            "ck_explosion_source", "origen IN ('EXPLOSION','SMNC')"
        )

    with op.batch_alter_table("purchase_requisitions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_purchase_requisition_status", type_="check")
        batch_op.alter_column(
            "estado",
            existing_type=sa.String(length=15),
            type_=sa.String(length=22),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("fecha_limite_oc", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("expiry_notified_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint(
            "ck_purchase_requisition_status",
            "estado IN ('BORRADOR','PENDIENTE_AUTORIZACION','APROBADA','RECHAZADA','PARCIAL','CERRADA','VENCIDA','CANCELADA')",
        )

    bind.execute(
        sa.text(
            "UPDATE purchase_requisitions SET estado='PENDIENTE_AUTORIZACION' WHERE estado='SOLICITADA'"
        )
    )
    bind.execute(
        sa.text("UPDATE purchase_requisitions SET estado='CERRADA' WHERE estado='ATENDIDA'")
    )

    with op.batch_alter_table("purchase_requisition_lines", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("cantidad_aprobada", sa.Numeric(16, 4), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("estado_linea", sa.String(length=24), server_default="PENDIENTE", nullable=False)
        )
        batch_op.add_column(sa.Column("motivo_rechazo_compras", sa.String(length=300), nullable=True))
        batch_op.create_check_constraint(
            "ck_requisition_line_approved_quantity",
            "cantidad_aprobada >= 0 AND cantidad_aprobada <= cantidad_solicitada",
        )
        batch_op.create_check_constraint(
            "ck_requisition_line_status",
            "estado_linea IN ('PENDIENTE','APROBADA','RECHAZADA','RECHAZADA_COMPRAS')",
        )

    bind.execute(
        sa.text(
            "UPDATE purchase_requisition_lines SET cantidad_aprobada=cantidad_solicitada, estado_linea='APROBADA' "
            "WHERE requisition_id IN (SELECT id FROM purchase_requisitions WHERE estado IN ('APROBADA','PARCIAL','CERRADA'))"
        )
    )

    op.create_table(
        "quotations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("folio", sa.String(length=30), nullable=False),
        sa.Column("requisition_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("fecha_solicitud", sa.Date(), nullable=False),
        sa.Column("fecha_respuesta", sa.Date(), nullable=True),
        sa.Column("fecha_entrega_ofertada", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(length=15), server_default="SOLICITADA", nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "estado IN ('SOLICITADA','RESPONDIDA','SELECCIONADA','DESCARTADA','CANCELADA')",
            name="ck_quotation_status",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requisition_id"], ["purchase_requisitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("folio"),
        sa.UniqueConstraint("requisition_id", "supplier_id", name="uq_quotation_requisition_supplier"),
    )
    op.create_index("ix_quotations_folio", "quotations", ["folio"], unique=True)
    op.create_index("ix_quotations_requisition_id", "quotations", ["requisition_id"], unique=False)

    op.create_table(
        "quotation_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quotation_id", sa.Integer(), nullable=False),
        sa.Column("requisition_line_id", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Numeric(16, 4), nullable=False),
        sa.Column("precio_unitario_cotizado", sa.Numeric(16, 4), server_default="0", nullable=False),
        sa.Column("importe_cotizado", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("notas", sa.String(length=240), nullable=True),
        sa.CheckConstraint("cantidad > 0", name="ck_quotation_line_quantity"),
        sa.CheckConstraint("precio_unitario_cotizado >= 0", name="ck_quotation_line_price"),
        sa.CheckConstraint("importe_cotizado >= 0", name="ck_quotation_line_amount"),
        sa.ForeignKeyConstraint(["quotation_id"], ["quotations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requisition_line_id"], ["purchase_requisition_lines.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quotation_id", "requisition_line_id", name="uq_quotation_requisition_line"),
    )

    with op.batch_alter_table("purchase_orders", schema=None) as batch_op:
        batch_op.drop_constraint("ck_purchase_order_status", type_="check")
        batch_op.alter_column(
            "estado",
            existing_type=sa.String(length=15),
            type_=sa.String(length=30),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("quotation_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("company_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("buyer_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("payment_method_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("fecha_surtido_real", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("fecha_limite", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("modalidad_pago", sa.String(length=12), server_default="CREDITO", nullable=False))
        batch_op.add_column(sa.Column("anticipo_monto", sa.Numeric(14, 2), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("anticipo_pendiente", sa.Numeric(14, 2), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("justificacion_anticipo", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("autorizado_anticipo_por_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("fecha_autorizacion_anticipo", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("numero_factura", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("fecha_factura", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("fecha_vencimiento", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("delivery_notified_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key("fk_purchase_order_quotation", "quotations", ["quotation_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_purchase_order_company", "companies", ["company_id"], ["id"], ondelete="RESTRICT")
        batch_op.create_foreign_key("fk_purchase_order_buyer", "usuarios", ["buyer_id"], ["id"], ondelete="RESTRICT")
        batch_op.create_foreign_key("fk_purchase_order_payment_method", "payment_methods", ["payment_method_id"], ["id"], ondelete="RESTRICT")
        batch_op.create_foreign_key("fk_purchase_order_advance_authorizer", "usuarios", ["autorizado_anticipo_por_id"], ["id"], ondelete="SET NULL")
        batch_op.create_check_constraint(
            "ck_purchase_order_status",
            "estado IN ('BORRADOR','EMITIDA','PENDIENTE_ANTICIPO','ANTICIPO_AUTORIZADO','ANTICIPO_PARCIAL','ANTICIPO_PAGADO','RECEPCION_PARCIAL','RECEPCION_TOTAL','CERRADA','CANCELADA')",
        )
        batch_op.create_check_constraint("ck_purchase_order_payment_mode", "modalidad_pago IN ('CREDITO','ANTICIPO')")
        batch_op.create_check_constraint("ck_purchase_order_advance", "anticipo_monto >= 0")
        batch_op.create_check_constraint("ck_purchase_order_advance_pending", "anticipo_pendiente >= 0")
        batch_op.create_index("ix_purchase_orders_fecha_vencimiento", ["fecha_vencimiento"])

    transfer_id = bind.execute(
        sa.text("SELECT id FROM payment_methods WHERE nombre='TRANSFERENCIA'")
    ).scalar()
    company_id = bind.execute(sa.text("SELECT MIN(id) FROM companies")).scalar()
    if company_id is not None:
        bind.execute(
            sa.text(
                "UPDATE purchase_orders SET company_id=:company_id, buyer_id=created_by_id, "
                "payment_method_id=:method_id, fecha_limite=fecha_orden, "
                "fecha_entrega_estimada=COALESCE(fecha_entrega_estimada, fecha_orden)"
            ),
            {"company_id": company_id, "method_id": transfer_id},
        )

    with op.batch_alter_table("purchase_orders", schema=None) as batch_op:
        batch_op.alter_column(
            "company_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.alter_column(
            "buyer_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.alter_column(
            "payment_method_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.alter_column(
            "fecha_entrega_estimada", existing_type=sa.Date(), nullable=False
        )
        batch_op.alter_column(
            "fecha_limite", existing_type=sa.Date(), nullable=False
        )

    with op.batch_alter_table("purchase_order_lines", schema=None) as batch_op:
        batch_op.drop_constraint("uq_order_explosion_item", type_="unique")
        batch_op.create_unique_constraint(
            "uq_order_requisition_line", ["order_id", "requisition_line_id"]
        )

    with op.batch_alter_table("goods_receipts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tipo", sa.String(length=10), server_default="PARCIAL", nullable=False))
        batch_op.add_column(sa.Column("fecha_factura", sa.Date(), nullable=True))
        batch_op.create_check_constraint("ck_goods_receipt_type", "tipo IN ('PARCIAL','TOTAL')")

    op.create_table(
        "material_change_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("folio", sa.String(length=30), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(length=22), server_default="PENDIENTE_AUTORIZACION", nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=False),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.Column("rejection_reason", sa.String(length=300), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE_AUTORIZACION','APROBADA','RECHAZADA')",
            name="ck_material_change_request_status",
        ),
        sa.ForeignKeyConstraint(["approved_by_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["centros_costo.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("folio"),
    )
    op.create_index("ix_material_change_requests_folio", "material_change_requests", ["folio"], unique=True)

    op.create_table(
        "material_change_request_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("budget_item_id", sa.Integer(), nullable=False),
        sa.Column("existing_explosion_item_id", sa.Integer(), nullable=True),
        sa.Column("action_type", sa.String(length=10), nullable=False),
        sa.Column("supply_key", sa.String(length=40), nullable=True),
        sa.Column("supply_type", sa.String(length=20), nullable=False),
        sa.Column("descripcion", sa.String(length=180), nullable=False),
        sa.Column("unidad", sa.String(length=20), nullable=False),
        sa.Column("cantidad", sa.Numeric(16, 4), nullable=False),
        sa.Column("precio_estimado", sa.Numeric(16, 4), nullable=False),
        sa.Column("justificacion_tipo", sa.String(length=30), nullable=False),
        sa.Column("justificacion", sa.String(length=500), nullable=False),
        sa.Column("generated_explosion_item_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("action_type IN ('NUEVO','AUMENTO')", name="ck_smnc_action_type"),
        sa.CheckConstraint("cantidad > 0", name="ck_smnc_quantity"),
        sa.CheckConstraint("precio_estimado >= 0", name="ck_smnc_price"),
        sa.CheckConstraint(
            "justificacion_tipo IN ('MATERIAL_NO_CONTEMPLADO','ERROR_CUANTIFICACION','CAMBIO_PROYECTO')",
            name="ck_smnc_justification_type",
        ),
        sa.ForeignKeyConstraint(["budget_item_id"], ["budget_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["existing_explosion_item_id"], ["budget_explosion_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["generated_explosion_item_id"], ["budget_explosion_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["request_id"], ["material_change_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "purchase_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=50), nullable=False),
        sa.Column("mensaje", sa.String(length=500), nullable=False),
        sa.Column("enlace", sa.String(length=300), nullable=True),
        sa.Column("leida", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_purchase_notifications_created_at", "purchase_notifications", ["created_at"], unique=False)

    with op.batch_alter_table("additional_payments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("payment_method_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_additional_payment_payment_method",
            "payment_methods",
            ["payment_method_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_additional_payments_payment_method_id", ["payment_method_id"])


def downgrade():
    with op.batch_alter_table("additional_payments", schema=None) as batch_op:
        batch_op.drop_index("ix_additional_payments_payment_method_id")
        batch_op.drop_constraint("fk_additional_payment_payment_method", type_="foreignkey")
        batch_op.drop_column("payment_method_id")

    op.drop_index("ix_purchase_notifications_created_at", table_name="purchase_notifications")
    op.drop_table("purchase_notifications")
    op.drop_table("material_change_request_lines")
    op.drop_index("ix_material_change_requests_folio", table_name="material_change_requests")
    op.drop_table("material_change_requests")

    with op.batch_alter_table("goods_receipts", schema=None) as batch_op:
        batch_op.drop_constraint("ck_goods_receipt_type", type_="check")
        batch_op.drop_column("fecha_factura")
        batch_op.drop_column("tipo")

    with op.batch_alter_table("purchase_order_lines", schema=None) as batch_op:
        batch_op.drop_constraint("uq_order_requisition_line", type_="unique")
        batch_op.create_unique_constraint("uq_order_explosion_item", ["order_id", "explosion_item_id"])

    with op.batch_alter_table("purchase_orders", schema=None) as batch_op:
        batch_op.drop_index("ix_purchase_orders_fecha_vencimiento")
        batch_op.drop_constraint("ck_purchase_order_advance_pending", type_="check")
        batch_op.drop_constraint("ck_purchase_order_advance", type_="check")
        batch_op.drop_constraint("ck_purchase_order_payment_mode", type_="check")
        batch_op.drop_constraint("fk_purchase_order_advance_authorizer", type_="foreignkey")
        batch_op.drop_constraint("fk_purchase_order_payment_method", type_="foreignkey")
        batch_op.drop_constraint("fk_purchase_order_buyer", type_="foreignkey")
        batch_op.drop_constraint("fk_purchase_order_company", type_="foreignkey")
        batch_op.drop_constraint("fk_purchase_order_quotation", type_="foreignkey")
        batch_op.drop_constraint("ck_purchase_order_status", type_="check")
        for name in [
            "delivery_notified_at", "fecha_vencimiento", "fecha_factura", "numero_factura",
            "fecha_autorizacion_anticipo", "autorizado_anticipo_por_id", "justificacion_anticipo",
            "anticipo_pendiente", "anticipo_monto", "modalidad_pago", "fecha_limite",
            "fecha_surtido_real", "payment_method_id", "buyer_id", "company_id", "quotation_id",
        ]:
            batch_op.drop_column(name)
        batch_op.alter_column("estado", existing_type=sa.String(length=30), type_=sa.String(length=15), existing_nullable=False)
        batch_op.alter_column(
            "fecha_entrega_estimada", existing_type=sa.Date(), nullable=True
        )
        batch_op.create_check_constraint(
            "ck_purchase_order_status",
            "estado IN ('BORRADOR','EMITIDA','PARCIAL','RECIBIDA','CANCELADA')",
        )

    op.drop_table("quotation_lines")
    op.drop_index("ix_quotations_requisition_id", table_name="quotations")
    op.drop_index("ix_quotations_folio", table_name="quotations")
    op.drop_table("quotations")

    with op.batch_alter_table("purchase_requisition_lines", schema=None) as batch_op:
        batch_op.drop_constraint("ck_requisition_line_status", type_="check")
        batch_op.drop_constraint("ck_requisition_line_approved_quantity", type_="check")
        batch_op.drop_column("motivo_rechazo_compras")
        batch_op.drop_column("estado_linea")
        batch_op.drop_column("cantidad_aprobada")

    with op.batch_alter_table("purchase_requisitions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_purchase_requisition_status", type_="check")
        batch_op.drop_column("expiry_notified_at")
        batch_op.drop_column("fecha_limite_oc")
        batch_op.drop_column("submitted_at")
        batch_op.alter_column("estado", existing_type=sa.String(length=22), type_=sa.String(length=15), existing_nullable=False)
        batch_op.create_check_constraint(
            "ck_purchase_requisition_status",
            "estado IN ('BORRADOR','SOLICITADA','APROBADA','RECHAZADA','PARCIAL','ATENDIDA','CANCELADA')",
        )

    with op.batch_alter_table("budget_explosion_items", schema=None) as batch_op:
        batch_op.drop_constraint("ck_explosion_source", type_="check")
        batch_op.drop_column("origen")

    with op.batch_alter_table("supply_items", schema=None) as batch_op:
        batch_op.alter_column("unidad", existing_type=sa.String(length=20), type_=sa.String(length=3), existing_nullable=False)
        batch_op.alter_column("descripcion", existing_type=sa.String(length=180), type_=sa.String(length=70), existing_nullable=False)
        batch_op.create_check_constraint("ck_supply_item_unit_length", "length(unidad) <= 3")

    with op.batch_alter_table("suppliers", schema=None) as batch_op:
        batch_op.drop_constraint("ck_supplier_credit_configuration", type_="check")
        batch_op.drop_constraint("ck_supplier_credit_days", type_="check")
        batch_op.drop_constraint("ck_supplier_credit_limit", type_="check")
        batch_op.drop_constraint("fk_suppliers_company", type_="foreignkey")
        batch_op.drop_column("dias_credito")
        batch_op.drop_column("limite_credito")
        batch_op.drop_column("tiene_credito")
        batch_op.drop_column("company_id")

    op.drop_table("payment_methods")

    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_constraint("ck_usuarios_rol", type_="check")
        batch_op.create_check_constraint("ck_usuarios_rol", "rol IN ('admin','capturista')")

    with op.batch_alter_table("centros_costo", schema=None) as batch_op:
        batch_op.alter_column(
            "created_at", existing_type=sa.DateTime(timezone=True), nullable=True
        )
        batch_op.alter_column(
            "codigo", existing_type=sa.String(length=40), nullable=True
        )
