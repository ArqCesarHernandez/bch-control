"""Fase 5: roles ampliados y funcionalidades de campo.

Revision ID: c6d9a4c5880d
Revises: c8d1f4a6b720
Create Date: 2026-07-22

"""
from alembic import op
import sqlalchemy as sa


# Identificadores de revisión usados por Alembic.
revision = "c6d9a4c5880d"
down_revision = "c8d1f4a6b720"
branch_labels = None
depends_on = None


PHASE5_MODULES = (
    "parte_diario",
    "avance_obra",
    "certificaciones",
    "no_conformidades",
    "rfis",
    "seguridad_obra",
    "licitaciones",
    "contratos",
    "recepcion_materiales",
    "conciliacion_facturas",
    "dashboard_ejecutivo",
)


def _set_sqlite_foreign_keys(enabled: bool) -> None:
    """Permite reconstruir tablas referenciadas durante la migración SQLite."""

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    with op.get_context().autocommit_block():
        bind.exec_driver_sql(
            f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}"
        )


def _role_defaults(role: str, module: str) -> dict[str, bool]:
    values = {
        "ver": False,
        "crear": False,
        "editar": False,
        "eliminar": False,
        "aprobar": False,
    }

    def grant(*actions: str) -> None:
        for action in actions:
            values[action] = True

    all_actions = tuple(values)
    if role == "admin":
        grant(*all_actions)
    elif role == "admin_financiero":
        if module == "conciliacion_facturas":
            grant(*all_actions)
        elif module in {"contratos", "dashboard_ejecutivo"}:
            grant("ver")
    elif role == "supervisor":
        if module in {
            "parte_diario",
            "avance_obra",
            "no_conformidades",
            "rfis",
            "seguridad_obra",
        }:
            grant(*all_actions)
        elif module == "certificaciones":
            grant("ver", "crear", "editar", "aprobar")
        elif module == "recepcion_materiales":
            grant("ver", "crear", "editar")
    elif role == "comprador":
        if module == "licitaciones":
            grant(*all_actions)
        elif module == "contratos":
            grant("ver", "crear", "editar", "eliminar")
        elif module == "conciliacion_facturas":
            grant("ver", "crear", "editar")
        elif module == "recepcion_materiales":
            grant("ver")
    elif role == "almacenista" and module == "recepcion_materiales":
        grant("ver", "crear", "editar")
    elif role == "ceo" and module == "dashboard_ejecutivo":
        grant("ver")
    elif role == "costos" and module in {
        "avance_obra",
        "licitaciones",
        "contratos",
    }:
        grant("ver")
    return values


def _backfill_phase5_permissions() -> None:
    """Materializa la matriz nueva sin alterar permisos CRUD históricos."""

    bind = op.get_bind()
    users = bind.execute(
        sa.text("SELECT id, rol FROM usuarios")
    ).mappings().all()
    insert = sa.text(
        """
        INSERT INTO permisos
            (usuario_id, modulo, puede_ver, puede_crear, puede_editar,
             puede_eliminar, puede_aprobar)
        VALUES
            (:usuario_id, :modulo, :puede_ver, :puede_crear, :puede_editar,
             :puede_eliminar, :puede_aprobar)
        """
    )
    update_approve = sa.text(
        """
        UPDATE permisos
        SET puede_aprobar = :puede_aprobar
        WHERE usuario_id = :usuario_id AND modulo = :modulo
        """
    )
    exists_query = sa.text(
        """
        SELECT 1 FROM permisos
        WHERE usuario_id = :usuario_id AND modulo = :modulo
        """
    )
    approval_defaults = {
        "admin": {
            "nomina",
            "compras",
            "requisiciones",
            "oc_operaciones",
            "proveedores",
            "reportes",
            "usuarios",
            "centros_costo",
            "tarjetas_credito",
            "seguridad",
        },
        "admin_financiero": {"nomina", "tarjetas_credito"},
        "comprador": {"compras", "requisiciones", "proveedores", "reportes"},
        "costos": {"reportes"},
    }
    for user in users:
        role = user["rol"]
        for module in PHASE5_MODULES:
            if bind.execute(
                exists_query,
                {"usuario_id": user["id"], "modulo": module},
            ).first():
                continue
            defaults = _role_defaults(role, module)
            bind.execute(
                insert,
                {
                    "usuario_id": user["id"],
                    "modulo": module,
                    "puede_ver": defaults["ver"],
                    "puede_crear": defaults["crear"],
                    "puede_editar": defaults["editar"],
                    "puede_eliminar": defaults["eliminar"],
                    "puede_aprobar": defaults["aprobar"],
                },
            )
        for module in approval_defaults.get(role, set()):
            bind.execute(
                update_approve,
                {
                    "usuario_id": user["id"],
                    "modulo": module,
                    "puede_aprobar": True,
                },
            )


