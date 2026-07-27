"""Integra el sistema original de nóminas al ERP V2.

Revision ID: 8b6d4f2a1c90
Revises: 3c7e9a1b2d4f
Create Date: 2026-07-21

La migración conserva usuarios y centros existentes. No elimina la tabla
``registros_semanales`` si una instalación previa llegó a crearla.
"""

from alembic import op
import sqlalchemy as sa


revision = "8b6d4f2a1c90"
down_revision = "3c7e9a1b2d4f"
branch_labels = None
depends_on = None


def _extend_centros_costo() -> None:
    """Agrega datos de presupuesto y asigna códigos a centros existentes."""

    connection = op.get_bind()
    is_sqlite = connection.dialect.name == "sqlite"

    # Se usan ALTER TABLE ADD COLUMN directos. En SQLite, batch_alter_table
    # recrearía centros_costo y podría activar ON DELETE SET NULL sobre las
    # asignaciones existentes de usuarios durante el reemplazo temporal.
    op.add_column(
        "centros_costo",
        sa.Column("codigo", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "centros_costo",
        sa.Column(
            "presupuesto_total",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        )
    )
    op.add_column(
        "centros_costo",
        sa.Column(
            "presupuesto_mano_obra",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        )
    )
    op.add_column(
        "centros_costo", sa.Column("descripcion", sa.Text(), nullable=True)
    )
    op.add_column(
        "centros_costo",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=None if is_sqlite else sa.func.now(),
            nullable=True,
        )
    )

    rows = connection.execute(
        sa.text("SELECT id FROM centros_costo ORDER BY id")
    ).fetchall()
    for row in rows:
        connection.execute(
            sa.text(
                "UPDATE centros_costo SET codigo = :codigo "
                "WHERE id = :centro_id AND codigo IS NULL"
            ),
            {"codigo": f"CC-{row.id:04d}", "centro_id": row.id},
        )
    connection.execute(
        sa.text(
            "UPDATE centros_costo SET created_at = CURRENT_TIMESTAMP "
            "WHERE created_at IS NULL"
        )
    )

    if not is_sqlite:
        op.alter_column(
            "centros_costo",
            "codigo", existing_type=sa.String(length=40), nullable=False
        )
        op.alter_column(
            "centros_costo",
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
    op.create_index(
        op.f("ix_centros_costo_codigo"),
        "centros_costo",
        ["codigo"],
        unique=True,
    )


def _create_catalogs() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column(
            "activa", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_table(
        "contractors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column("especialidad", sa.String(length=140), nullable=True),
        sa.Column("telefono", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=180), nullable=True),
        sa.Column(
            "activo", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )
    op.create_table(
        "budget_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("codigo", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column(
            "categoria",
            sa.String(length=25),
            server_default=sa.text("'MANO_OBRA'"),
            nullable=False,
        ),
        sa.Column(
            "presupuesto",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "activa", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.CheckConstraint(
            "categoria IN ('MANO_OBRA','SUBCONTRATO','INDIRECTO','ADICIONAL')",
            name="ck_budget_category",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["budget_items.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["centros_costo.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "codigo", name="uq_budget_code_project"
        ),
    )
    op.create_table(
        "user_projects",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["centros_costo.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["usuarios.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "project_id"),
    )
    op.create_table(
        "weekly_resource_availability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("semana_inicio", sa.Date(), nullable=False),
        sa.Column("metodo", sa.String(length=20), nullable=False),
        sa.Column(
            "monto_disponible",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("updated_by_id", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "metodo IN ('EFECTIVO','TRANSFERENCIA')",
            name="ck_weekly_resource_method",
        ),
        sa.CheckConstraint(
            "monto_disponible >= 0", name="ck_weekly_resource_amount"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "semana_inicio", "metodo", name="uq_weekly_resource_method"
        ),
    )
    with op.batch_alter_table(
        "weekly_resource_availability", schema=None
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_weekly_resource_availability_semana_inicio"),
            ["semana_inicio"],
            unique=False,
        )


def _create_payroll_tables() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre_completo", sa.String(length=180), nullable=False),
        sa.Column("fecha_ingreso", sa.Date(), nullable=False),
        sa.Column("fecha_baja", sa.Date(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("puesto", sa.String(length=120), nullable=False),
        sa.Column("cuadrilla", sa.String(length=100), nullable=True),
        sa.Column("supervisor", sa.String(length=120), nullable=True),
        sa.Column("empresa_operativa", sa.String(length=80), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("budget_item_id", sa.Integer(), nullable=True),
        sa.Column(
            "salario_semanal",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "registrado_imss",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("nss", sa.String(length=30), nullable=True),
        sa.Column("empresa_imss_id", sa.Integer(), nullable=True),
        sa.Column(
            "descuento_infonavit",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "imss_tipo",
            sa.String(length=15),
            server_default=sa.text("'FIJO'"),
            nullable=False,
        ),
        sa.Column(
            "descuento_imss",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "transferencia_predeterminada",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("empresa_transferencia_id", sa.Integer(), nullable=True),
        sa.Column("empresa_efectivo_id", sa.Integer(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "imss_tipo IN ('FIJO','PORCENTAJE')",
            name="ck_employee_imss_type",
        ),
        sa.ForeignKeyConstraint(
            ["budget_item_id"], ["budget_items.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["empresa_efectivo_id"], ["companies.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["empresa_imss_id"], ["companies.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["empresa_transferencia_id"],
            ["companies.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["centros_costo.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_employees_nombre_completo"),
            ["nombre_completo"],
            unique=False,
        )

    op.create_table(
        "payrolls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("semana_inicio", sa.Date(), nullable=False),
        sa.Column("semana_fin", sa.Date(), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=15),
            server_default=sa.text("'BORRADOR'"),
            nullable=False,
        ),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("closed_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "estado IN ('BORRADOR','CERRADA')", name="ck_payroll_status"
        ),
        sa.ForeignKeyConstraint(
            ["closed_by_id"], ["usuarios.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["centros_costo.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "semana_inicio", name="uq_payroll_project_week"
        ),
    )

    op.create_table(
        "payroll_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payroll_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("budget_item_id", sa.Integer(), nullable=False),
        sa.Column("nombre_trabajador", sa.String(length=180), nullable=False),
        sa.Column("puesto", sa.String(length=120), nullable=False),
        sa.Column("cuadrilla", sa.String(length=100), nullable=True),
        sa.Column("supervisor", sa.String(length=120), nullable=True),
        sa.Column("empresa_operativa", sa.String(length=80), nullable=True),
        sa.Column("salario_semanal", sa.Numeric(12, 2), nullable=False),
        sa.Column("lunes", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("martes", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("miercoles", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("jueves", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("viernes", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("dias_trabajados", sa.Numeric(4, 2), server_default=sa.text("5"), nullable=False),
        sa.Column("numero_faltas", sa.Numeric(4, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("sueldo_diario", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("descuento_faltas", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("monto_devengado", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("pago_extra", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("descuento_infonavit", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("descuento_imss", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("descuento_prestamo", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("otro_descuento", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("concepto_otro_descuento", sa.String(length=180), nullable=True),
        sa.Column("vales_gasolina", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("pago_transferencia", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("empresa_transferencia_id", sa.Integer(), nullable=True),
        sa.Column("pago_efectivo", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("empresa_efectivo_id", sa.Integer(), nullable=True),
        sa.Column("neto_pagar", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["budget_item_id"], ["budget_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["empresa_efectivo_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["empresa_transferencia_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payroll_id"], ["payrolls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payroll_id", "employee_id", name="uq_line_employee_payroll"),
    )

    op.create_table(
        "loans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("fecha_prestamo", sa.Date(), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("retencion_semanal", sa.Numeric(12, 2), nullable=False),
        sa.Column("metodo_entrega", sa.String(20), server_default=sa.text("'EFECTIVO'"), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("concepto", sa.String(220), nullable=True),
        sa.Column("estado", sa.String(15), server_default=sa.text("'ACTIVO'"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("estado IN ('ACTIVO','PAGADO','CANCELADO')", name="ck_loan_status"),
        sa.CheckConstraint("monto > 0", name="ck_loan_amount"),
        sa.CheckConstraint("retencion_semanal > 0", name="ck_loan_weekly"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "loan_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("loan_id", sa.Integer(), nullable=False),
        sa.Column("payroll_line_id", sa.Integer(), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payroll_line_id"], ["payroll_lines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("loan_id", "payroll_line_id", name="uq_loan_line_payment"),
    )


def _create_cost_tables() -> None:
    common_payment_columns = None  # Documento visual: las tablas se declaran explícitamente.
    del common_payment_columns

    op.create_table(
        "additional_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("budget_item_id", sa.Integer(), nullable=False),
        sa.Column("beneficiario", sa.String(180), nullable=False),
        sa.Column("concepto", sa.String(240), nullable=False),
        sa.Column("monto_capturado", sa.Numeric(12, 2), nullable=False),
        sa.Column("tipo_monto", sa.String(15), server_default=sa.text("'SIN_IVA'"), nullable=False),
        sa.Column("monto_sin_iva", sa.Numeric(12, 2), nullable=False),
        sa.Column("metodo_pago", sa.String(20), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["budget_item_id"], ["budget_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["centros_costo.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "office_expenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("budget_item_id", sa.Integer(), nullable=False),
        sa.Column("proveedor", sa.String(180), nullable=False),
        sa.Column("concepto", sa.String(240), nullable=False),
        sa.Column("monto_capturado", sa.Numeric(12, 2), nullable=False),
        sa.Column("tipo_monto", sa.String(15), server_default=sa.text("'SIN_IVA'"), nullable=False),
        sa.Column("monto_sin_iva", sa.Numeric(12, 2), nullable=False),
        sa.Column("metodo_pago", sa.String(20), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["budget_item_id"], ["budget_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["centros_costo.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "subcontracts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("budget_item_id", sa.Integer(), nullable=False),
        sa.Column("contractor_id", sa.Integer(), nullable=False),
        sa.Column("especialidad", sa.String(140), nullable=False),
        sa.Column("presupuesto_sin_iva", sa.Numeric(14, 2), nullable=False),
        sa.Column("avance_fisico", sa.Numeric(6, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("umbral_alerta", sa.Numeric(6, 4), server_default=sa.text("0.15"), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["budget_item_id"], ["budget_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contractor_id"], ["contractors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["centros_costo.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "contractor_id", "especialidad", name="uq_subcontract_scope"),
    )
    op.create_table(
        "subcontract_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subcontract_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("concepto", sa.String(180), nullable=False),
        sa.Column("monto_capturado", sa.Numeric(12, 2), nullable=False),
        sa.Column("tipo_monto", sa.String(15), server_default=sa.text("'SIN_IVA'"), nullable=False),
        sa.Column("monto_sin_iva", sa.Numeric(12, 2), nullable=False),
        sa.Column("metodo_pago", sa.String(20), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subcontract_id"], ["subcontracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _seed_shared_data() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO user_projects (user_id, project_id) "
            "SELECT id, centro_costo_id FROM usuarios "
            "WHERE rol = 'capturista' AND centro_costo_id IS NOT NULL "
            "AND NOT EXISTS ("
            "SELECT 1 FROM user_projects up "
            "WHERE up.user_id = usuarios.id "
            "AND up.project_id = usuarios.centro_costo_id)"
        )
    )

    company_table = sa.table(
        "companies",
        sa.column("codigo", sa.String),
        sa.column("nombre", sa.String),
        sa.column("activa", sa.Boolean),
    )
    op.bulk_insert(
        company_table,
        [
            {"codigo": "BCH", "nombre": "Baja Custom Homes", "activa": True},
            {"codigo": "RGOVC", "nombre": "RGOVC", "activa": True},
            {"codigo": "CA", "nombre": "Centenario Administración", "activa": True},
            {"codigo": "CN", "nombre": "Centenario National", "activa": True},
        ],
    )


def upgrade():
    _extend_centros_costo()
    _create_catalogs()
    _create_payroll_tables()
    _create_cost_tables()
    _seed_shared_data()


def downgrade():
    """Revierte estructura; no modifica la tabla cancelada de Fase 3."""

    op.drop_table("subcontract_payments")
    op.drop_table("subcontracts")
    op.drop_table("office_expenses")
    op.drop_table("additional_payments")
    op.drop_table("loan_payments")
    op.drop_table("loans")
    op.drop_table("payroll_lines")
    op.drop_table("payrolls")
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_employees_nombre_completo"))
    op.drop_table("employees")
    with op.batch_alter_table(
        "weekly_resource_availability", schema=None
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_weekly_resource_availability_semana_inicio")
        )
    op.drop_table("weekly_resource_availability")
    op.drop_table("user_projects")
    op.drop_table("budget_items")
    op.drop_table("contractors")
    op.drop_table("companies")

    with op.batch_alter_table("centros_costo", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_centros_costo_codigo"))
        batch_op.drop_column("created_at")
        batch_op.drop_column("descripcion")
        batch_op.drop_column("presupuesto_mano_obra")
        batch_op.drop_column("presupuesto_total")
        batch_op.drop_column("codigo")
