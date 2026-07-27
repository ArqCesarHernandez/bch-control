"""Ciclo financiero, MFA, rate limiting y datos sensibles.

Revision ID: c8d1f4a6b720
Revises: a4c7e2f9b615
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa


revision = "c8d1f4a6b720"
down_revision = "a4c7e2f9b615"
branch_labels = None
depends_on = None


def _set_sqlite_foreign_keys(enabled: bool) -> None:
    """Permite que Alembic reconstruya tablas referenciadas en SQLite.

    ``batch_alter_table`` crea una tabla temporal y sustituye la original.
    SQLite impide ese reemplazo si hay filas hijas mientras las llaves foráneas
    están activas. PostgreSQL no necesita ni admite este PRAGMA.
    """

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    with op.get_context().autocommit_block():
        bind.exec_driver_sql(
            f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}"
        )


def _protect_principal_admin() -> None:
    """Garantiza que la cuenta histórica principal (id=1) siga operativa."""

    op.get_bind().execute(
        sa.text(
            "UPDATE usuarios SET rol = 'admin', activo = :activo WHERE id = 1"
        ),
        {"activo": True},
    )


def _backfill_sensitive_permissions() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, rol FROM usuarios")).mappings().all()
    insert = sa.text(
        """
        INSERT INTO permisos
            (usuario_id, modulo, puede_ver, puede_crear, puede_editar, puede_eliminar)
        VALUES
            (:usuario_id, :modulo, :puede_ver, :puede_crear, :puede_editar, :puede_eliminar)
        """
    )
    for row in rows:
        is_admin = row["rol"] == "admin"
        for module in ("seguridad", "ver_nss_completo"):
            exists = bind.execute(
                sa.text(
                    "SELECT 1 FROM permisos WHERE usuario_id = :usuario_id AND modulo = :modulo"
                ),
                {"usuario_id": row["id"], "modulo": module},
            ).first()
            if exists:
                continue
            bind.execute(
                insert,
                {
                    "usuario_id": row["id"],
                    "modulo": module,
                    "puede_ver": is_admin,
                    "puede_crear": is_admin and module == "seguridad",
                    "puede_editar": is_admin and module == "seguridad",
                    "puede_eliminar": is_admin and module == "seguridad",
                },
            )


def upgrade():
    _set_sqlite_foreign_keys(False)
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_constraint("ck_usuarios_rol", type_="check")
        batch_op.add_column(
            sa.Column("intentos_fallidos", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("ventana_intentos_inicio", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("mfa_secret", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("mfa_confirmado_en", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_usuarios_rol",
            "rol IN ('admin','admin_financiero','capturista','supervisor','comprador','costos')",
        )
    op.create_index(
        "ix_usuarios_bloqueado_hasta", "usuarios", ["bloqueado_hasta"], unique=False
    )
    _protect_principal_admin()
    _backfill_sensitive_permissions()

    with op.batch_alter_table("payrolls", schema=None) as batch_op:
        batch_op.drop_constraint("ck_payroll_status", type_="check")
        batch_op.add_column(sa.Column("paid_by_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("reconciled_by_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_payrolls_paid_by_id_usuarios",
            "usuarios",
            ["paid_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_payrolls_reconciled_by_id_usuarios",
            "usuarios",
            ["reconciled_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute(
        sa.text(
            """
            UPDATE payrolls
            SET estado = CASE
                WHEN estado = 'CERRADA' THEN 'aprobada'
                ELSE 'borrador'
            END
            """
        )
    )
    with op.batch_alter_table("payrolls", schema=None) as batch_op:
        batch_op.alter_column(
            "estado",
            existing_type=sa.String(length=15),
            server_default=sa.text("'borrador'"),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_payroll_status",
            "estado IN ('borrador','enviada','aprobada','pagada','conciliada')",
        )
    op.create_index("ix_payrolls_estado", "payrolls", ["estado"], unique=False)

    with op.batch_alter_table("loans", schema=None) as batch_op:
        batch_op.drop_constraint("ck_loan_status", type_="check")
        batch_op.add_column(
            sa.Column("tasa_interes", sa.Float(), server_default="5.0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("total_pagar", sa.Numeric(12, 2), nullable=True)
        )
        batch_op.add_column(sa.Column("solicitante_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("aprobador_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("fecha_aprobacion", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("motivo_rechazo", sa.String(length=500), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_loans_solicitante_id_usuarios",
            "usuarios",
            ["solicitante_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_loans_aprobador_id_usuarios",
            "usuarios",
            ["aprobador_id"],
            ["id"],
            ondelete="SET NULL",
        )
    # Los contratos históricos no reciben interés retroactivo. Los nuevos sí
    # usan el default de 5% y calculan capital * 1.05 desde la aplicación.
    op.execute(
        sa.text(
            """
            UPDATE loans
            SET tasa_interes = 0,
                total_pagar = monto,
                solicitante_id = created_by_id,
                estado = CASE
                    WHEN estado = 'PAGADO' THEN 'liquidado'
                    WHEN estado = 'CANCELADO' THEN 'rechazado'
                    ELSE 'activo'
                END,
                motivo_rechazo = CASE
                    WHEN estado = 'CANCELADO' THEN 'Registro histórico cancelado antes de la migración.'
                    ELSE motivo_rechazo
                END
            """
        )
    )
    with op.batch_alter_table("loans", schema=None) as batch_op:
        batch_op.alter_column(
            "solicitante_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.alter_column(
            "total_pagar", existing_type=sa.Numeric(12, 2), nullable=False
        )
        batch_op.alter_column(
            "estado",
            existing_type=sa.String(length=15),
            server_default=sa.text("'pendiente'"),
            existing_nullable=False,
        )
        batch_op.create_check_constraint("ck_loan_interest", "tasa_interes >= 0")
        batch_op.create_check_constraint("ck_loan_total", "total_pagar >= monto")
        batch_op.create_check_constraint(
            "ck_loan_status",
            "estado IN ('pendiente','aprobado','rechazado','activo','liquidado')",
        )
    op.create_index("ix_loans_estado", "loans", ["estado"], unique=False)
    _set_sqlite_foreign_keys(True)


def downgrade():
    _set_sqlite_foreign_keys(False)
    op.drop_index("ix_loans_estado", table_name="loans")
    with op.batch_alter_table("loans", schema=None) as batch_op:
        batch_op.drop_constraint("ck_loan_status", type_="check")
        batch_op.drop_constraint("ck_loan_total", type_="check")
        batch_op.drop_constraint("ck_loan_interest", type_="check")
    op.execute(
        sa.text(
            """
            UPDATE loans
            SET estado = CASE
                WHEN estado = 'liquidado' THEN 'PAGADO'
                WHEN estado IN ('pendiente', 'rechazado') THEN 'CANCELADO'
                ELSE 'ACTIVO'
            END
            """
        )
    )
    with op.batch_alter_table("loans", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_loan_status", "estado IN ('ACTIVO','PAGADO','CANCELADO')"
        )
        batch_op.alter_column(
            "estado",
            existing_type=sa.String(length=15),
            server_default=sa.text("'ACTIVO'"),
            existing_nullable=False,
        )
        batch_op.drop_constraint("fk_loans_aprobador_id_usuarios", type_="foreignkey")
        batch_op.drop_constraint("fk_loans_solicitante_id_usuarios", type_="foreignkey")
        batch_op.drop_column("motivo_rechazo")
        batch_op.drop_column("fecha_aprobacion")
        batch_op.drop_column("aprobador_id")
        batch_op.drop_column("solicitante_id")
        batch_op.drop_column("total_pagar")
        batch_op.drop_column("tasa_interes")

    op.drop_index("ix_payrolls_estado", table_name="payrolls")
    with op.batch_alter_table("payrolls", schema=None) as batch_op:
        batch_op.drop_constraint("ck_payroll_status", type_="check")
    op.execute(
        sa.text(
            """
            UPDATE payrolls
            SET estado = CASE
                WHEN estado IN ('borrador','enviada') THEN 'BORRADOR'
                ELSE 'CERRADA'
            END
            """
        )
    )
    with op.batch_alter_table("payrolls", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_payroll_status", "estado IN ('BORRADOR','CERRADA')"
        )
        batch_op.alter_column(
            "estado",
            existing_type=sa.String(length=15),
            server_default=sa.text("'BORRADOR'"),
            existing_nullable=False,
        )
        batch_op.drop_constraint(
            "fk_payrolls_reconciled_by_id_usuarios", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_payrolls_paid_by_id_usuarios", type_="foreignkey"
        )
        batch_op.drop_column("reconciled_at")
        batch_op.drop_column("reconciled_by_id")
        batch_op.drop_column("paid_at")
        batch_op.drop_column("paid_by_id")

    # Las versiones anteriores ignoran estos módulos desconocidos. Conservar
    # las filas evita perder decisiones de acceso si luego se vuelve a subir.
    op.drop_index("ix_usuarios_bloqueado_hasta", table_name="usuarios")
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_constraint("ck_usuarios_rol", type_="check")
    op.execute(
        sa.text("UPDATE usuarios SET rol = 'admin' WHERE rol = 'admin_financiero'")
    )
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_usuarios_rol",
            "rol IN ('admin','capturista','supervisor','comprador','costos')",
        )
        batch_op.drop_column("mfa_confirmado_en")
        batch_op.drop_column("mfa_secret")
        batch_op.drop_column("bloqueado_hasta")
        batch_op.drop_column("ventana_intentos_inicio")
        batch_op.drop_column("intentos_fallidos")
    _set_sqlite_foreign_keys(True)
