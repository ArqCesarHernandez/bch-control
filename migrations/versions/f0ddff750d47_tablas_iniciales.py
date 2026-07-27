"""Tablas iniciales de autenticación y administración.

Revision ID: f0ddff750d47
Revises:
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "f0ddff750d47"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "centros_costo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=20),
            server_default=sa.text("'activa'"),
            nullable=False,
        ),
        sa.Column("fecha_apertura", sa.Date(), nullable=True),
        sa.Column("fecha_cierre", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "fecha_cierre IS NULL OR fecha_apertura IS NULL "
            "OR fecha_cierre >= fecha_apertura",
            name="ck_centros_costo_fechas",
        ),
        sa.CheckConstraint(
            "tipo IN ('obra', 'oficina')", name="ck_centros_costo_tipo"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_centros_costo_nombre"),
        "centros_costo",
        ["nombre"],
        unique=False,
    )

    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre_completo", sa.String(length=150), nullable=False),
        sa.Column("correo", sa.String(length=120), nullable=False),
        sa.Column("contrasena_hash", sa.String(length=256), nullable=False),
        sa.Column("rol", sa.String(length=20), nullable=False),
        sa.Column("centro_costo_id", sa.Integer(), nullable=True),
        sa.Column(
            "activo", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column(
            "fecha_alta",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rol = 'capturista' OR centro_costo_id IS NULL",
            name="ck_usuarios_centro_segun_rol",
        ),
        sa.CheckConstraint(
            "rol IN ('admin', 'capturista')", name="ck_usuarios_rol"
        ),
        sa.ForeignKeyConstraint(
            ["centro_costo_id"], ["centros_costo.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("correo"),
    )
    op.create_index(
        op.f("ix_usuarios_centro_costo_id"),
        "usuarios",
        ["centro_costo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_usuarios_correo"), "usuarios", ["correo"], unique=True
    )

    op.create_table(
        "bitacora_auditoria",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("accion", sa.String(length=100), nullable=False),
        sa.Column("tabla_afectada", sa.String(length=50), nullable=False),
        sa.Column("registro_id", sa.Integer(), nullable=True),
        sa.Column(
            "fecha_hora",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("detalle", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bitacora_auditoria_fecha_hora"),
        "bitacora_auditoria",
        ["fecha_hora"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bitacora_auditoria_usuario_id"),
        "bitacora_auditoria",
        ["usuario_id"],
        unique=False,
    )
    op.create_index(
        "ix_bitacora_tabla_registro",
        "bitacora_auditoria",
        ["tabla_afectada", "registro_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_bitacora_tabla_registro", table_name="bitacora_auditoria")
    op.drop_index(
        op.f("ix_bitacora_auditoria_usuario_id"),
        table_name="bitacora_auditoria",
    )
    op.drop_index(
        op.f("ix_bitacora_auditoria_fecha_hora"),
        table_name="bitacora_auditoria",
    )
    op.drop_table("bitacora_auditoria")
    op.drop_index(op.f("ix_usuarios_correo"), table_name="usuarios")
    op.drop_index(op.f("ix_usuarios_centro_costo_id"), table_name="usuarios")
    op.drop_table("usuarios")
    op.drop_index(op.f("ix_centros_costo_nombre"), table_name="centros_costo")
    op.drop_table("centros_costo")