def upgrade():
    _set_sqlite_foreign_keys(False)
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_constraint("ck_usuarios_rol", type_="check")
        batch_op.create_check_constraint(
            "ck_usuarios_rol",
            "rol IN ('admin','admin_financiero','capturista','supervisor',"
            "'comprador','almacenista','ceo','costos')",
        )

    op.create_table('fase5_alert_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('ncr_por_vencer', sa.Integer(), server_default='0', nullable=False),
    sa.Column('certificaciones_pendientes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('licitaciones_sin_adjudicar', sa.Integer(), server_default='0', nullable=False),
    sa.Column('executed_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('fase5_alert_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_fase5_alert_runs_fecha'), ['fecha'], unique=True)

    op.create_table('avances_partidas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('partida_id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('cantidad_ejecutada', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unidad', sa.String(length=20), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('observaciones', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('cantidad_ejecutada > 0', name='ck_avance_partida_cantidad'),
    sa.ForeignKeyConstraint(['partida_id'], ['budget_items.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('avances_partidas', schema=None) as batch_op:
        batch_op.create_index('ix_avance_partida_partida_fecha', ['partida_id', 'fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_avances_partidas_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_avances_partidas_partida_id'), ['partida_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_avances_partidas_usuario_id'), ['usuario_id'], unique=False)

    op.create_table('no_conformidades',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('centro_costo_id', sa.Integer(), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=False),
    sa.Column('ubicacion', sa.String(length=240), nullable=False),
    sa.Column('severidad', sa.String(length=12), nullable=False),
    sa.Column('responsable', sa.String(length=180), nullable=False),
    sa.Column('fecha_deteccion', sa.Date(), nullable=False),
    sa.Column('fecha_limite', sa.Date(), nullable=False),
    sa.Column('fecha_cierre', sa.Date(), nullable=True),
    sa.Column('estado', sa.String(length=15), server_default='abierta', nullable=False),
    sa.Column('usuario_reporta_id', sa.Integer(), nullable=False),
    sa.Column('usuario_resuelve_id', sa.Integer(), nullable=True),
    sa.Column('evidencia_foto', sa.String(length=500), nullable=True),
    sa.Column('accion_correctiva', sa.Text(), nullable=True),
    sa.Column('evidencia_cierre', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("estado IN ('abierta','en_proceso','cerrada')", name='ck_no_conformidad_estado'),
    sa.CheckConstraint("severidad IN ('leve','moderada','grave')", name='ck_no_conformidad_severidad'),
    sa.CheckConstraint('fecha_limite >= fecha_deteccion', name='ck_no_conformidad_fechas'),
    sa.ForeignKeyConstraint(['centro_costo_id'], ['centros_costo.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['usuario_reporta_id'], ['usuarios.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['usuario_resuelve_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('no_conformidades', schema=None) as batch_op:
        batch_op.create_index('ix_no_conformidad_obra_estado_limite', ['centro_costo_id', 'estado', 'fecha_limite'], unique=False)
        batch_op.create_index(batch_op.f('ix_no_conformidades_centro_costo_id'), ['centro_costo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_no_conformidades_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_no_conformidades_fecha_deteccion'), ['fecha_deteccion'], unique=False)
        batch_op.create_index(batch_op.f('ix_no_conformidades_fecha_limite'), ['fecha_limite'], unique=False)
        batch_op.create_index(batch_op.f('ix_no_conformidades_severidad'), ['severidad'], unique=False)

    op.create_table('partes_diarios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('centro_costo_id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('personal_total', sa.Integer(), server_default='0', nullable=False),
    sa.Column('horas_trabajadas', sa.Numeric(precision=10, scale=2), server_default='0', nullable=False),
    sa.Column('equipos_utilizados', sa.Text(), nullable=True),
    sa.Column('condiciones_meteorologicas', sa.String(length=240), nullable=True),
    sa.Column('visitas', sa.Text(), nullable=True),
    sa.Column('incidencias', sa.Text(), nullable=True),
    sa.Column('observaciones', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('horas_trabajadas >= 0', name='ck_parte_diario_horas'),
    sa.CheckConstraint('personal_total >= 0', name='ck_parte_diario_personal'),
    sa.ForeignKeyConstraint(['centro_costo_id'], ['centros_costo.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('centro_costo_id', 'fecha', name='uq_parte_diario_obra_fecha')
    )
    with op.batch_alter_table('partes_diarios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_partes_diarios_centro_costo_id'), ['centro_costo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_partes_diarios_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_partes_diarios_usuario_id'), ['usuario_id'], unique=False)

    op.create_table('permisos_trabajo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('centro_costo_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('fecha_inicio', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fecha_fin', sa.DateTime(timezone=True), nullable=False),
    sa.Column('supervisor_aprueba_id', sa.Integer(), nullable=True),
    sa.Column('estado', sa.String(length=12), server_default='pendiente', nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=True),
    sa.Column('ubicacion', sa.String(length=240), nullable=True),
    sa.Column('solicitado_por_id', sa.Integer(), nullable=False),
    sa.Column('fecha_aprobacion', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("estado IN ('pendiente','aprobado','cerrado')", name='ck_permiso_trabajo_estado'),
    sa.CheckConstraint("tipo IN ('caliente','altura','excavacion','electrico','espacio_confinado')", name='ck_permiso_trabajo_tipo'),
    sa.CheckConstraint('fecha_fin > fecha_inicio', name='ck_permiso_trabajo_fechas'),
    sa.ForeignKeyConstraint(['centro_costo_id'], ['centros_costo.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['solicitado_por_id'], ['usuarios.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['supervisor_aprueba_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('permisos_trabajo', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_permisos_trabajo_centro_costo_id'), ['centro_costo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_permisos_trabajo_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_permisos_trabajo_fecha_inicio'), ['fecha_inicio'], unique=False)
        batch_op.create_index(batch_op.f('ix_permisos_trabajo_tipo'), ['tipo'], unique=False)

    op.create_table('reportes_hse',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('centro_costo_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=22), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=False),
    sa.Column('ubicacion', sa.String(length=240), nullable=False),
    sa.Column('usuario_reporta_id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('acciones', sa.Text(), nullable=True),
    sa.Column('estado', sa.String(length=15), server_default='abierta', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("estado IN ('abierta','en_proceso','cerrada')", name='ck_reporte_hse_estado'),
    sa.CheckConstraint("tipo IN ('acto_inseguro','condicion_insegura','observacion')", name='ck_reporte_hse_tipo'),
    sa.ForeignKeyConstraint(['centro_costo_id'], ['centros_costo.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['usuario_reporta_id'], ['usuarios.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('reportes_hse', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reportes_hse_centro_costo_id'), ['centro_costo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_reportes_hse_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_reportes_hse_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_reportes_hse_tipo'), ['tipo'], unique=False)

    op.create_table('rfis',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('centro_costo_id', sa.Integer(), nullable=False),
    sa.Column('asunto', sa.String(length=240), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=False),
    sa.Column('estado', sa.String(length=12), server_default='abierta', nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('fecha_respuesta', sa.DateTime(timezone=True), nullable=True),
    sa.Column('usuario_solicita_id', sa.Integer(), nullable=False),
    sa.Column('usuario_responde_id', sa.Integer(), nullable=True),
    sa.Column('destinatario_id', sa.Integer(), nullable=True),
    sa.Column('respuesta', sa.Text(), nullable=True),
    sa.Column('archivo_adjunto', sa.String(length=500), nullable=True),
    sa.Column('archivo_respuesta', sa.String(length=500), nullable=True),
    sa.CheckConstraint("estado IN ('abierta','respondida','cerrada')", name='ck_rfi_estado'),
    sa.ForeignKeyConstraint(['centro_costo_id'], ['centros_costo.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['destinatario_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['usuario_responde_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['usuario_solicita_id'], ['usuarios.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('rfis', schema=None) as batch_op:
        batch_op.create_index('ix_rfi_obra_estado', ['centro_costo_id', 'estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_rfis_centro_costo_id'), ['centro_costo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_rfis_destinatario_id'), ['destinatario_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_rfis_estado'), ['estado'], unique=False)

    op.create_table('licitaciones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('requisicion_id', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=12), server_default='preparacion', nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('fecha_limite', sa.Date(), nullable=False),
    sa.Column('creado_por_id', sa.Integer(), nullable=False),
    sa.Column('adjudicada_por_id', sa.Integer(), nullable=True),
    sa.Column('fecha_adjudicacion', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("estado IN ('preparacion','enviada','cerrada')", name='ck_licitacion_estado'),
    sa.ForeignKeyConstraint(['adjudicada_por_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['requisicion_id'], ['purchase_requisitions.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('licitaciones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_licitaciones_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_licitaciones_fecha_limite'), ['fecha_limite'], unique=False)
        batch_op.create_index(batch_op.f('ix_licitaciones_requisicion_id'), ['requisicion_id'], unique=False)

    op.create_table('rfi_eventos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rfi_id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('accion', sa.String(length=40), nullable=False),
    sa.Column('detalle', sa.Text(), nullable=True),
    sa.Column('archivo_adjunto', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['rfi_id'], ['rfis.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('rfi_eventos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_rfi_eventos_rfi_id'), ['rfi_id'], unique=False)

    op.create_table('solicitudes_pago_subcontrato',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('subcontrato_id', sa.Integer(), nullable=False),
    sa.Column('fecha_solicitud', sa.Date(), nullable=False),
    sa.Column('monto_solicitado', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('concepto', sa.String(length=240), nullable=False),
    sa.Column('archivo_adjunto', sa.String(length=500), nullable=True),
    sa.Column('estado', sa.String(length=20), server_default='pendiente', nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("estado IN ('pendiente','certificada','rechazada')", name='ck_solicitud_subcontrato_estado'),
    sa.CheckConstraint('monto_solicitado > 0', name='ck_solicitud_subcontrato_monto'),
    sa.ForeignKeyConstraint(['subcontrato_id'], ['subcontracts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('solicitudes_pago_subcontrato', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_solicitudes_pago_subcontrato_fecha_solicitud'), ['fecha_solicitud'], unique=False)
        batch_op.create_index(batch_op.f('ix_solicitudes_pago_subcontrato_subcontrato_id'), ['subcontrato_id'], unique=False)

    op.create_table('certificaciones_subcontratos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('subcontrato_id', sa.Integer(), nullable=False),
    sa.Column('solicitud_pago_id', sa.Integer(), nullable=False),
    sa.Column('monto_solicitado', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('monto_aprobado', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('estado', sa.String(length=15), server_default='pendiente', nullable=False),
    sa.Column('supervisor_id', sa.Integer(), nullable=True),
    sa.Column('fecha_aprobacion', sa.DateTime(timezone=True), nullable=True),
    sa.Column('comentario', sa.Text(), nullable=True),
    sa.Column('pago_generado_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("estado IN ('pendiente','aprobada','rechazada')", name='ck_certificacion_estado'),
    sa.CheckConstraint('monto_aprobado IS NULL OR monto_aprobado >= 0', name='ck_certificacion_monto_aprobado'),
    sa.CheckConstraint('monto_solicitado > 0', name='ck_certificacion_monto_solicitado'),
    sa.ForeignKeyConstraint(['pago_generado_id'], ['subcontract_payments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['solicitud_pago_id'], ['solicitudes_pago_subcontrato.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subcontrato_id'], ['subcontracts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['supervisor_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('pago_generado_id'),
    sa.UniqueConstraint('solicitud_pago_id')
    )
    with op.batch_alter_table('certificaciones_subcontratos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_certificaciones_subcontratos_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_certificaciones_subcontratos_subcontrato_id'), ['subcontrato_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_certificaciones_subcontratos_supervisor_id'), ['supervisor_id'], unique=False)

    op.create_table('licitacion_proveedores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('licitacion_id', sa.Integer(), nullable=False),
    sa.Column('proveedor_id', sa.Integer(), nullable=False),
    sa.Column('fecha_envio', sa.DateTime(timezone=True), nullable=True),
    sa.Column('fecha_respuesta', sa.DateTime(timezone=True), nullable=True),
    sa.Column('estado', sa.String(length=15), server_default='invitado', nullable=False),
    sa.Column('error_envio', sa.String(length=500), nullable=True),
    sa.CheckConstraint("estado IN ('invitado','enviado','respondido','declinado')", name='ck_licitacion_proveedor_estado'),
    sa.ForeignKeyConstraint(['licitacion_id'], ['licitaciones.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['proveedor_id'], ['suppliers.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('licitacion_id', 'proveedor_id', name='uq_licitacion_proveedor')
    )
    with op.batch_alter_table('licitacion_proveedores', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_licitacion_proveedores_licitacion_id'), ['licitacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_licitacion_proveedores_proveedor_id'), ['proveedor_id'], unique=False)

    op.create_table('ofertas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('licitacion_id', sa.Integer(), nullable=False),
    sa.Column('proveedor_id', sa.Integer(), nullable=False),
    sa.Column('monto_total', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('plazo_entrega', sa.Integer(), nullable=False),
    sa.Column('condiciones', sa.Text(), nullable=True),
    sa.Column('archivo_adjunto', sa.String(length=500), nullable=True),
    sa.Column('estado', sa.String(length=12), server_default='recibida', nullable=False),
    sa.Column('fecha_recepcion', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('adjudicada_por_id', sa.Integer(), nullable=True),
    sa.Column('fecha_adjudicacion', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resultado_tipo', sa.String(length=15), nullable=True),
    sa.Column('resultado_id', sa.Integer(), nullable=True),
    sa.CheckConstraint("estado IN ('recibida','evaluada','adjudicada','rechazada')", name='ck_oferta_estado'),
    sa.CheckConstraint("resultado_tipo IS NULL OR resultado_tipo IN ('orden_compra','contrato')", name='ck_oferta_resultado_tipo'),
    sa.CheckConstraint('monto_total > 0', name='ck_oferta_monto'),
    sa.CheckConstraint('plazo_entrega >= 0', name='ck_oferta_plazo'),
    sa.ForeignKeyConstraint(['adjudicada_por_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['licitacion_id'], ['licitaciones.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['proveedor_id'], ['suppliers.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('licitacion_id', 'proveedor_id', name='uq_oferta_licitacion_proveedor')
    )
    with op.batch_alter_table('ofertas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ofertas_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_ofertas_licitacion_id'), ['licitacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ofertas_proveedor_id'), ['proveedor_id'], unique=False)

    op.create_table('conciliaciones_facturas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('orden_compra_id', sa.Integer(), nullable=False),
    sa.Column('factura_numero', sa.String(length=80), nullable=False),
    sa.Column('fecha_factura', sa.Date(), nullable=False),
    sa.Column('monto_factura', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('monto_pedido', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('monto_recibido', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('monto_pagado', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('estado', sa.String(length=12), server_default='pendiente', nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('fecha_conciliacion', sa.DateTime(timezone=True), nullable=True),
    sa.Column('motivo_diferencia', sa.Text(), nullable=True),
    sa.Column('aprobador_id', sa.Integer(), nullable=True),
    sa.Column('fecha_aprobacion', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("estado IN ('pendiente','aprobada','rechazada','pagada')", name='ck_conciliacion_estado'),
    sa.CheckConstraint('monto_factura >= 0 AND monto_pedido >= 0 AND monto_recibido >= 0 AND monto_pagado >= 0', name='ck_conciliacion_montos'),
    sa.ForeignKeyConstraint(['aprobador_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['orden_compra_id'], ['purchase_orders.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('orden_compra_id', 'factura_numero', name='uq_conciliacion_orden_factura')
    )
    with op.batch_alter_table('conciliaciones_facturas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_conciliaciones_facturas_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_conciliaciones_facturas_orden_compra_id'), ['orden_compra_id'], unique=False)

    op.create_table('contratos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('proveedor_id', sa.Integer(), nullable=False),
    sa.Column('centro_costo_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('monto_total', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('fecha_inicio', sa.Date(), nullable=False),
    sa.Column('fecha_fin', sa.Date(), nullable=False),
    sa.Column('estado', sa.String(length=12), server_default='borrador', nullable=False),
    sa.Column('condiciones_pago', sa.Text(), nullable=False),
    sa.Column('retencion_garantia', sa.Numeric(precision=5, scale=2), server_default='0', nullable=False),
    sa.Column('hitos', sa.JSON(), server_default='[]', nullable=False),
    sa.Column('licitacion_id', sa.Integer(), nullable=True),
    sa.Column('oferta_id', sa.Integer(), nullable=True),
    sa.Column('creado_por_id', sa.Integer(), nullable=False),
    sa.Column('version_actual', sa.Integer(), server_default='1', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("estado IN ('borrador','activo','suspendido','finalizado')", name='ck_contrato_estado'),
    sa.CheckConstraint("tipo IN ('precio_unitario','suma_alzada','mixto')", name='ck_contrato_tipo'),
    sa.CheckConstraint('fecha_fin >= fecha_inicio', name='ck_contrato_fechas'),
    sa.CheckConstraint('monto_total >= 0', name='ck_contrato_monto'),
    sa.CheckConstraint('retencion_garantia >= 0 AND retencion_garantia <= 100', name='ck_contrato_retencion'),
    sa.ForeignKeyConstraint(['centro_costo_id'], ['centros_costo.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['licitacion_id'], ['licitaciones.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['oferta_id'], ['ofertas.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['proveedor_id'], ['suppliers.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('contratos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_contratos_centro_costo_id'), ['centro_costo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_contratos_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_contratos_proveedor_id'), ['proveedor_id'], unique=False)

    op.create_table('contrato_modificaciones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('contrato_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=False),
    sa.Column('monto_original', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('monto_nuevo', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=12), server_default='pendiente', nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('fecha_fin_nueva', sa.Date(), nullable=True),
    sa.Column('aprobador_id', sa.Integer(), nullable=True),
    sa.Column('fecha_aprobacion', sa.DateTime(timezone=True), nullable=True),
    sa.Column('comentario_aprobacion', sa.Text(), nullable=True),
    sa.CheckConstraint("estado IN ('pendiente','aprobada','rechazada')", name='ck_contrato_modificacion_estado'),
    sa.CheckConstraint("tipo IN ('alcance','precio','plazo')", name='ck_contrato_modificacion_tipo'),
    sa.ForeignKeyConstraint(['aprobador_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['contrato_id'], ['contratos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('contrato_id', 'version', name='uq_contrato_modificacion_version')
    )
    with op.batch_alter_table('contrato_modificaciones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_contrato_modificaciones_contrato_id'), ['contrato_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_contrato_modificaciones_estado'), ['estado'], unique=False)

    op.create_table('discrepancias_recepcion',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('orden_compra_id', sa.Integer(), nullable=False),
    sa.Column('orden_linea_id', sa.Integer(), nullable=False),
    sa.Column('recepcion_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('cantidad', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('descripcion', sa.String(length=500), nullable=False),
    sa.Column('estado', sa.String(length=10), server_default='abierta', nullable=False),
    sa.Column('usuario_reporta_id', sa.Integer(), nullable=False),
    sa.Column('fecha_reporte', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('usuario_resuelve_id', sa.Integer(), nullable=True),
    sa.Column('fecha_resolucion', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolucion', sa.Text(), nullable=True),
    sa.CheckConstraint("estado IN ('abierta','resuelta')", name='ck_discrepancia_estado'),
    sa.CheckConstraint("tipo IN ('rechazado','faltante')", name='ck_discrepancia_tipo'),
    sa.CheckConstraint('cantidad > 0', name='ck_discrepancia_cantidad'),
    sa.ForeignKeyConstraint(['orden_compra_id'], ['purchase_orders.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['orden_linea_id'], ['purchase_order_lines.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recepcion_id'], ['goods_receipts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['usuario_reporta_id'], ['usuarios.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['usuario_resuelve_id'], ['usuarios.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('discrepancias_recepcion', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_discrepancias_recepcion_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_discrepancias_recepcion_orden_compra_id'), ['orden_compra_id'], unique=False)

    with op.batch_alter_table('budget_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cantidad_objetivo', sa.Numeric(precision=16, scale=4), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('unidad_medida', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('porcentaje_avance_real', sa.Numeric(precision=6, scale=2), server_default='0', nullable=False))
        batch_op.create_check_constraint(
            "ck_budget_item_target_quantity", "cantidad_objetivo >= 0"
        )
        batch_op.create_check_constraint(
            "ck_budget_item_progress",
            "porcentaje_avance_real >= 0 AND porcentaje_avance_real <= 100",
        )

    with op.batch_alter_table('permisos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('puede_aprobar', sa.Boolean(), server_default='0', nullable=False))
    _backfill_phase5_permissions()

    with op.batch_alter_table('purchase_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('requiere_conciliacion', sa.Boolean(), server_default='0', nullable=False))
        batch_op.create_index(batch_op.f('ix_purchase_orders_requiere_conciliacion'), ['requiere_conciliacion'], unique=False)

    _set_sqlite_foreign_keys(True)


def downgrade():
    _set_sqlite_foreign_keys(False)
    with op.batch_alter_table('purchase_orders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_purchase_orders_requiere_conciliacion'))
        batch_op.drop_column('requiere_conciliacion')

    phase5_modules_sql = ", ".join(
        f"'{module}'" for module in PHASE5_MODULES
    )
    op.execute(
        sa.text(
            f"DELETE FROM permisos WHERE modulo IN ({phase5_modules_sql})"
        )
    )

    with op.batch_alter_table('permisos', schema=None) as batch_op:
        batch_op.drop_column('puede_aprobar')

    with op.batch_alter_table('budget_items', schema=None) as batch_op:
        batch_op.drop_constraint("ck_budget_item_progress", type_="check")
        batch_op.drop_constraint(
            "ck_budget_item_target_quantity", type_="check"
        )
        batch_op.drop_column('porcentaje_avance_real')
        batch_op.drop_column('unidad_medida')
        batch_op.drop_column('cantidad_objetivo')

    with op.batch_alter_table('discrepancias_recepcion', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_discrepancias_recepcion_orden_compra_id'))
        batch_op.drop_index(batch_op.f('ix_discrepancias_recepcion_estado'))

    op.drop_table('discrepancias_recepcion')
    with op.batch_alter_table('contrato_modificaciones', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_contrato_modificaciones_estado'))
        batch_op.drop_index(batch_op.f('ix_contrato_modificaciones_contrato_id'))

    op.drop_table('contrato_modificaciones')
    with op.batch_alter_table('contratos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_contratos_proveedor_id'))
        batch_op.drop_index(batch_op.f('ix_contratos_estado'))
        batch_op.drop_index(batch_op.f('ix_contratos_centro_costo_id'))

    op.drop_table('contratos')
    with op.batch_alter_table('conciliaciones_facturas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_conciliaciones_facturas_orden_compra_id'))
        batch_op.drop_index(batch_op.f('ix_conciliaciones_facturas_estado'))

    op.drop_table('conciliaciones_facturas')
    with op.batch_alter_table('ofertas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ofertas_proveedor_id'))
        batch_op.drop_index(batch_op.f('ix_ofertas_licitacion_id'))
        batch_op.drop_index(batch_op.f('ix_ofertas_estado'))

    op.drop_table('ofertas')
    with op.batch_alter_table('licitacion_proveedores', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_licitacion_proveedores_proveedor_id'))
        batch_op.drop_index(batch_op.f('ix_licitacion_proveedores_licitacion_id'))

    op.drop_table('licitacion_proveedores')
    with op.batch_alter_table('certificaciones_subcontratos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_certificaciones_subcontratos_supervisor_id'))
        batch_op.drop_index(batch_op.f('ix_certificaciones_subcontratos_subcontrato_id'))
        batch_op.drop_index(batch_op.f('ix_certificaciones_subcontratos_estado'))

    op.drop_table('certificaciones_subcontratos')
    with op.batch_alter_table('solicitudes_pago_subcontrato', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_solicitudes_pago_subcontrato_subcontrato_id'))
        batch_op.drop_index(batch_op.f('ix_solicitudes_pago_subcontrato_fecha_solicitud'))

    op.drop_table('solicitudes_pago_subcontrato')
    with op.batch_alter_table('rfi_eventos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rfi_eventos_rfi_id'))

    op.drop_table('rfi_eventos')
    with op.batch_alter_table('licitaciones', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_licitaciones_requisicion_id'))
        batch_op.drop_index(batch_op.f('ix_licitaciones_fecha_limite'))
        batch_op.drop_index(batch_op.f('ix_licitaciones_estado'))

    op.drop_table('licitaciones')
    with op.batch_alter_table('rfis', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rfis_estado'))
        batch_op.drop_index(batch_op.f('ix_rfis_destinatario_id'))
        batch_op.drop_index(batch_op.f('ix_rfis_centro_costo_id'))
        batch_op.drop_index('ix_rfi_obra_estado')

    op.drop_table('rfis')
    with op.batch_alter_table('reportes_hse', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reportes_hse_tipo'))
        batch_op.drop_index(batch_op.f('ix_reportes_hse_fecha'))
        batch_op.drop_index(batch_op.f('ix_reportes_hse_estado'))
        batch_op.drop_index(batch_op.f('ix_reportes_hse_centro_costo_id'))

    op.drop_table('reportes_hse')
    with op.batch_alter_table('permisos_trabajo', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_permisos_trabajo_tipo'))
        batch_op.drop_index(batch_op.f('ix_permisos_trabajo_fecha_inicio'))
        batch_op.drop_index(batch_op.f('ix_permisos_trabajo_estado'))
        batch_op.drop_index(batch_op.f('ix_permisos_trabajo_centro_costo_id'))

    op.drop_table('permisos_trabajo')
    with op.batch_alter_table('partes_diarios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_partes_diarios_usuario_id'))
        batch_op.drop_index(batch_op.f('ix_partes_diarios_fecha'))
        batch_op.drop_index(batch_op.f('ix_partes_diarios_centro_costo_id'))

    op.drop_table('partes_diarios')
    with op.batch_alter_table('no_conformidades', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_no_conformidades_severidad'))
        batch_op.drop_index(batch_op.f('ix_no_conformidades_fecha_limite'))
        batch_op.drop_index(batch_op.f('ix_no_conformidades_fecha_deteccion'))
        batch_op.drop_index(batch_op.f('ix_no_conformidades_estado'))
        batch_op.drop_index(batch_op.f('ix_no_conformidades_centro_costo_id'))
        batch_op.drop_index('ix_no_conformidad_obra_estado_limite')

    op.drop_table('no_conformidades')
    with op.batch_alter_table('avances_partidas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_avances_partidas_usuario_id'))
        batch_op.drop_index(batch_op.f('ix_avances_partidas_partida_id'))
        batch_op.drop_index(batch_op.f('ix_avances_partidas_fecha'))
        batch_op.drop_index('ix_avance_partida_partida_fecha')

    op.drop_table('avances_partidas')
    with op.batch_alter_table('fase5_alert_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_fase5_alert_runs_fecha'))

    op.drop_table('fase5_alert_runs')
    op.execute(
        sa.text(
            "UPDATE usuarios SET rol = 'capturista' "
            "WHERE rol IN ('almacenista', 'ceo')"
        )
    )
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_constraint("ck_usuarios_rol", type_="check")
        batch_op.create_check_constraint(
            "ck_usuarios_rol",
            "rol IN ('admin','admin_financiero','capturista','supervisor',"
            "'comprador','costos')",
        )
    _set_sqlite_foreign_keys(True)
