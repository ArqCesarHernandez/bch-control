"""Tipos de OC, permisos configurables y tarjetas de crédito.

Revision ID: e9a3f7c2d614
Revises: b6e1c9f4a820
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa


revision = "e9a3f7c2d614"
down_revision = "b6e1c9f4a820"
branch_labels = None
depends_on = None


MODULES = (
    "nomina",
    "compras",
    "requisiciones",
    "oc_operaciones",
    "proveedores",
    "reportes",
    "usuarios",
    "centros_costo",
    "tarjetas_credito",
)


def _role_permissions(role: str, module: str) -> tuple[bool, bool, bool, bool]:
    if role == "admin":
        return True, True, True, True
    if role == "capturista" and module == "nomina":
        return True, True, True, False
    if role == "supervisor":
        if module in {"nomina", "requisiciones", "oc_operaciones"}:
            return True, True, True, False
    if role == "comprador" and module in {
        "compras",
        "requisiciones",
        "proveedores",
        "reportes",
    }:
        return True, True, True, True
    if role == "costos":
        if module == "reportes":
            return True, True, True, True
        if module == "centros_costo":
            return True, True, True, False
        if module in {"compras", "requisiciones"}:
            return True, False, False, False
    return False, False, False, False


def _backfill_permissions() -> None:
    bind = op.get_bind()
    users = bind.execute(sa.text("SELECT id, rol FROM usuarios")).mappings().all()
    insert = sa.text(
        """
        INSERT INTO permisos
            (usuario_id, modulo, puede_ver, puede_crear, puede_editar,
             puede_eliminar)
        VALUES
            (:usuario_id, :modulo, :puede_ver, :puede_crear,
             :puede_editar, :puede_eliminar)
        """
    )
    for user in users:
        for module in MODULES:
            can_view, can_create, can_edit, can_delete = _role_permissions(
                user["rol"], module
            )
            bind.execute(
                insert,
                {
                    "usuario_id": user["id"],
                    "modulo": module,
                    "puede_ver": can_view,
                    "puede_crear": can_create,
                    "puede_editar": can_edit,
                    "puede_eliminar": can_delete,
                },
            )


def _classify_operational_supplies() -> None:
    """Marca solo descripciones inequívocas; los demás quedan para revisión."""

    bind = op.get_bind()
    rules = (
        (
            "RETIRO_ESCOMBRO",
            "UPPER(descripcion) LIKE '%RETIRO%ESCOMBRO%'",
        ),
        (
            "TIERRA_RELLENO",
            "UPPER(descripcion) LIKE '%TIERRA%RELLENO%'",
        ),
        ("ARENA", "UPPER(descripcion) LIKE '%ARENA%'"),
        ("GRAVA", "UPPER(descripcion) LIKE '%GRAVA%'"),
        ("AGREGADOS", "UPPER(descripcion) LIKE '%AGREGADO%'"),
        ("AGUA", "UPPER(descripcion) LIKE '%AGUA%'"),
        (
            "RENTA_EQUIPO",
            "(UPPER(descripcion) LIKE '%RETROEXCAVADORA%' "
            "OR UPPER(descripcion) LIKE '%EXCAVADORA%' "
            "OR UPPER(descripcion) LIKE '%BOBCAT%') "
            "AND (UPPER(descripcion) LIKE '%RENTA%' "
            "OR UPPER(descripcion) LIKE '%HORA%')",
        ),
        (
            "GASTO_OFICINA",
            "tipo = 'INDIRECTO' AND (UPPER(descripcion) LIKE '%OFICINA%' "
            "OR UPPER(descripcion) LIKE '%PAPELERIA%' "
            "OR UPPER(descripcion) LIKE '%PAPELERÍA%')",
        ),
    )
    for category, condition in rules:
        bind.execute(
            sa.text(
                "UPDATE supply_items "
                "SET es_operacion = :enabled, categoria_operacion = :category "
                f"WHERE es_operacion = :disabled AND ({condition})"
            ),
            {"category": category, "enabled": True, "disabled": False},
        )


def upgrade():
    op.create_table(
        "permisos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("modulo", sa.String(length=50), nullable=False),
        sa.Column(
            "puede_ver", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "puede_crear", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "puede_editar", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "puede_eliminar", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "usuario_id", "modulo", name="uq_permisos_usuario_modulo"
        ),
    )
    op.create_index("ix_permisos_usuario_id", "permisos", ["usuario_id"])
    _backfill_permissions()

    op.add_column(
        "supply_items",
        sa.Column(
            "es_operacion", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.add_column(
        "supply_items",
        sa.Column("categoria_operacion", sa.String(length=30), nullable=True),
    )
    op.create_index(
        "ix_supply_items_es_operacion", "supply_items", ["es_operacion"]
    )
    op.create_index(
        "ix_supply_items_categoria_operacion",
        "supply_items",
        ["categoria_operacion"],
    )
    _classify_operational_supplies()

    op.add_column(
        "purchase_requisitions",
        sa.Column(
            "tipo_requisicion",
            sa.String(length=12),
            server_default="COMPRAS",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_purchase_requisitions_tipo_requisicion",
        "purchase_requisitions",
        ["tipo_requisicion"],
    )

    op.add_column(
        "purchase_orders",
        sa.Column(
            "tipo_oc",
            sa.String(length=12),
            server_default="COMPRAS",
            nullable=False,
        ),
    )
    op.add_column(
        "purchase_orders",
        sa.Column(
            "categoria_pago",
            sa.String(length=12),
            server_default="COMPRAS",
            nullable=False,
        ),
    )
    op.add_column(
        "purchase_orders",
        sa.Column(
            "requiere_autorizacion",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "purchase_orders",
        sa.Column(
            "autorizacion_solicitada_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index("ix_purchase_orders_tipo_oc", "purchase_orders", ["tipo_oc"])
    op.create_index(
        "ix_purchase_orders_categoria_pago",
        "purchase_orders",
        ["categoria_pago"],
    )
    op.create_index(
        "ix_purchase_orders_requiere_autorizacion",
        "purchase_orders",
        ["requiere_autorizacion"],
    )

    op.add_column(
        "purchase_alert_runs",
        sa.Column(
            "tarjetas_por_vencer",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    op.create_table(
        "tarjetas_credito",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("numero_tarjeta", sa.String(length=30), nullable=False),
        sa.Column("fecha_corte", sa.Date(), nullable=False),
        sa.Column("fecha_pago", sa.Date(), nullable=False),
        sa.Column("limite_credito", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "saldo_actual",
            sa.Numeric(14, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "activa", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("payment_due_notified_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "limite_credito >= 0", name="ck_credit_card_credit_limit"
        ),
        sa.CheckConstraint(
            "saldo_actual >= 0", name="ck_credit_card_balance"
        ),
        sa.CheckConstraint(
            "fecha_pago >= fecha_corte", name="ck_credit_card_cycle_dates"
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tarjetas_credito_empresa_id", "tarjetas_credito", ["empresa_id"]
    )
    op.create_index(
        "ix_tarjetas_credito_fecha_corte", "tarjetas_credito", ["fecha_corte"]
    )
    op.create_index(
        "ix_tarjetas_credito_fecha_pago", "tarjetas_credito", ["fecha_pago"]
    )

    op.create_table(
        "tarjetas_credito_pagos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tarjeta_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("monto", sa.Numeric(14, 2), nullable=False),
        sa.Column("saldo_anterior", sa.Numeric(14, 2), nullable=False),
        sa.Column("saldo_nuevo", sa.Numeric(14, 2), nullable=False),
        sa.Column("referencia", sa.String(length=120), nullable=True),
        sa.Column("notas", sa.String(length=500), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "monto > 0", name="ck_credit_card_payment_amount"
        ),
        sa.CheckConstraint(
            "saldo_anterior >= 0 AND saldo_nuevo >= 0",
            name="ck_credit_card_payment_balances",
        ),
        sa.ForeignKeyConstraint(
            ["tarjeta_id"], ["tarjetas_credito.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tarjetas_credito_pagos_tarjeta_id",
        "tarjetas_credito_pagos",
        ["tarjeta_id"],
    )
    op.create_index(
        "ix_tarjetas_credito_pagos_fecha",
        "tarjetas_credito_pagos",
        ["fecha"],
    )


def downgrade():
    op.drop_index(
        "ix_tarjetas_credito_pagos_fecha",
        table_name="tarjetas_credito_pagos",
    )
    op.drop_index(
        "ix_tarjetas_credito_pagos_tarjeta_id",
        table_name="tarjetas_credito_pagos",
    )
    op.drop_table("tarjetas_credito_pagos")
    op.drop_index("ix_tarjetas_credito_fecha_pago", table_name="tarjetas_credito")
    op.drop_index("ix_tarjetas_credito_fecha_corte", table_name="tarjetas_credito")
    op.drop_index("ix_tarjetas_credito_empresa_id", table_name="tarjetas_credito")
    op.drop_table("tarjetas_credito")

    op.drop_column("purchase_alert_runs", "tarjetas_por_vencer")

    op.drop_index(
        "ix_purchase_orders_requiere_autorizacion",
        table_name="purchase_orders",
    )
    op.drop_index(
        "ix_purchase_orders_categoria_pago", table_name="purchase_orders"
    )
    op.drop_index("ix_purchase_orders_tipo_oc", table_name="purchase_orders")
    op.drop_column("purchase_orders", "autorizacion_solicitada_at")
    op.drop_column("purchase_orders", "requiere_autorizacion")
    op.drop_column("purchase_orders", "categoria_pago")
    op.drop_column("purchase_orders", "tipo_oc")

    op.drop_index(
        "ix_purchase_requisitions_tipo_requisicion",
        table_name="purchase_requisitions",
    )
    op.drop_column("purchase_requisitions", "tipo_requisicion")

    op.drop_index(
        "ix_supply_items_categoria_operacion", table_name="supply_items"
    )
    op.drop_index("ix_supply_items_es_operacion", table_name="supply_items")
    op.drop_column("supply_items", "categoria_operacion")
    op.drop_column("supply_items", "es_operacion")

    op.drop_index("ix_permisos_usuario_id", table_name="permisos")
    op.drop_table("permisos")
