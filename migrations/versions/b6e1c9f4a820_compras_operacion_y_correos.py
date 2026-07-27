"""Compras: parciales, proveedor sugerido, correos y rol supervisor.

Revision ID: b6e1c9f4a820
Revises: f2c8a1d4e705
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa


revision = "b6e1c9f4a820"
down_revision = "f2c8a1d4e705"
branch_labels = None
depends_on = None


def _replace_user_role_constraints(
    role_expression: str, center_expression: str
) -> None:
    """Reconstruye ``usuarios`` sin romper sus múltiples FK en SQLite.

    SQLite no permite modificar un CHECK y recrear ``usuarios`` rompería las
    múltiples FK de Compras, Nóminas y auditoría. En ese motor se sustituye de
    forma validada solo el texto de ambas restricciones en el catálogo del
    esquema; los datos y la tabla permanecen intactos. PostgreSQL altera las
    restricciones normalmente.
    """

    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    if is_sqlite:
        current_sql = bind.exec_driver_sql(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='usuarios'"
        ).scalar_one()
        role_candidates = (
            "rol IN ('admin','capturista','comprador','costos')",
            "rol IN ('admin','capturista','supervisor','comprador','costos')",
        )
        center_candidates = (
            "rol = 'capturista' OR centro_costo_id IS NULL",
            "rol IN ('capturista','supervisor') OR centro_costo_id IS NULL",
        )
        current_role = next(
            (
                candidate
                for candidate in role_candidates
                if f"CONSTRAINT ck_usuarios_rol CHECK ({candidate})"
                in current_sql
            ),
            None,
        )
        current_center = next(
            (
                candidate
                for candidate in center_candidates
                if (
                    "CONSTRAINT ck_usuarios_centro_segun_rol "
                    f"CHECK ({candidate})"
                )
                in current_sql
            ),
            None,
        )
        if not current_role or not current_center:
            raise RuntimeError(
                "No se localizaron las restricciones de rol de usuarios."
            )
        updated_sql = current_sql.replace(
            f"CONSTRAINT ck_usuarios_rol CHECK ({current_role})",
            f"CONSTRAINT ck_usuarios_rol CHECK ({role_expression})",
            1,
        ).replace(
            "CONSTRAINT ck_usuarios_centro_segun_rol "
            f"CHECK ({current_center})",
            "CONSTRAINT ck_usuarios_centro_segun_rol "
            f"CHECK ({center_expression})",
            1,
        )
        if updated_sql == current_sql:
            raise RuntimeError("No fue posible ampliar las restricciones de rol.")
        schema_version = bind.exec_driver_sql("PRAGMA schema_version").scalar_one()
        bind.exec_driver_sql("PRAGMA writable_schema=ON")
        try:
            result = bind.exec_driver_sql(
                "UPDATE sqlite_master SET sql=? "
                "WHERE type='table' AND name='usuarios'",
                (updated_sql,),
            )
            if result.rowcount != 1:
                raise RuntimeError(
                    "No fue posible actualizar el esquema de usuarios."
                )
            bind.exec_driver_sql(f"PRAGMA schema_version={schema_version + 1}")
        finally:
            bind.exec_driver_sql("PRAGMA writable_schema=OFF")
        return

    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_constraint("ck_usuarios_rol", type_="check")
        batch_op.drop_constraint(
            "ck_usuarios_centro_segun_rol", type_="check"
        )
        batch_op.create_check_constraint("ck_usuarios_rol", role_expression)
        batch_op.create_check_constraint(
            "ck_usuarios_centro_segun_rol", center_expression
        )


def _add_user_reference(table_name: str, column_name: str, fk_name: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} "
            "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"
        )
    else:
        op.add_column(table_name, sa.Column(column_name, sa.Integer(), nullable=True))
        op.create_foreign_key(
            fk_name,
            table_name,
            "usuarios",
            [column_name],
            ["id"],
            ondelete="SET NULL",
        )


def _normalize_sqlite_user_reference(
    table_name: str, column_name: str, fk_name: str
) -> None:
    """Convierte la FK inline de ``ALTER TABLE`` en una FK de tabla.

    SQLite conserva correctamente ``ON DELETE SET NULL`` en ambos formatos,
    pero SQLAlchemy no refleja esa opción cuando la columna se agregó como FK
    inline. La forma de tabla evita falsos cambios en ``flask db check`` sin
    reconstruir tablas que ya tienen relaciones y datos.
    """

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    current_sql = bind.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).scalar_one()
    inline_reference = (
        f"{column_name} INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"
    )
    if inline_reference not in current_sql:
        raise RuntimeError(
            f"No se localizo la referencia nueva {table_name}.{column_name}."
        )

    updated_sql = current_sql.replace(
        inline_reference, f"{column_name} INTEGER", 1
    )
    closing_parenthesis = updated_sql.rfind(")")
    if closing_parenthesis < 0:
        raise RuntimeError(f"Esquema SQLite invalido para {table_name}.")
    constraint = (
        f"CONSTRAINT {fk_name} FOREIGN KEY({column_name}) "
        "REFERENCES usuarios (id) ON DELETE SET NULL"
    )
    updated_sql = (
        updated_sql[:closing_parenthesis].rstrip()
        + ", \n\t"
        + constraint
        + "\n"
        + updated_sql[closing_parenthesis:]
    )

    schema_version = bind.exec_driver_sql("PRAGMA schema_version").scalar_one()
    bind.exec_driver_sql("PRAGMA writable_schema=ON")
    try:
        result = bind.exec_driver_sql(
            "UPDATE sqlite_master SET sql=? "
            "WHERE type='table' AND name=?",
            (updated_sql, table_name),
        )
        if result.rowcount != 1:
            raise RuntimeError(
                f"No fue posible normalizar la referencia de {table_name}."
            )
        bind.exec_driver_sql(f"PRAGMA schema_version={schema_version + 1}")
    finally:
        bind.exec_driver_sql("PRAGMA writable_schema=OFF")


def _remove_sqlite_user_reference_constraint(
    table_name: str, column_name: str, fk_name: str
) -> None:
    """Retira la FK de tabla antes de eliminar su columna al revertir."""

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    current_sql = bind.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).scalar_one()
    constraint = (
        f", \n\tCONSTRAINT {fk_name} FOREIGN KEY({column_name}) "
        "REFERENCES usuarios (id) ON DELETE SET NULL"
    )
    if constraint not in current_sql:
        raise RuntimeError(
            f"No se localizo la referencia {table_name}.{column_name}."
        )
    updated_sql = current_sql.replace(constraint, "", 1)
    schema_version = bind.exec_driver_sql("PRAGMA schema_version").scalar_one()
    bind.exec_driver_sql("PRAGMA writable_schema=ON")
    try:
        result = bind.exec_driver_sql(
            "UPDATE sqlite_master SET sql=? "
            "WHERE type='table' AND name=?",
            (updated_sql, table_name),
        )
        if result.rowcount != 1:
            raise RuntimeError(
                f"No fue posible retirar la referencia de {table_name}."
            )
        bind.exec_driver_sql(f"PRAGMA schema_version={schema_version + 1}")
    finally:
        bind.exec_driver_sql("PRAGMA writable_schema=OFF")


def upgrade():
    # Capturista y Supervisor dejan de compartir permisos e interfaz.
    _replace_user_role_constraints(
        "rol IN ('admin','capturista','supervisor','comprador','costos')",
        "rol IN ('capturista','supervisor') OR centro_costo_id IS NULL",
    )

    _add_user_reference(
        "purchase_requisitions",
        "buyer_received_by_id",
        "fk_purchase_requisition_buyer_received_by",
    )
    _normalize_sqlite_user_reference(
        "purchase_requisitions",
        "buyer_received_by_id",
        "fk_purchase_requisition_buyer_received_by",
    )
    op.add_column(
        "purchase_requisitions",
        sa.Column("buyer_received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_purchase_requisitions_buyer_received_by_id",
        "purchase_requisitions",
        ["buyer_received_by_id"],
    )

    op.add_column(
        "purchase_requisition_lines",
        sa.Column("proveedor_sugerido", sa.String(length=180), nullable=True),
    )
    op.create_index(
        "ix_purchase_requisition_lines_proveedor_sugerido",
        "purchase_requisition_lines",
        ["proveedor_sugerido"],
    )

    op.add_column(
        "quotations",
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_user_reference(
        "quotations", "email_sent_by_id", "fk_quotation_email_sent_by"
    )
    op.add_column(
        "quotations", sa.Column("email_to", sa.String(length=180), nullable=True)
    )
    op.add_column(
        "quotations", sa.Column("email_cc", sa.String(length=180), nullable=True)
    )
    op.add_column(
        "quotations", sa.Column("email_error", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "quotations",
        sa.Column("whatsapp_contacted_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_user_reference(
        "quotations",
        "whatsapp_contacted_by_id",
        "fk_quotation_whatsapp_contacted_by",
    )
    _normalize_sqlite_user_reference(
        "quotations", "email_sent_by_id", "fk_quotation_email_sent_by"
    )
    _normalize_sqlite_user_reference(
        "quotations",
        "whatsapp_contacted_by_id",
        "fk_quotation_whatsapp_contacted_by",
    )
    op.add_column(
        "quotations",
        sa.Column("whatsapp_notes", sa.String(length=500), nullable=True),
    )
    op.create_index(
        "ix_quotations_email_sent_by_id", "quotations", ["email_sent_by_id"]
    )
    op.create_index(
        "ix_quotations_whatsapp_contacted_by_id",
        "quotations",
        ["whatsapp_contacted_by_id"],
    )

    op.add_column(
        "goods_receipts",
        sa.Column(
            "notification_email_sent_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "goods_receipts",
        sa.Column("notification_email_error", sa.String(length=500), nullable=True),
    )


def downgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.drop_column("goods_receipts", "notification_email_error")
    op.drop_column("goods_receipts", "notification_email_sent_at")

    _remove_sqlite_user_reference_constraint(
        "quotations",
        "whatsapp_contacted_by_id",
        "fk_quotation_whatsapp_contacted_by",
    )
    _remove_sqlite_user_reference_constraint(
        "quotations", "email_sent_by_id", "fk_quotation_email_sent_by"
    )
    op.drop_index("ix_quotations_whatsapp_contacted_by_id", table_name="quotations")
    op.drop_index("ix_quotations_email_sent_by_id", table_name="quotations")
    op.drop_column("quotations", "whatsapp_notes")
    if not is_sqlite:
        op.drop_constraint(
            "fk_quotation_whatsapp_contacted_by", "quotations", type_="foreignkey"
        )
    op.drop_column("quotations", "whatsapp_contacted_by_id")
    op.drop_column("quotations", "whatsapp_contacted_at")
    op.drop_column("quotations", "email_error")
    op.drop_column("quotations", "email_cc")
    op.drop_column("quotations", "email_to")
    if not is_sqlite:
        op.drop_constraint(
            "fk_quotation_email_sent_by", "quotations", type_="foreignkey"
        )
    op.drop_column("quotations", "email_sent_by_id")
    op.drop_column("quotations", "email_sent_at")

    op.drop_index(
        "ix_purchase_requisition_lines_proveedor_sugerido",
        table_name="purchase_requisition_lines",
    )
    op.drop_column("purchase_requisition_lines", "proveedor_sugerido")

    op.drop_index(
        "ix_purchase_requisitions_buyer_received_by_id",
        table_name="purchase_requisitions",
    )
    _remove_sqlite_user_reference_constraint(
        "purchase_requisitions",
        "buyer_received_by_id",
        "fk_purchase_requisition_buyer_received_by",
    )
    op.drop_column("purchase_requisitions", "buyer_received_at")
    if not is_sqlite:
        op.drop_constraint(
            "fk_purchase_requisition_buyer_received_by",
            "purchase_requisitions",
            type_="foreignkey",
        )
    op.drop_column("purchase_requisitions", "buyer_received_by_id")

    # La versión anterior no conoce el rol separado. Si se revierte, esos
    # usuarios conservan sus obras y regresan al rol operativo histórico.
    op.execute("UPDATE usuarios SET rol='capturista' WHERE rol='supervisor'")
    _replace_user_role_constraints(
        "rol IN ('admin','capturista','comprador','costos')",
        "rol = 'capturista' OR centro_costo_id IS NULL",
    )
