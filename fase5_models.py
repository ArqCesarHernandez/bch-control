"""Modelos de la Fase 5: campo, abastecimiento, contratos y Dirección.

Los nombres de tabla se mantienen en español porque corresponden a conceptos
operativos de BCH Control. Las relaciones hacia Nóminas y Compras se declaran
por nombre para evitar ciclos de importación entre módulos.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, UniqueConstraint, func

from models import db, utc_now


class ParteDiario(db.Model):
    __tablename__ = "partes_diarios"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    centro_costo_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    fecha = db.Column(db.Date, nullable=False, index=True)
    personal_total = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    horas_trabajadas = db.Column(
        db.Numeric(10, 2), nullable=False, default=0, server_default="0"
    )
    equipos_utilizados = db.Column(db.Text)
    condiciones_meteorologicas = db.Column(db.String(240))
    visitas = db.Column(db.Text)
    incidencias = db.Column(db.Text)
    observaciones = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now,
        server_default=func.now()
    )

    usuario = db.relationship("Usuario")
    centro_costo = db.relationship("CentroCosto")

    __table_args__ = (
        UniqueConstraint(
            "centro_costo_id", "fecha", name="uq_parte_diario_obra_fecha"
        ),
        CheckConstraint("personal_total >= 0", name="ck_parte_diario_personal"),
        CheckConstraint("horas_trabajadas >= 0", name="ck_parte_diario_horas"),
    )


class AvancePartida(db.Model):
    __tablename__ = "avances_partidas"

    id = db.Column(db.Integer, primary_key=True)
    partida_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fecha = db.Column(db.Date, nullable=False, index=True)
    cantidad_ejecutada = db.Column(db.Numeric(16, 4), nullable=False)
    unidad = db.Column(db.String(20), nullable=False)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    observaciones = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now,
        server_default=func.now()
    )

    partida = db.relationship("BudgetItem", backref="avances_reales")
    usuario = db.relationship("Usuario")

    __table_args__ = (
        CheckConstraint(
            "cantidad_ejecutada > 0", name="ck_avance_partida_cantidad"
        ),
        Index("ix_avance_partida_partida_fecha", "partida_id", "fecha"),
    )


class SolicitudPagoSubcontrato(db.Model):
    """Pay application capturada por BCH en representación del subcontratista."""

    __tablename__ = "solicitudes_pago_subcontrato"

    id = db.Column(db.Integer, primary_key=True)
    subcontrato_id = db.Column(
        db.Integer,
        db.ForeignKey("subcontracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fecha_solicitud = db.Column(db.Date, nullable=False, index=True)
    monto_solicitado = db.Column(db.Numeric(14, 2), nullable=False)
    concepto = db.Column(db.String(240), nullable=False)
    archivo_adjunto = db.Column(db.String(500))
    estado = db.Column(
        db.String(20), nullable=False, default="pendiente", server_default="pendiente"
    )
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    subcontrato = db.relationship("Subcontract")
    usuario = db.relationship("Usuario")

    __table_args__ = (
        CheckConstraint(
            "monto_solicitado > 0", name="ck_solicitud_subcontrato_monto"
        ),
        CheckConstraint(
            "estado IN ('pendiente','certificada','rechazada')",
            name="ck_solicitud_subcontrato_estado",
        ),
    )


class CertificacionSubcontrato(db.Model):
    __tablename__ = "certificaciones_subcontratos"

    id = db.Column(db.Integer, primary_key=True)
    subcontrato_id = db.Column(
        db.Integer,
        db.ForeignKey("subcontracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    solicitud_pago_id = db.Column(
        db.Integer,
        db.ForeignKey("solicitudes_pago_subcontrato.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    monto_solicitado = db.Column(db.Numeric(14, 2), nullable=False)
    monto_aprobado = db.Column(db.Numeric(14, 2))
    estado = db.Column(
        db.String(15), nullable=False, default="pendiente", server_default="pendiente",
        index=True
    )
    supervisor_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
        index=True,
    )
    fecha_aprobacion = db.Column(db.DateTime(timezone=True))
    comentario = db.Column(db.Text)
    pago_generado_id = db.Column(
        db.Integer,
        db.ForeignKey("subcontract_payments.id", ondelete="SET NULL"),
        unique=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    subcontrato = db.relationship("Subcontract")
    solicitud_pago = db.relationship("SolicitudPagoSubcontrato")
    supervisor = db.relationship("Usuario")
    pago_generado = db.relationship("SubcontractPayment")

    __table_args__ = (
        CheckConstraint(
            "monto_solicitado > 0", name="ck_certificacion_monto_solicitado"
        ),
        CheckConstraint(
            "monto_aprobado IS NULL OR monto_aprobado >= 0",
            name="ck_certificacion_monto_aprobado",
        ),
        CheckConstraint(
            "estado IN ('pendiente','aprobada','rechazada')",
            name="ck_certificacion_estado",
        ),
    )


class NoConformidad(db.Model):
    __tablename__ = "no_conformidades"

    id = db.Column(db.Integer, primary_key=True)
    centro_costo_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    descripcion = db.Column(db.Text, nullable=False)
    ubicacion = db.Column(db.String(240), nullable=False)
    severidad = db.Column(db.String(12), nullable=False, index=True)
    responsable = db.Column(db.String(180), nullable=False)
    fecha_deteccion = db.Column(db.Date, nullable=False, index=True)
    fecha_limite = db.Column(db.Date, nullable=False, index=True)
    fecha_cierre = db.Column(db.Date)
    estado = db.Column(
        db.String(15), nullable=False, default="abierta", server_default="abierta",
        index=True
    )
    usuario_reporta_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    usuario_resuelve_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    evidencia_foto = db.Column(db.String(500))
    accion_correctiva = db.Column(db.Text)
    evidencia_cierre = db.Column(db.String(500))
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now,
        server_default=func.now()
    )

    centro_costo = db.relationship("CentroCosto")
    usuario_reporta = db.relationship("Usuario", foreign_keys=[usuario_reporta_id])
    usuario_resuelve = db.relationship("Usuario", foreign_keys=[usuario_resuelve_id])

    __table_args__ = (
        CheckConstraint(
            "severidad IN ('leve','moderada','grave')",
            name="ck_no_conformidad_severidad",
        ),
        CheckConstraint(
            "estado IN ('abierta','en_proceso','cerrada')",
            name="ck_no_conformidad_estado",
        ),
        CheckConstraint(
            "fecha_limite >= fecha_deteccion", name="ck_no_conformidad_fechas"
        ),
        Index(
            "ix_no_conformidad_obra_estado_limite",
            "centro_costo_id",
            "estado",
            "fecha_limite",
        ),
    )

    def semaforo(self, referencia: date | None = None) -> str:
        if self.estado == "cerrada":
            return "cerrada"
        dias = (self.fecha_limite - (referencia or date.today())).days
        if dias < 0:
            return "vencida"
        if dias <= 2:
            return "rojo"
        if dias <= 7:
            return "amarillo"
        return "verde"


class RFI(db.Model):
    __tablename__ = "rfis"

    id = db.Column(db.Integer, primary_key=True)
    centro_costo_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    asunto = db.Column(db.String(240), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    estado = db.Column(
        db.String(12), nullable=False, default="abierta", server_default="abierta",
        index=True
    )
    fecha_creacion = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    fecha_respuesta = db.Column(db.DateTime(timezone=True))
    usuario_solicita_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    usuario_responde_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    destinatario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
        index=True,
    )
    respuesta = db.Column(db.Text)
    archivo_adjunto = db.Column(db.String(500))
    archivo_respuesta = db.Column(db.String(500))

    centro_costo = db.relationship("CentroCosto")
    usuario_solicita = db.relationship("Usuario", foreign_keys=[usuario_solicita_id])
    usuario_responde = db.relationship("Usuario", foreign_keys=[usuario_responde_id])
    destinatario = db.relationship("Usuario", foreign_keys=[destinatario_id])
    eventos = db.relationship(
        "RFIEvento", back_populates="rfi", cascade="all, delete-orphan",
        order_by="RFIEvento.created_at"
    )

    __table_args__ = (
        CheckConstraint(
            "estado IN ('abierta','respondida','cerrada')", name="ck_rfi_estado"
        ),
        Index("ix_rfi_obra_estado", "centro_costo_id", "estado"),
    )


class RFIEvento(db.Model):
    __tablename__ = "rfi_eventos"

    id = db.Column(db.Integer, primary_key=True)
    rfi_id = db.Column(
        db.Integer,
        db.ForeignKey("rfis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    accion = db.Column(db.String(40), nullable=False)
    detalle = db.Column(db.Text)
    archivo_adjunto = db.Column(db.String(500))
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    rfi = db.relationship("RFI", back_populates="eventos")
    usuario = db.relationship("Usuario")


class ReporteHSE(db.Model):
    __tablename__ = "reportes_hse"

    id = db.Column(db.Integer, primary_key=True)
    centro_costo_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tipo = db.Column(db.String(22), nullable=False, index=True)
    descripcion = db.Column(db.Text, nullable=False)
    ubicacion = db.Column(db.String(240), nullable=False)
    usuario_reporta_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fecha = db.Column(db.Date, nullable=False, index=True)
    acciones = db.Column(db.Text)
    estado = db.Column(
        db.String(15), nullable=False, default="abierta", server_default="abierta",
        index=True
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now,
        server_default=func.now()
    )

    centro_costo = db.relationship("CentroCosto")
    usuario_reporta = db.relationship("Usuario")

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('acto_inseguro','condicion_insegura','observacion')",
            name="ck_reporte_hse_tipo",
        ),
        CheckConstraint(
            "estado IN ('abierta','en_proceso','cerrada')",
            name="ck_reporte_hse_estado",
        ),
    )


class PermisoTrabajo(db.Model):
    __tablename__ = "permisos_trabajo"

    id = db.Column(db.Integer, primary_key=True)
    centro_costo_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tipo = db.Column(db.String(20), nullable=False, index=True)
    fecha_inicio = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    fecha_fin = db.Column(db.DateTime(timezone=True), nullable=False)
    supervisor_aprueba_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    estado = db.Column(
        db.String(12), nullable=False, default="pendiente", server_default="pendiente",
        index=True
    )
    descripcion = db.Column(db.Text)
    ubicacion = db.Column(db.String(240))
    solicitado_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fecha_aprobacion = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    centro_costo = db.relationship("CentroCosto")
    supervisor_aprueba = db.relationship(
        "Usuario", foreign_keys=[supervisor_aprueba_id]
    )
    solicitado_por = db.relationship("Usuario", foreign_keys=[solicitado_por_id])

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('caliente','altura','excavacion','electrico','espacio_confinado')",
            name="ck_permiso_trabajo_tipo",
        ),
        CheckConstraint(
            "estado IN ('pendiente','aprobado','cerrado')",
            name="ck_permiso_trabajo_estado",
        ),
        CheckConstraint("fecha_fin > fecha_inicio", name="ck_permiso_trabajo_fechas"),
    )


class Licitacion(db.Model):
    __tablename__ = "licitaciones"

    id = db.Column(db.Integer, primary_key=True)
    requisicion_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_requisitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    estado = db.Column(
        db.String(12), nullable=False, default="preparacion", server_default="preparacion",
        index=True
    )
    fecha_creacion = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    fecha_limite = db.Column(db.Date, nullable=False, index=True)
    creado_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    adjudicada_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    fecha_adjudicacion = db.Column(db.DateTime(timezone=True))

    requisicion = db.relationship("PurchaseRequisition")
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    adjudicada_por = db.relationship("Usuario", foreign_keys=[adjudicada_por_id])
    proveedores = db.relationship(
        "LicitacionProveedor", back_populates="licitacion", cascade="all, delete-orphan"
    )
    ofertas = db.relationship(
        "Oferta", back_populates="licitacion", cascade="all, delete-orphan"
    )
    lineas = db.relationship(
        "LicitacionLinea",
        back_populates="licitacion",
        cascade="all, delete-orphan",
        order_by="LicitacionLinea.id",
    )

    __table_args__ = (
        CheckConstraint(
            "estado IN ('preparacion','enviada','cerrada')",
            name="ck_licitacion_estado",
        ),
    )

    @property
    def oferta_ganadora(self):
        return next((oferta for oferta in self.ofertas if oferta.estado == "adjudicada"), None)


class LicitacionLinea(db.Model):
    """Renglones liberados automáticamente desde una requisición mixta."""

    __tablename__ = "licitacion_lineas"

    id = db.Column(db.Integer, primary_key=True)
    licitacion_id = db.Column(
        db.Integer,
        db.ForeignKey("licitaciones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requisicion_linea_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_requisition_lines.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    fecha_liberacion = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    licitacion = db.relationship("Licitacion", back_populates="lineas")
    requisicion_linea = db.relationship("PurchaseRequisitionLine")

    __table_args__ = (
        UniqueConstraint(
            "licitacion_id",
            "requisicion_linea_id",
            name="uq_licitacion_requisicion_linea",
        ),
    )


class LicitacionProveedor(db.Model):
    __tablename__ = "licitacion_proveedores"

    id = db.Column(db.Integer, primary_key=True)
    licitacion_id = db.Column(
        db.Integer,
        db.ForeignKey("licitaciones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proveedor_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    fecha_envio = db.Column(db.DateTime(timezone=True))
    fecha_respuesta = db.Column(db.DateTime(timezone=True))
    estado = db.Column(
        db.String(15), nullable=False, default="invitado", server_default="invitado"
    )
    error_envio = db.Column(db.String(500))

    licitacion = db.relationship("Licitacion", back_populates="proveedores")
    proveedor = db.relationship("Supplier")

    __table_args__ = (
        UniqueConstraint(
            "licitacion_id", "proveedor_id", name="uq_licitacion_proveedor"
        ),
        CheckConstraint(
            "estado IN ('invitado','enviado','respondido','declinado')",
            name="ck_licitacion_proveedor_estado",
        ),
    )


class Oferta(db.Model):
    __tablename__ = "ofertas"

    id = db.Column(db.Integer, primary_key=True)
    licitacion_id = db.Column(
        db.Integer,
        db.ForeignKey("licitaciones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proveedor_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    monto_total = db.Column(db.Numeric(14, 2), nullable=False)
    plazo_entrega = db.Column(db.Integer, nullable=False)
    condiciones = db.Column(db.Text)
    archivo_adjunto = db.Column(db.String(500))
    estado = db.Column(
        db.String(12), nullable=False, default="recibida", server_default="recibida",
        index=True
    )
    fecha_recepcion = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    adjudicada_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    fecha_adjudicacion = db.Column(db.DateTime(timezone=True))
    resultado_tipo = db.Column(db.String(15))
    resultado_id = db.Column(db.Integer)

    licitacion = db.relationship("Licitacion", back_populates="ofertas")
    proveedor = db.relationship("Supplier")
    adjudicada_por = db.relationship("Usuario")

    __table_args__ = (
        UniqueConstraint(
            "licitacion_id", "proveedor_id", name="uq_oferta_licitacion_proveedor"
        ),
        CheckConstraint("monto_total > 0", name="ck_oferta_monto"),
        CheckConstraint("plazo_entrega >= 0", name="ck_oferta_plazo"),
        CheckConstraint(
            "estado IN ('recibida','evaluada','adjudicada','rechazada')",
            name="ck_oferta_estado",
        ),
        CheckConstraint(
            "resultado_tipo IS NULL OR resultado_tipo IN ('orden_compra','contrato')",
            name="ck_oferta_resultado_tipo",
        ),
    )


class Contrato(db.Model):
    __tablename__ = "contratos"

    id = db.Column(db.Integer, primary_key=True)
    proveedor_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    centro_costo_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tipo = db.Column(db.String(20), nullable=False)
    monto_total = db.Column(db.Numeric(14, 2), nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    estado = db.Column(
        db.String(12), nullable=False, default="borrador", server_default="borrador",
        index=True
    )
    condiciones_pago = db.Column(db.Text, nullable=False)
    retencion_garantia = db.Column(
        db.Numeric(5, 2), nullable=False, default=0, server_default="0"
    )
    hitos = db.Column(db.JSON, nullable=False, default=list, server_default="[]")
    licitacion_id = db.Column(
        db.Integer,
        db.ForeignKey("licitaciones.id", ondelete="SET NULL"),
    )
    oferta_id = db.Column(
        db.Integer,
        db.ForeignKey("ofertas.id", ondelete="SET NULL"),
    )
    creado_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_actual = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now,
        server_default=func.now()
    )

    proveedor = db.relationship("Supplier")
    centro_costo = db.relationship("CentroCosto")
    licitacion = db.relationship("Licitacion")
    oferta = db.relationship("Oferta")
    creado_por = db.relationship("Usuario")
    modificaciones = db.relationship(
        "ContratoModificacion", back_populates="contrato",
        cascade="all, delete-orphan", order_by="ContratoModificacion.version"
    )

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('precio_unitario','suma_alzada','mixto')",
            name="ck_contrato_tipo",
        ),
        CheckConstraint("monto_total >= 0", name="ck_contrato_monto"),
        CheckConstraint("fecha_fin >= fecha_inicio", name="ck_contrato_fechas"),
        CheckConstraint(
            "estado IN ('borrador','activo','suspendido','finalizado')",
            name="ck_contrato_estado",
        ),
        CheckConstraint(
            "retencion_garantia >= 0 AND retencion_garantia <= 100",
            name="ck_contrato_retencion",
        ),
    )


class ContratoModificacion(db.Model):
    __tablename__ = "contrato_modificaciones"

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(
        db.Integer,
        db.ForeignKey("contratos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo = db.Column(db.String(10), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    monto_original = db.Column(db.Numeric(14, 2))
    monto_nuevo = db.Column(db.Numeric(14, 2))
    fecha = db.Column(db.Date, nullable=False)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    estado = db.Column(
        db.String(12), nullable=False, default="pendiente", server_default="pendiente",
        index=True
    )
    version = db.Column(db.Integer, nullable=False)
    fecha_fin_nueva = db.Column(db.Date)
    aprobador_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    fecha_aprobacion = db.Column(db.DateTime(timezone=True))
    comentario_aprobacion = db.Column(db.Text)

    contrato = db.relationship("Contrato", back_populates="modificaciones")
    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])
    aprobador = db.relationship("Usuario", foreign_keys=[aprobador_id])

    __table_args__ = (
        UniqueConstraint(
            "contrato_id", "version", name="uq_contrato_modificacion_version"
        ),
        CheckConstraint(
            "tipo IN ('alcance','precio','plazo')",
            name="ck_contrato_modificacion_tipo",
        ),
        CheckConstraint(
            "estado IN ('pendiente','aprobada','rechazada')",
            name="ck_contrato_modificacion_estado",
        ),
    )


class ConciliacionFactura(db.Model):
    __tablename__ = "conciliaciones_facturas"

    id = db.Column(db.Integer, primary_key=True)
    orden_compra_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    factura_numero = db.Column(db.String(80), nullable=False)
    fecha_factura = db.Column(db.Date, nullable=False)
    monto_factura = db.Column(db.Numeric(14, 2), nullable=False)
    monto_pedido = db.Column(db.Numeric(14, 2), nullable=False)
    monto_recibido = db.Column(db.Numeric(14, 2), nullable=False)
    monto_pagado = db.Column(db.Numeric(14, 2), nullable=False)
    estado = db.Column(
        db.String(12), nullable=False, default="pendiente", server_default="pendiente",
        index=True
    )
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fecha_conciliacion = db.Column(db.DateTime(timezone=True))
    motivo_diferencia = db.Column(db.Text)
    aprobador_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    fecha_aprobacion = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    orden_compra = db.relationship("PurchaseOrder")
    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])
    aprobador = db.relationship("Usuario", foreign_keys=[aprobador_id])

    __table_args__ = (
        UniqueConstraint(
            "orden_compra_id", "factura_numero",
            name="uq_conciliacion_orden_factura"
        ),
        CheckConstraint(
            "monto_factura >= 0 AND monto_pedido >= 0 AND "
            "monto_recibido >= 0 AND monto_pagado >= 0",
            name="ck_conciliacion_montos",
        ),
        CheckConstraint(
            "estado IN ('pendiente','aprobada','rechazada','pagada')",
            name="ck_conciliacion_estado",
        ),
    )

    @property
    def coincide(self) -> bool:
        tolerance = Decimal("0.01")
        pedido = Decimal(str(self.monto_pedido or 0))
        recibido = Decimal(str(self.monto_recibido or 0))
        factura = Decimal(str(self.monto_factura or 0))
        return abs(pedido - recibido) <= tolerance and abs(recibido - factura) <= tolerance

    @property
    def diferencia(self) -> Decimal:
        return Decimal(str(self.monto_factura or 0)) - Decimal(
            str(self.monto_recibido or 0)
        )


class GarantiaObra(db.Model):
    """Garantía separada de la ejecución original de una obra terminada."""

    __tablename__ = "garantias_obras"

    id = db.Column(db.Integer, primary_key=True)
    obra_principal_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    centro_garantia_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    supervisor_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reportada_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    descripcion = db.Column(db.Text, nullable=False)
    ubicacion = db.Column(db.String(240), nullable=False)
    motivo = db.Column(db.String(500), nullable=False)
    evidencia_inicial = db.Column(db.String(500))
    diagnostico = db.Column(db.Text)
    trabajos_requeridos = db.Column(db.Text)
    accion_correctiva = db.Column(db.Text)
    evidencia_final = db.Column(db.String(500))
    estado = db.Column(
        db.String(20),
        nullable=False,
        default="reportada",
        server_default="reportada",
        index=True,
    )
    autorizada_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    cerrada_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    rechazada_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    motivo_rechazo = db.Column(db.String(500))
    fecha_diagnostico = db.Column(db.DateTime(timezone=True))
    fecha_autorizacion = db.Column(db.DateTime(timezone=True))
    fecha_inicio = db.Column(db.DateTime(timezone=True))
    fecha_solicitud_cierre = db.Column(db.DateTime(timezone=True))
    fecha_cierre = db.Column(db.DateTime(timezone=True))
    fecha_creacion = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    obra_principal = db.relationship(
        "CentroCosto", foreign_keys=[obra_principal_id]
    )
    centro_garantia = db.relationship(
        "CentroCosto", foreign_keys=[centro_garantia_id]
    )
    supervisor = db.relationship("Usuario", foreign_keys=[supervisor_id])
    reportada_por = db.relationship("Usuario", foreign_keys=[reportada_por_id])
    autorizada_por = db.relationship("Usuario", foreign_keys=[autorizada_por_id])
    cerrada_por = db.relationship("Usuario", foreign_keys=[cerrada_por_id])
    rechazada_por = db.relationship("Usuario", foreign_keys=[rechazada_por_id])
    smnc = db.relationship("MaterialChangeRequest", back_populates="garantia")

    __table_args__ = (
        CheckConstraint(
            "obra_principal_id <> centro_garantia_id",
            name="ck_garantia_centros_distintos",
        ),
        CheckConstraint(
            "estado IN ('reportada','diagnostico','autorizada','en_ejecucion',"
            "'pendiente_cierre','cerrada','rechazada')",
            name="ck_garantia_estado",
        ),
    )

    @property
    def activa(self) -> bool:
        return self.estado not in {"cerrada", "rechazada"}


class DiscrepanciaRecepcion(db.Model):
    __tablename__ = "discrepancias_recepcion"

    id = db.Column(db.Integer, primary_key=True)
    orden_compra_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    orden_linea_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_order_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    recepcion_id = db.Column(
        db.Integer,
        db.ForeignKey("goods_receipts.id", ondelete="SET NULL"),
    )
    tipo = db.Column(db.String(10), nullable=False)
    cantidad = db.Column(db.Numeric(16, 4), nullable=False)
    descripcion = db.Column(db.String(500), nullable=False)
    evidencia = db.Column(db.String(500))
    estado = db.Column(
        db.String(10), nullable=False, default="abierta", server_default="abierta",
        index=True
    )
    usuario_reporta_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fecha_reporte = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    usuario_resuelve_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    fecha_resolucion = db.Column(db.DateTime(timezone=True))
    resolucion = db.Column(db.Text)

    orden_compra = db.relationship("PurchaseOrder")
    orden_linea = db.relationship("PurchaseOrderLine")
    recepcion = db.relationship("GoodsReceipt")
    usuario_reporta = db.relationship("Usuario", foreign_keys=[usuario_reporta_id])
    usuario_resuelve = db.relationship("Usuario", foreign_keys=[usuario_resuelve_id])

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('rechazado','faltante')", name="ck_discrepancia_tipo"
        ),
        CheckConstraint("cantidad > 0", name="ck_discrepancia_cantidad"),
        CheckConstraint(
            "estado IN ('abierta','resuelta')", name="ck_discrepancia_estado"
        ),
    )


class Fase5AlertRun(db.Model):
    __tablename__ = "fase5_alert_runs"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, unique=True, index=True)
    ncr_por_vencer = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    certificaciones_pendientes = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    licitaciones_sin_adjudicar = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    executed_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
