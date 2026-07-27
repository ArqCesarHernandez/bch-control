"""Modelos de la Fase 4 final: Compras, crédito y control presupuestal.

El módulo conserva la estructura de Nóminas y añade un flujo auditable desde
la explosión de insumos hasta requisición, cotización, orden, recepción y pago.
Todos los importes de control se expresan sin IVA y en MXN.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, UniqueConstraint

from models import CentroCosto, Usuario, db, utc_now
from nominas_models import BudgetItem, Company, decimal_value, money


ACTIVE_ORDER_STATES = {
    "EMITIDA",
    "PENDIENTE_ANTICIPO",
    "ANTICIPO_AUTORIZADO",
    "ANTICIPO_PARCIAL",
    "ANTICIPO_PAGADO",
    "RECEPCION_PARCIAL",
    "RECEPCION_TOTAL",
    "CERRADA",
}

# Una cotización puede agrupar requisiciones de una o varias obras. La llave
# ``Quotation.requisition_id`` se conserva como ancla histórica; esta relación
# registra el conjunto completo sin alterar cotizaciones anteriores.
quotation_requisitions = db.Table(
    "quotation_requisitions",
    db.Column(
        "quotation_id",
        db.Integer,
        db.ForeignKey("quotations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "requisition_id",
        db.Integer,
        db.ForeignKey("purchase_requisitions.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)

OPERATION_CATEGORIES = {
    "AGREGADOS": "Agregados",
    "TIERRA_RELLENO": "Tierra para relleno",
    "ARENA": "Arena",
    "RETIRO_ESCOMBRO": "Retiro de escombro",
    "GRAVA": "Grava",
    "AGUA": "Agua",
    "RENTA_EQUIPO": "Horas de renta de equipo",
    "GASTO_OFICINA": "Gastos de oficina",
}


class Supplier(db.Model):
    """Proveedor y condiciones vigentes de su línea de crédito."""

    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(40), nullable=False, unique=True, index=True)
    nombre = db.Column(db.String(180), nullable=False, unique=True, index=True)
    rfc = db.Column(db.String(13), index=True)
    contacto = db.Column(db.String(150))
    telefono = db.Column(db.String(50))
    email = db.Column(db.String(180))
    company_id = db.Column(
        db.Integer, db.ForeignKey("companies.id", ondelete="SET NULL")
    )
    tiene_credito = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )
    limite_credito = db.Column(
        db.Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    dias_credito = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    moneda = db.Column(
        db.String(3), nullable=False, default="MXN", server_default="MXN"
    )
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    notas = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    company = db.relationship("Company")
    orders = db.relationship("PurchaseOrder", back_populates="supplier")
    quotations = db.relationship("Quotation", back_populates="supplier")
    supply_history = db.relationship(
        "SupplierSupplyItem",
        back_populates="supplier",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("moneda = 'MXN'", name="ck_supplier_currency_mxn"),
        CheckConstraint("limite_credito >= 0", name="ck_supplier_credit_limit"),
        CheckConstraint("dias_credito >= 0", name="ck_supplier_credit_days"),
        CheckConstraint(
            "tiene_credito = 0 OR (limite_credito > 0 AND dias_credito > 0)",
            name="ck_supplier_credit_configuration",
        ),
    )

    @property
    def etiqueta(self) -> str:
        return f"{self.codigo} · {self.nombre}"

    @property
    def credito_utilizado(self) -> Decimal:
        return money(
            sum(
                (
                    order.saldo_pendiente
                    for order in self.orders
                    if order.modalidad_pago == "CREDITO"
                    and order.estado in ACTIVE_ORDER_STATES
                ),
                Decimal("0"),
            )
        )

    @property
    def credito_disponible(self) -> Decimal:
        if not self.tiene_credito:
            return Decimal("0.00")
        return money(decimal_value(self.limite_credito) - self.credito_utilizado)

    def tiene_credito_vencido(self, today: date | None = None) -> bool:
        current = today or date.today()
        return any(
            order.modalidad_pago == "CREDITO"
            and order.estado in ACTIVE_ORDER_STATES
            and order.fecha_vencimiento is not None
            and order.fecha_vencimiento < current
            and order.saldo_pendiente > 0
            for order in self.orders
        )

    def estado_credito(self, today: date | None = None) -> str:
        if self.tiene_credito_vencido(today):
            return "VENCIDO"
        if self.tiene_credito:
            return "ACTIVO"
        return "SIN_CREDITO"


class PaymentMethod(db.Model):
    """Catálogo compartido y desactivable de métodos de pago."""

    __tablename__ = "payment_methods"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False, unique=True)
    descripcion = db.Column(db.String(240))
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    orders = db.relationship("PurchaseOrder", back_populates="payment_method")


class SupplyItem(db.Model):
    """Catálogo maestro de insumos."""

    __tablename__ = "supply_items"

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(40), nullable=False, unique=True, index=True)
    descripcion = db.Column(db.String(180), nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False)
    unidad = db.Column(db.String(20), nullable=False)
    clave_sat = db.Column(
        db.String(20), nullable=False, default="00000000", server_default="00000000"
    )
    moneda = db.Column(
        db.String(3), nullable=False, default="MXN", server_default="MXN"
    )
    precio_variable = db.Column(
        db.Boolean, nullable=False, default=True, server_default="1"
    )
    es_operacion = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0", index=True
    )
    categoria_operacion = db.Column(db.String(30), index=True)
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    supplier_history = db.relationship(
        "SupplierSupplyItem",
        back_populates="supply_item",
        cascade="all, delete-orphan",
    )
    project_catalog_entries = db.relationship(
        "SupplyProjectCatalog",
        back_populates="supply_item",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('MATERIAL','EQUIPO','MANO_OBRA','SUBCONTRATO','INDIRECTO')",
            name="ck_supply_item_type",
        ),
        CheckConstraint("moneda = 'MXN'", name="ck_supply_item_currency_mxn"),
    )

    @property
    def etiqueta(self) -> str:
        return f"{self.clave} · {self.descripcion}"


class SupplierSupplyItem(db.Model):
    """Último precio conocido de un insumo para un proveedor.

    La relación se guarda contra el catálogo maestro y no contra una sola obra.
    Así puede sugerirse el mismo proveedor cuando el insumo aparezca en otra
    explosión, sin sumar cantidades históricas al presupuesto vigente.
    """

    __tablename__ = "supplier_supply_items"

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supply_item_id = db.Column(
        db.Integer,
        db.ForeignKey("supply_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    precio_historico = db.Column(db.Numeric(16, 4), nullable=False)
    fecha_ultima_compra = db.Column(db.Date)
    origen = db.Column(
        db.String(20), nullable=False, default="IMPORTACION", server_default="IMPORTACION"
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    supplier = db.relationship("Supplier", back_populates="supply_history")
    supply_item = db.relationship("SupplyItem", back_populates="supplier_history")

    __table_args__ = (
        UniqueConstraint(
            "supplier_id", "supply_item_id", name="uq_supplier_supply_item"
        ),
        CheckConstraint(
            "precio_historico >= 0", name="ck_supplier_supply_historical_price"
        ),
        CheckConstraint(
            "origen IN ('IMPORTACION','ORDEN_COMPRA')",
            name="ck_supplier_supply_source",
        ),
    )


class SupplyProjectCatalog(db.Model):
    """Clasifica un insumo histórico por obra sin crear presupuesto."""

    __tablename__ = "supply_project_catalog"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    budget_item_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    supply_item_id = db.Column(
        db.Integer,
        db.ForeignKey("supply_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    project = db.relationship("CentroCosto")
    budget_item = db.relationship("BudgetItem")
    supply_item = db.relationship(
        "SupplyItem", back_populates="project_catalog_entries"
    )
    created_by = db.relationship("Usuario")

    __table_args__ = (
        UniqueConstraint(
            "project_id", "supply_item_id", name="uq_supply_project_catalog"
        ),
    )


class ExplosionRevision(db.Model):
    """Carga versionada de la explosión de una obra.

    Solo una revisión puede estar vigente por centro de costo. Los renglones
    históricos permanecen disponibles para trazabilidad y garantías, pero no
    se mezclan con el presupuesto operativo actual.
    """

    __tablename__ = "explosion_revisions"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    numero_revision = db.Column(db.Integer, nullable=False)
    estado = db.Column(
        db.String(12),
        nullable=False,
        default="VIGENTE",
        server_default="VIGENTE",
        index=True,
    )
    es_vigente = db.Column(
        db.Boolean, nullable=False, default=True, server_default="1", index=True
    )
    archivo_origen = db.Column(db.String(255))
    observaciones = db.Column(db.String(500))
    obra_origen_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    loaded_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    loaded_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )
    vigente_desde = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )
    vigente_hasta = db.Column(db.DateTime(timezone=True))

    project = db.relationship("CentroCosto", foreign_keys=[project_id])
    obra_origen = db.relationship("CentroCosto", foreign_keys=[obra_origen_id])
    loaded_by = db.relationship("Usuario")
    items = db.relationship(
        "BudgetExplosionItem",
        back_populates="revision",
        cascade="all, delete-orphan",
        order_by="BudgetExplosionItem.id",
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "numero_revision",
            name="uq_explosion_revision_project_number",
        ),
        CheckConstraint(
            "estado IN ('VIGENTE','HISTORICA','CANCELADA')",
            name="ck_explosion_revision_status",
        ),
    )


class BudgetExplosionItem(db.Model):
    """Renglón presupuestado de la explosión de una obra."""

    __tablename__ = "budget_explosion_items"

    id = db.Column(db.Integer, primary_key=True)
    revision_id = db.Column(
        db.Integer,
        db.ForeignKey("explosion_revisions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    budget_item_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    supply_item_id = db.Column(
        db.Integer,
        db.ForeignKey("supply_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    cantidad_presupuestada = db.Column(db.Numeric(16, 4), nullable=False)
    # Reserva inmediata de conceptos todavía pendientes (incluidos
    # borradores). Al liberarse una línea aprobada, la reserva pasa al cálculo
    # dinámico ``cantidad_aprobada_pendiente`` para no duplicar el compromiso.
    cantidad_reservada_borrador = db.Column(
        db.Numeric(16, 4),
        nullable=False,
        default=0,
        server_default="0",
    )
    precio_unitario_sin_iva = db.Column(db.Numeric(16, 4), nullable=False)
    importe_presupuestado = db.Column(db.Numeric(14, 2), nullable=False)
    clasificacion = db.Column(
        db.String(40), nullable=False, default="NORMAL", server_default="NORMAL"
    )
    requiere_autorizacion_previa = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0", index=True
    )
    observacion_clasificacion = db.Column(db.String(500))
    source_explosion_item_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_explosion_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    origen = db.Column(
        db.String(20), nullable=False, default="EXPLOSION", server_default="EXPLOSION"
    )
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    revision = db.relationship("ExplosionRevision", back_populates="items")
    project = db.relationship("CentroCosto")
    budget_item = db.relationship("BudgetItem")
    supply_item = db.relationship("SupplyItem")
    created_by = db.relationship("Usuario")
    source_explosion_item = db.relationship(
        "BudgetExplosionItem",
        remote_side=[id],
        foreign_keys=[source_explosion_item_id],
    )
    requisition_lines = db.relationship(
        "PurchaseRequisitionLine", back_populates="explosion_item"
    )
    order_lines = db.relationship("PurchaseOrderLine", back_populates="explosion_item")

    __table_args__ = (
        UniqueConstraint(
            "revision_id",
            "budget_item_id",
            "supply_item_id",
            name="uq_explosion_revision_budget_supply",
        ),
        CheckConstraint(
            "cantidad_presupuestada > 0", name="ck_explosion_budget_quantity"
        ),
        CheckConstraint(
            "cantidad_reservada_borrador >= 0",
            name="ck_explosion_draft_reserved_quantity",
        ),
        CheckConstraint(
            "precio_unitario_sin_iva >= 0", name="ck_explosion_unit_price"
        ),
        CheckConstraint(
            "importe_presupuestado >= 0", name="ck_explosion_budget_amount"
        ),
        CheckConstraint(
            "origen IN ('EXPLOSION','SMNC','GARANTIA_HISTORICA')",
            name="ck_explosion_source",
        ),
    )

    @property
    def etiqueta(self) -> str:
        return (
            f"{self.budget_item.codigo} · {self.supply_item.clave} · "
            f"{self.supply_item.descripcion}"
        )

    @property
    def cantidad_ordenada(self) -> Decimal:
        return sum(
            (
                decimal_value(line.cantidad)
                for line in self.order_lines
                if line.order and line.order.estado in ACTIVE_ORDER_STATES
            ),
            Decimal("0"),
        )

    @property
    def cantidad_aprobada_pendiente(self) -> Decimal:
        return sum(
            (
                line.cantidad_pendiente_compra
                for line in self.requisition_lines
                if line.requisition.estado in {"APROBADA", "PARCIAL"}
                and line.estado_linea == "APROBADA"
            ),
            Decimal("0"),
        )

    @property
    def cantidad_recibida(self) -> Decimal:
        return sum(
            (
                receipt_line.cantidad_recibida
                for line in self.order_lines
                if line.order and line.order.estado in ACTIVE_ORDER_STATES
                for receipt_line in line.receipt_lines
            ),
            Decimal("0"),
        )

    @property
    def cantidad_pagada(self) -> Decimal:
        from nominas_models import AdditionalPayment

        paid = money(
            db.session.query(db.func.coalesce(db.func.sum(AdditionalPayment.monto_sin_iva), 0))
            .filter(AdditionalPayment.explosion_item_id == self.id)
            .scalar()
        )
        price = decimal_value(self.precio_unitario_sin_iva)
        return Decimal("0") if price <= 0 else paid / price

    @property
    def cantidad_disponible(self) -> Decimal:
        return max(
            Decimal("0"),
            self.saldo_disponible_crudo,
        )

    @property
    def saldo_disponible_crudo(self) -> Decimal:
        return (
            decimal_value(self.cantidad_presupuestada)
            - self.cantidad_ordenada
            - self.cantidad_aprobada_pendiente
            - decimal_value(self.cantidad_reservada_borrador)
        )

    @property
    def importe_ordenado(self) -> Decimal:
        return money(
            sum(
                (
                    line.importe_sin_iva
                    for line in self.order_lines
                    if line.order and line.order.estado in ACTIVE_ORDER_STATES
                ),
                Decimal("0"),
            )
        )

    @property
    def importe_pagado(self) -> Decimal:
        from nominas_models import AdditionalPayment

        legacy = money(
            db.session.query(
                db.func.coalesce(db.func.sum(AdditionalPayment.monto_sin_iva), 0)
            )
            .filter(
                AdditionalPayment.explosion_item_id == self.id,
                AdditionalPayment.purchase_order_line_id.is_(None),
            )
            .scalar()
        )
        return money(
            legacy
            + sum(
                (line.monto_pagado_efectivo for line in self.order_lines),
                Decimal("0"),
            )
        )

    @property
    def importe_disponible(self) -> Decimal:
        return money(
            self.cantidad_disponible * decimal_value(self.precio_unitario_sin_iva)
        )


class PurchaseRequisition(db.Model):
    """Requisición de obra creada por un supervisor y autorizada por Costos/Admin."""

    __tablename__ = "purchase_requisitions"

    id = db.Column(db.Integer, primary_key=True)
    folio = db.Column(db.String(30), nullable=False, unique=True, index=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    fecha_solicitud = db.Column(db.Date, nullable=False)
    fecha_requerida = db.Column(db.Date, nullable=False)
    tipo_requisicion = db.Column(
        db.String(12), nullable=False, default="COMPRAS", server_default="COMPRAS", index=True
    )
    estado = db.Column(
        db.String(22), nullable=False, default="BORRADOR", server_default="BORRADOR"
    )
    motivo = db.Column(db.String(240), nullable=False)
    observaciones = db.Column(db.Text)
    requested_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    submitted_at = db.Column(db.DateTime(timezone=True))
    approved_by_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    approved_at = db.Column(db.DateTime(timezone=True))
    buyer_received_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
        index=True,
    )
    buyer_received_at = db.Column(db.DateTime(timezone=True))
    fecha_limite_oc = db.Column(db.Date)
    rejection_reason = db.Column(db.String(300))
    expiry_notified_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    project = db.relationship("CentroCosto")
    requested_by = db.relationship("Usuario", foreign_keys=[requested_by_id])
    approved_by = db.relationship("Usuario", foreign_keys=[approved_by_id])
    buyer_received_by = db.relationship(
        "Usuario", foreign_keys=[buyer_received_by_id]
    )
    lines = db.relationship(
        "PurchaseRequisitionLine",
        back_populates="requisition",
        cascade="all, delete-orphan",
        order_by="PurchaseRequisitionLine.id",
    )
    quotations = db.relationship(
        "Quotation", back_populates="requisition", cascade="all, delete-orphan"
    )
    consolidated_quotations = db.relationship(
        "Quotation",
        secondary=quotation_requisitions,
        back_populates="requisitions",
        overlaps="quotation,requisition,quotations",
    )
    legacy_orders = db.relationship("PurchaseOrder", back_populates="requisition")

    __table_args__ = (
        CheckConstraint(
            "estado IN ('BORRADOR','PENDIENTE_AUTORIZACION','APROBADA','RECHAZADA','PARCIAL','CERRADA','VENCIDA','CANCELADA')",
            name="ck_purchase_requisition_status",
        ),
        CheckConstraint(
            "fecha_requerida >= fecha_solicitud",
            name="ck_purchase_requisition_dates",
        ),
    )

    @property
    def total_solicitado(self) -> Decimal:
        return money(sum((line.importe_solicitado for line in self.lines), Decimal("0")))

    @property
    def total_estimado(self) -> Decimal:
        return self.total_solicitado

    @property
    def total_aprobado(self) -> Decimal:
        return money(sum((line.importe_aprobado for line in self.lines), Decimal("0")))

    @property
    def total_pendiente_compra(self) -> Decimal:
        return money(
            sum((line.importe_pendiente_compra for line in self.lines), Decimal("0"))
        )

    @property
    def porcentaje_compra(self) -> Decimal:
        """Avance físico comprado contra la cantidad originalmente solicitada."""

        requested = sum(
            (decimal_value(line.cantidad_solicitada) for line in self.lines),
            Decimal("0"),
        )
        if requested <= 0:
            return Decimal("0")
        purchased = sum(
            (
                min(
                    decimal_value(line.cantidad_solicitada),
                    line.cantidad_ordenada,
                )
                for line in self.lines
            ),
            Decimal("0"),
        )
        return min(Decimal("100"), purchased * Decimal("100") / requested)

    @property
    def related_orders(self):
        orders = {}
        for line in self.lines:
            for order_line in line.order_lines:
                if order_line.order:
                    orders[order_line.order.id] = order_line.order
        return list(orders.values())

    @property
    def orders(self):
        """Alias de compatibilidad con las plantillas de la primera versión."""

        return self.related_orders or self.legacy_orders

    @property
    def all_quotations(self):
        """Cotizaciones ancladas o consolidadas, sin duplicados."""

        by_id = {
            quotation.id: quotation
            for quotation in [*self.quotations, *self.consolidated_quotations]
            if quotation.id is not None
        }
        return sorted(by_id.values(), key=lambda quotation: quotation.id)


class PurchaseRequisitionLine(db.Model):
    __tablename__ = "purchase_requisition_lines"

    id = db.Column(db.Integer, primary_key=True)
    requisition_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_requisitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    explosion_item_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_explosion_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cantidad_solicitada = db.Column(db.Numeric(16, 4), nullable=False)
    cantidad_aprobada = db.Column(
        db.Numeric(16, 4), nullable=False, default=0, server_default="0"
    )
    estado_linea = db.Column(
        db.String(24), nullable=False, default="PENDIENTE", server_default="PENDIENTE"
    )
    requiere_autorizacion_previa = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0", index=True
    )
    liberada_at = db.Column(db.DateTime(timezone=True))
    motivo_rechazo_compras = db.Column(db.String(300))
    notas = db.Column(db.String(240))
    # Campo histórico de Fase 4: se conserva para no destruir datos, pero ya
    # no se captura, filtra ni muestra. El Comprador elige al proveedor al
    # preparar la cotización.
    proveedor_sugerido = db.Column(db.String(180), index=True)

    requisition = db.relationship("PurchaseRequisition", back_populates="lines")
    explosion_item = db.relationship(
        "BudgetExplosionItem", back_populates="requisition_lines"
    )
    order_lines = db.relationship("PurchaseOrderLine", back_populates="requisition_line")
    quotation_lines = db.relationship("QuotationLine", back_populates="requisition_line")

    __table_args__ = (
        UniqueConstraint(
            "requisition_id",
            "explosion_item_id",
            name="uq_requisition_explosion_item",
        ),
        CheckConstraint(
            "cantidad_solicitada > 0", name="ck_requisition_line_quantity"
        ),
        CheckConstraint(
            "cantidad_aprobada >= 0 AND cantidad_aprobada <= cantidad_solicitada",
            name="ck_requisition_line_approved_quantity",
        ),
        CheckConstraint(
            "estado_linea IN ('PENDIENTE','APROBADA','RECHAZADA','RECHAZADA_COMPRAS')",
            name="ck_requisition_line_status",
        ),
    )

    @property
    def importe_solicitado(self) -> Decimal:
        return money(
            decimal_value(self.cantidad_solicitada)
            * decimal_value(self.explosion_item.precio_unitario_sin_iva)
        )

    @property
    def importe_estimado(self) -> Decimal:
        return self.importe_solicitado

    @property
    def importe_aprobado(self) -> Decimal:
        return money(
            decimal_value(self.cantidad_aprobada)
            * decimal_value(self.explosion_item.precio_unitario_sin_iva)
        )

    @property
    def cantidad_ordenada(self) -> Decimal:
        return sum(
            (
                decimal_value(line.cantidad)
                for line in self.order_lines
                if line.order and line.order.estado in ACTIVE_ORDER_STATES
            ),
            Decimal("0"),
        )

    @property
    def cantidad_pendiente_compra(self) -> Decimal:
        if self.estado_linea != "APROBADA":
            return Decimal("0")
        return max(
            Decimal("0"),
            decimal_value(self.cantidad_aprobada) - self.cantidad_ordenada,
        )

    @property
    def cantidad_pendiente(self) -> Decimal:
        return self.cantidad_pendiente_compra

    @property
    def cantidad_pendiente_solicitada(self) -> Decimal:
        """Cantidad faltante para cerrar el renglón completo de la requisición."""

        return max(
            Decimal("0"),
            decimal_value(self.cantidad_solicitada) - self.cantidad_ordenada,
        )

    @property
    def porcentaje_compra(self) -> Decimal:
        requested = decimal_value(self.cantidad_solicitada)
        if requested <= 0:
            return Decimal("0")
        return min(
            Decimal("100"),
            self.cantidad_ordenada * Decimal("100") / requested,
        )

    @property
    def importe_pendiente_compra(self) -> Decimal:
        return money(
            self.cantidad_pendiente_compra
            * decimal_value(self.explosion_item.precio_unitario_sin_iva)
        )


class Quotation(db.Model):
    """Solicitud y respuesta de cotización de un proveedor."""

    __tablename__ = "quotations"

    id = db.Column(db.Integer, primary_key=True)
    folio = db.Column(db.String(30), nullable=False, unique=True, index=True)
    requisition_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_requisitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier_id = db.Column(
        db.Integer, db.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    fecha_solicitud = db.Column(db.Date, nullable=False)
    fecha_respuesta = db.Column(db.Date)
    fecha_entrega_ofertada = db.Column(db.Date)
    estado = db.Column(
        db.String(15), nullable=False, default="SOLICITADA", server_default="SOLICITADA"
    )
    notas = db.Column(db.Text)
    email_sent_at = db.Column(db.DateTime(timezone=True))
    email_sent_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
        index=True,
    )
    email_to = db.Column(db.String(180))
    email_cc = db.Column(db.String(180))
    email_error = db.Column(db.String(500))
    whatsapp_contacted_at = db.Column(db.DateTime(timezone=True))
    whatsapp_contacted_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
        index=True,
    )
    whatsapp_notes = db.Column(db.String(500))
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    requisition = db.relationship("PurchaseRequisition", back_populates="quotations")
    requisitions = db.relationship(
        "PurchaseRequisition",
        secondary=quotation_requisitions,
        back_populates="consolidated_quotations",
        overlaps="quotation,requisition,quotations",
    )
    supplier = db.relationship("Supplier", back_populates="quotations")
    created_by = db.relationship("Usuario", foreign_keys=[created_by_id])
    email_sent_by = db.relationship("Usuario", foreign_keys=[email_sent_by_id])
    whatsapp_contacted_by = db.relationship(
        "Usuario", foreign_keys=[whatsapp_contacted_by_id]
    )
    lines = db.relationship(
        "QuotationLine", back_populates="quotation", cascade="all, delete-orphan"
    )
    orders = db.relationship("PurchaseOrder", back_populates="quotation")

    __table_args__ = (
        CheckConstraint(
            "estado IN ('SOLICITADA','RESPONDIDA','SELECCIONADA','DESCARTADA','CANCELADA')",
            name="ck_quotation_status",
        ),
    )

    @property
    def total_cotizado(self) -> Decimal:
        return money(sum((line.importe_cotizado for line in self.lines), Decimal("0")))

    @property
    def requisition_set(self) -> list[PurchaseRequisition]:
        requisitions = list(self.requisitions)
        if self.requisition and all(
            requisition.id != self.requisition.id for requisition in requisitions
        ):
            requisitions.insert(0, self.requisition)
        return sorted(requisitions, key=lambda item: item.id)

    @property
    def projects(self) -> list[CentroCosto]:
        by_id = {
            requisition.project.id: requisition.project
            for requisition in self.requisition_set
            if requisition.project
        }
        return sorted(by_id.values(), key=lambda project: project.nombre)

    @property
    def es_consolidada(self) -> bool:
        return len(self.requisition_set) > 1


class QuotationLine(db.Model):
    __tablename__ = "quotation_lines"

    id = db.Column(db.Integer, primary_key=True)
    quotation_id = db.Column(
        db.Integer, db.ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False
    )
    requisition_line_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_requisition_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    supply_item_id = db.Column(
        db.Integer,
        db.ForeignKey("supply_items.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    cantidad = db.Column(db.Numeric(16, 4), nullable=False)
    precio_unitario_cotizado = db.Column(
        db.Numeric(16, 4), nullable=False, default=0, server_default="0"
    )
    importe_cotizado = db.Column(
        db.Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    notas = db.Column(db.String(240))

    quotation = db.relationship("Quotation", back_populates="lines")
    requisition_line = db.relationship(
        "PurchaseRequisitionLine", back_populates="quotation_lines"
    )
    supply_item = db.relationship("SupplyItem")
    sources = db.relationship(
        "QuotationLineSource",
        back_populates="quotation_line",
        cascade="all, delete-orphan",
        order_by="QuotationLineSource.id",
    )

    __table_args__ = (
        UniqueConstraint(
            "quotation_id", "requisition_line_id", name="uq_quotation_requisition_line"
        ),
        CheckConstraint("cantidad > 0", name="ck_quotation_line_quantity"),
        CheckConstraint(
            "precio_unitario_cotizado >= 0", name="ck_quotation_line_price"
        ),
        CheckConstraint("importe_cotizado >= 0", name="ck_quotation_line_amount"),
    )

    @property
    def material(self) -> SupplyItem:
        return self.supply_item or self.requisition_line.explosion_item.supply_item

    @property
    def source_requisition_lines(self) -> list[PurchaseRequisitionLine]:
        if self.sources:
            return [source.requisition_line for source in self.sources]
        return [self.requisition_line]

    @property
    def comentarios_supervisor(self) -> str:
        comments = []
        for line in self.source_requisition_lines:
            comment = (line.notas or "").strip()
            if comment and comment not in comments:
                comments.append(comment)
        return " · ".join(comments)

    @property
    def precio_presupuestado(self) -> Decimal:
        total_quantity = Decimal("0")
        total_amount = Decimal("0")
        for line in self.source_requisition_lines:
            quantity = next(
                (
                    decimal_value(source.cantidad)
                    for source in self.sources
                    if source.requisition_line_id == line.id
                ),
                decimal_value(self.cantidad),
            )
            total_quantity += quantity
            total_amount += (
                quantity
                * decimal_value(line.explosion_item.precio_unitario_sin_iva)
            )
        return (
            Decimal("0")
            if total_quantity <= 0
            else total_amount / total_quantity
        )


class QuotationLineSource(db.Model):
    """Trazabilidad de una línea agrupada hacia cada requisición original."""

    __tablename__ = "quotation_line_sources"

    id = db.Column(db.Integer, primary_key=True)
    quotation_line_id = db.Column(
        db.Integer,
        db.ForeignKey("quotation_lines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requisition_line_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_requisition_lines.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    cantidad = db.Column(db.Numeric(16, 4), nullable=False)

    quotation_line = db.relationship("QuotationLine", back_populates="sources")
    requisition_line = db.relationship("PurchaseRequisitionLine")

    __table_args__ = (
        UniqueConstraint(
            "quotation_line_id",
            "requisition_line_id",
            name="uq_quotation_line_source",
        ),
        CheckConstraint(
            "cantidad > 0",
            name="ck_quotation_line_source_quantity",
        ),
    )


class PurchaseOrder(db.Model):
    """Orden que puede consolidar líneas de varias requisiciones."""

    __tablename__ = "purchase_orders"

    id = db.Column(db.Integer, primary_key=True)
    folio = db.Column(db.String(30), nullable=False, unique=True, index=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Se conserva para compatibilidad histórica; la relación definitiva está
    # en cada renglón y permite consolidar varias requisiciones.
    requisition_id = db.Column(
        db.Integer, db.ForeignKey("purchase_requisitions.id", ondelete="SET NULL")
    )
    quotation_id = db.Column(
        db.Integer, db.ForeignKey("quotations.id", ondelete="SET NULL")
    )
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=True,
    )
    company_id = db.Column(
        db.Integer, db.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True
    )
    buyer_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    payment_method_id = db.Column(
        db.Integer,
        db.ForeignKey("payment_methods.id", ondelete="RESTRICT"),
        nullable=True,
    )
    fecha_orden = db.Column(db.Date, nullable=False)
    fecha_entrega_estimada = db.Column(db.Date, nullable=False)
    fecha_surtido_real = db.Column(db.Date)
    fecha_limite = db.Column(db.Date, nullable=False)
    tipo_oc = db.Column(
        db.String(12), nullable=False, default="COMPRAS", server_default="COMPRAS", index=True
    )
    categoria_pago = db.Column(
        db.String(12), nullable=False, default="COMPRAS", server_default="COMPRAS", index=True
    )
    requiere_autorizacion = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0", index=True
    )
    # Las OC creadas después de la Fase 5 exigen conciliación de tres vías
    # antes del pago. La migración conserva las OC históricas con False para
    # evitar bloquear compromisos que nacieron bajo el flujo anterior.
    requiere_conciliacion = db.Column(
        db.Boolean, nullable=False, default=True, server_default="0", index=True
    )
    autorizacion_solicitada_at = db.Column(db.DateTime(timezone=True))
    estado = db.Column(
        db.String(30), nullable=False, default="BORRADOR", server_default="BORRADOR"
    )
    modalidad_pago = db.Column(
        db.String(24), nullable=False, default="CREDITO", server_default="CREDITO"
    )
    beneficiario_libre = db.Column(db.String(180))
    beneficiario_validado = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )
    beneficiario_validado_por_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    beneficiario_validado_at = db.Column(db.DateTime(timezone=True))
    condicion_saldo = db.Column(
        db.String(30),
        nullable=False,
        default="CONTRA_RECEPCION",
        server_default="CONTRA_RECEPCION",
    )
    anticipo_monto = db.Column(
        db.Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    anticipo_porcentaje = db.Column(
        db.Numeric(7, 4), nullable=False, default=0, server_default="0"
    )
    anticipo_pendiente = db.Column(
        db.Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    justificacion_anticipo = db.Column(db.String(500))
    autorizado_anticipo_por_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    fecha_autorizacion_anticipo = db.Column(db.DateTime(timezone=True))
    numero_factura = db.Column(db.String(80))
    fecha_factura = db.Column(db.Date)
    fecha_vencimiento = db.Column(db.Date, index=True)
    moneda = db.Column(
        db.String(3), nullable=False, default="MXN", server_default="MXN"
    )
    notas = db.Column(db.Text)
    direccion_entrega = db.Column(db.String(500))
    direccion_entrega_confirmada_at = db.Column(db.DateTime(timezone=True))
    direccion_entrega_confirmada_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issued_by_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    issued_at = db.Column(db.DateTime(timezone=True))
    delivery_notified_at = db.Column(db.DateTime(timezone=True))
    payment_due_notified_on = db.Column(db.Date)
    version_actual = db.Column(
        db.Integer, nullable=False, default=1, server_default="1"
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=db.func.now(),
    )

    project = db.relationship("CentroCosto")
    requisition = db.relationship("PurchaseRequisition", back_populates="legacy_orders")
    quotation = db.relationship("Quotation", back_populates="orders")
    supplier = db.relationship("Supplier", back_populates="orders")
    company = db.relationship("Company")
    buyer = db.relationship("Usuario", foreign_keys=[buyer_id])
    payment_method = db.relationship("PaymentMethod", back_populates="orders")
    advance_authorizer = db.relationship(
        "Usuario", foreign_keys=[autorizado_anticipo_por_id]
    )
    beneficiary_validator = db.relationship(
        "Usuario", foreign_keys=[beneficiario_validado_por_id]
    )
    created_by = db.relationship("Usuario", foreign_keys=[created_by_id])
    issued_by = db.relationship("Usuario", foreign_keys=[issued_by_id])
    delivery_address_confirmer = db.relationship(
        "Usuario",
        foreign_keys=[direccion_entrega_confirmada_por_id],
    )
    lines = db.relationship(
        "PurchaseOrderLine",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderLine.id",
    )
    receipts = db.relationship(
        "GoodsReceipt",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="GoodsReceipt.fecha",
    )
    payment_schedules = db.relationship(
        "PurchaseOrderPaymentSchedule",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderPaymentSchedule.secuencia",
    )
    revisions = db.relationship(
        "PurchaseOrderRevision",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderRevision.version",
    )
    advance_movements_out = db.relationship(
        "SupplierAdvanceMovement",
        foreign_keys="SupplierAdvanceMovement.source_order_id",
        back_populates="source_order",
        cascade="all, delete-orphan",
    )
    advance_movements_in = db.relationship(
        "SupplierAdvanceMovement",
        foreign_keys="SupplierAdvanceMovement.target_order_id",
        back_populates="target_order",
    )

    __table_args__ = (
        CheckConstraint(
            "estado IN ('BORRADOR','PENDIENTE_AUTORIZACION','EMITIDA','PENDIENTE_ANTICIPO','ANTICIPO_AUTORIZADO','ANTICIPO_PARCIAL','ANTICIPO_PAGADO','RECEPCION_PARCIAL','RECEPCION_TOTAL','CERRADA','CANCELADA')",
            name="ck_purchase_order_status",
        ),
        CheckConstraint(
            "modalidad_pago IN ('CREDITO','ANTICIPO','PAGO_CONTRA_ENTREGA')",
            name="ck_purchase_order_payment_mode",
        ),
        CheckConstraint(
            "condicion_saldo IN ('CONTRA_RECEPCION','CONTRA_ENTREGA_TOTAL')",
            name="ck_purchase_order_balance_condition",
        ),
        CheckConstraint("anticipo_monto >= 0", name="ck_purchase_order_advance"),
        CheckConstraint(
            "anticipo_porcentaje >= 0 AND anticipo_porcentaje <= 100",
            name="ck_purchase_order_advance_percentage",
        ),
        CheckConstraint(
            "anticipo_pendiente >= 0", name="ck_purchase_order_advance_pending"
        ),
        CheckConstraint("moneda = 'MXN'", name="ck_purchase_order_currency_mxn"),
    )

    @property
    def subtotal_sin_iva(self) -> Decimal:
        return money(sum((line.importe_sin_iva for line in self.lines), Decimal("0")))

    @property
    def iva(self) -> Decimal:
        return money(self.subtotal_sin_iva * Decimal("0.16"))

    @property
    def total_con_iva(self) -> Decimal:
        return money(self.subtotal_sin_iva + self.iva)

    @property
    def es_operaciones(self) -> bool:
        return self.tipo_oc == "OPERACIONES"

    @property
    def estado_visible(self) -> str:
        if self.estado == "BORRADOR" and self.requiere_autorizacion:
            return "PENDIENTE_AUTORIZACION"
        return self.estado

    @property
    def beneficiario_nombre(self) -> str:
        if self.supplier:
            return self.supplier.nombre
        return self.beneficiario_libre or "Beneficiario pendiente"

    @property
    def monto_pagado_directo(self) -> Decimal:
        from nominas_models import AdditionalPayment

        return money(
            db.session.query(db.func.coalesce(db.func.sum(AdditionalPayment.monto_sin_iva), 0))
            .filter(AdditionalPayment.purchase_order_id == self.id)
            .scalar()
        )

    @property
    def saldo_aplicado_entrada(self) -> Decimal:
        return money(
            sum(
                (
                    decimal_value(movement.monto)
                    for movement in self.advance_movements_in
                    if movement.tipo == "APLICACION"
                ),
                Decimal("0"),
            )
        )

    @property
    def saldo_aplicado_salida(self) -> Decimal:
        return money(
            sum(
                (decimal_value(movement.monto) for movement in self.advance_movements_out),
                Decimal("0"),
            )
        )

    @property
    def monto_pagado(self) -> Decimal:
        return max(
            Decimal("0.00"),
            money(
                self.monto_pagado_directo
                + self.saldo_aplicado_entrada
                - self.saldo_aplicado_salida
            ),
        )

    @property
    def saldo_favor_disponible(self) -> Decimal:
        if self.modalidad_pago != "ANTICIPO":
            return Decimal("0.00")
        return max(
            Decimal("0.00"),
            money(
                self.monto_pagado_directo
                - self.monto_recibido
                - self.saldo_aplicado_salida
            ),
        )

    @property
    def saldo_pendiente(self) -> Decimal:
        return max(Decimal("0.00"), money(self.subtotal_sin_iva - self.monto_pagado))

    @property
    def monto_recibido(self) -> Decimal:
        return money(
            sum(
                (
                    line.cantidad_recibida
                    * decimal_value(line.precio_unitario_sin_iva)
                    for line in self.lines
                ),
                Decimal("0"),
            )
        )

    @property
    def monto_consumido_real(self) -> Decimal:
        """Importe que ya reúne las dos condiciones: recepción y pago.

        Un anticipo autorizado puede estar pagado antes de recibir material,
        pero continúa comprometido hasta que la recepción lo respalde.
        """

        return money(min(self.monto_pagado, self.monto_recibido))

    @property
    def saldo_comprometido(self) -> Decimal:
        """Parte comprada por OC que aún no se convierte en consumo real."""

        return max(
            Decimal("0.00"),
            money(self.subtotal_sin_iva - self.monto_consumido_real),
        )

    @property
    def limite_pagable(self) -> Decimal:
        if self.modalidad_pago == "ANTICIPO" and self.estado in {
            "ANTICIPO_AUTORIZADO",
            "ANTICIPO_PARCIAL",
            "ANTICIPO_PAGADO",
        }:
            return max(decimal_value(self.anticipo_monto), self.monto_recibido)
        return self.monto_recibido

    @property
    def saldo_pagable(self) -> Decimal:
        return max(
            Decimal("0.00"),
            money(min(self.subtotal_sin_iva, self.limite_pagable) - self.monto_pagado),
        )

    @property
    def porcentaje_recepcion(self) -> Decimal:
        ordered = sum((decimal_value(line.cantidad) for line in self.lines), Decimal("0"))
        if not ordered:
            return Decimal("0")
        received = sum((line.cantidad_recibida for line in self.lines), Decimal("0"))
        return received / ordered

    @property
    def requisitions(self):
        requisitions = {}
        for line in self.lines:
            if line.requisition_line and line.requisition_line.requisition:
                req = line.requisition_line.requisition
                requisitions[req.id] = req
        return list(requisitions.values())

    def semaforo_vencimiento(self, today: date | None = None) -> str:
        if not self.fecha_vencimiento or self.saldo_pendiente <= 0:
            return "SIN_FECHA"
        current = today or date.today()
        days = (self.fecha_vencimiento - current).days
        if days <= 3:
            return "ROJO"
        if days <= 7:
            return "AMARILLO"
        return "VERDE"


class PurchaseOrderPaymentSchedule(db.Model):
    """Programación financiera; nunca equivale por sí sola a un pago."""

    __tablename__ = "purchase_order_payment_schedules"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    secuencia = db.Column(db.Integer, nullable=False)
    tipo = db.Column(db.String(10), nullable=False)
    condicion = db.Column(db.String(24), nullable=False)
    monto_programado = db.Column(db.Numeric(14, 2), nullable=False)
    porcentaje = db.Column(
        db.Numeric(7, 4), nullable=False, default=0, server_default="0"
    )
    estado = db.Column(
        db.String(24),
        nullable=False,
        default="SOLICITADO",
        server_default="SOLICITADO",
        index=True,
    )
    monto_pagado = db.Column(
        db.Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    solicitado_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    autorizado_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    fecha_solicitud = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )
    fecha_autorizacion = db.Column(db.DateTime(timezone=True))
    fecha_pago = db.Column(db.DateTime(timezone=True))
    justificacion = db.Column(db.String(500))

    order = db.relationship("PurchaseOrder", back_populates="payment_schedules")
    solicitado_por = db.relationship("Usuario", foreign_keys=[solicitado_por_id])
    autorizado_por = db.relationship("Usuario", foreign_keys=[autorizado_por_id])
    payments = db.relationship(
        "AdditionalPayment",
        back_populates="payment_schedule",
        foreign_keys="AdditionalPayment.payment_schedule_id",
    )

    __table_args__ = (
        UniqueConstraint(
            "order_id", "secuencia", name="uq_order_payment_schedule_sequence"
        ),
        CheckConstraint(
            "tipo IN ('ANTICIPO','SALDO')",
            name="ck_order_payment_schedule_type",
        ),
        CheckConstraint(
            "condicion IN ('SOLICITADO','CONTRA_RECEPCION','CONTRA_ENTREGA_TOTAL')",
            name="ck_order_payment_schedule_condition",
        ),
        CheckConstraint(
            "estado IN ('SOLICITADO','PENDIENTE_RECEPCION','AUTORIZADO','PARCIAL','PAGADO','CANCELADO')",
            name="ck_order_payment_schedule_status",
        ),
        CheckConstraint(
            "monto_programado >= 0 AND monto_pagado >= 0 "
            "AND monto_pagado <= monto_programado",
            name="ck_order_payment_schedule_amounts",
        ),
        CheckConstraint(
            "porcentaje >= 0 AND porcentaje <= 100",
            name="ck_order_payment_schedule_percentage",
        ),
    )

    @property
    def pendiente(self) -> Decimal:
        return max(
            Decimal("0.00"),
            money(
                decimal_value(self.monto_programado)
                - decimal_value(self.monto_pagado)
            ),
        )

    @property
    def monto_liberado(self) -> Decimal:
        """Monto que puede pagar Finanzas conforme a autorización/recepción."""

        if self.estado in {"CANCELADO", "PAGADO"}:
            return Decimal("0.00")
        if self.tipo == "ANTICIPO":
            if self.estado not in {"AUTORIZADO", "PARCIAL"}:
                return Decimal("0.00")
            return self.pendiente
        if self.condicion == "CONTRA_ENTREGA_TOTAL":
            if self.order.porcentaje_recepcion < Decimal("1"):
                return Decimal("0.00")
            total_liberado = self.order.subtotal_sin_iva
        else:
            total_liberado = self.order.monto_recibido
        anticipos = money(
            sum(
                (
                    decimal_value(item.monto_pagado)
                    for item in self.order.payment_schedules
                    if item.tipo == "ANTICIPO"
                ),
                Decimal("0"),
            )
        )
        saldo_liberado = max(
            Decimal("0.00"), money(total_liberado - anticipos)
        )
        return max(
            Decimal("0.00"),
            money(
                min(decimal_value(self.monto_programado), saldo_liberado)
                - decimal_value(self.monto_pagado)
            ),
        )


class PurchaseOrderRevision(db.Model):
    """Versión inmutable de un cambio posterior a la emisión de una OC."""

    __tablename__ = "purchase_order_revisions"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = db.Column(db.Integer, nullable=False)
    motivo = db.Column(db.String(500), nullable=False)
    valores_anteriores = db.Column(db.JSON, nullable=False)
    valores_nuevos = db.Column(db.JSON, nullable=False)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    order = db.relationship("PurchaseOrder", back_populates="revisions")
    usuario = db.relationship("Usuario")

    __table_args__ = (
        UniqueConstraint(
            "order_id", "version", name="uq_purchase_order_revision_version"
        ),
        CheckConstraint("version > 1", name="ck_purchase_order_revision_version"),
    )


class PurchaseOrderLine(db.Model):
    __tablename__ = "purchase_order_lines"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    requisition_line_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_requisition_lines.id", ondelete="SET NULL"),
        # La primera versión de Compras admitió renglones históricos sin
        # requisición. Las rutas nuevas nunca crean ese caso, pero el modelo lo
        # conserva para no invalidar información ya existente.
        nullable=True,
    )
    explosion_item_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_explosion_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cantidad = db.Column(db.Numeric(16, 4), nullable=False)
    precio_unitario_sin_iva = db.Column(db.Numeric(16, 4), nullable=False)
    importe_sin_iva = db.Column(db.Numeric(14, 2), nullable=False)
    notas = db.Column(db.String(240))
    clasificacion_explosion = db.Column(db.String(40))
    observacion_operativa = db.Column(db.String(500))
    smnc_id = db.Column(
        db.Integer,
        db.ForeignKey("material_change_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    order = db.relationship("PurchaseOrder", back_populates="lines")
    requisition_line = db.relationship(
        "PurchaseRequisitionLine", back_populates="order_lines"
    )
    explosion_item = db.relationship("BudgetExplosionItem", back_populates="order_lines")
    smnc = db.relationship("MaterialChangeRequest")
    receipt_lines = db.relationship(
        "GoodsReceiptLine", back_populates="order_line", cascade="all, delete-orphan"
    )
    payments = db.relationship(
        "AdditionalPayment",
        back_populates="purchase_order_line",
        foreign_keys="AdditionalPayment.purchase_order_line_id",
    )
    advance_movements_out = db.relationship(
        "SupplierAdvanceMovement",
        foreign_keys="SupplierAdvanceMovement.source_order_line_id",
        back_populates="source_order_line",
    )
    advance_movements_in = db.relationship(
        "SupplierAdvanceMovement",
        foreign_keys="SupplierAdvanceMovement.target_order_line_id",
        back_populates="target_order_line",
    )

    __table_args__ = (
        UniqueConstraint(
            "order_id", "requisition_line_id", name="uq_order_requisition_line"
        ),
        CheckConstraint("cantidad > 0", name="ck_purchase_order_line_quantity"),
        CheckConstraint(
            "precio_unitario_sin_iva >= 0", name="ck_purchase_order_line_price"
        ),
        CheckConstraint(
            "importe_sin_iva >= 0", name="ck_purchase_order_line_amount"
        ),
    )

    @property
    def cantidad_recibida(self) -> Decimal:
        return sum(
            (decimal_value(line.cantidad_recibida) for line in self.receipt_lines),
            Decimal("0"),
        )

    @property
    def cantidad_pendiente(self) -> Decimal:
        return max(Decimal("0"), decimal_value(self.cantidad) - self.cantidad_recibida)

    @property
    def monto_pagado_directo(self) -> Decimal:
        return money(
            sum((decimal_value(payment.monto_sin_iva) for payment in self.payments), Decimal("0"))
        )

    @property
    def monto_pagado_efectivo(self) -> Decimal:
        incoming = sum(
            (
                decimal_value(movement.monto)
                for movement in self.advance_movements_in
                if movement.tipo == "APLICACION"
            ),
            Decimal("0"),
        )
        outgoing = sum(
            (decimal_value(movement.monto) for movement in self.advance_movements_out),
            Decimal("0"),
        )
        return max(
            Decimal("0.00"), money(self.monto_pagado_directo + incoming - outgoing)
        )

    @property
    def monto_recibido(self) -> Decimal:
        return money(
            self.cantidad_recibida * decimal_value(self.precio_unitario_sin_iva)
        )

    @property
    def saldo_favor_disponible(self) -> Decimal:
        if not self.order or self.order.modalidad_pago != "ANTICIPO":
            return Decimal("0.00")
        outgoing = sum(
            (decimal_value(movement.monto) for movement in self.advance_movements_out),
            Decimal("0"),
        )
        return max(
            Decimal("0.00"),
            money(self.monto_pagado_directo - self.monto_recibido - outgoing),
        )


class GoodsReceipt(db.Model):
    """Recepción física confirmada por supervisor/capturista."""

    __tablename__ = "goods_receipts"

    id = db.Column(db.Integer, primary_key=True)
    folio = db.Column(db.String(30), nullable=False, unique=True, index=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    fecha = db.Column(db.Date, nullable=False)
    tipo = db.Column(db.String(10), nullable=False)
    documento_proveedor = db.Column(db.String(80))
    fecha_factura = db.Column(db.Date)
    notas = db.Column(db.Text)
    notification_email_sent_at = db.Column(db.DateTime(timezone=True))
    notification_email_error = db.Column(db.String(500))
    received_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    order = db.relationship("PurchaseOrder", back_populates="receipts")
    received_by = db.relationship("Usuario")
    lines = db.relationship(
        "GoodsReceiptLine", back_populates="receipt", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("tipo IN ('PARCIAL','TOTAL')", name="ck_goods_receipt_type"),
    )


class GoodsReceiptLine(db.Model):
    __tablename__ = "goods_receipt_lines"

    id = db.Column(db.Integer, primary_key=True)
    receipt_id = db.Column(
        db.Integer,
        db.ForeignKey("goods_receipts.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_line_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cantidad_recibida = db.Column(db.Numeric(16, 4), nullable=False)
    notas = db.Column(db.String(240))

    receipt = db.relationship("GoodsReceipt", back_populates="lines")
    order_line = db.relationship("PurchaseOrderLine", back_populates="receipt_lines")

    __table_args__ = (
        UniqueConstraint("receipt_id", "order_line_id", name="uq_receipt_order_line"),
        CheckConstraint(
            "cantidad_recibida > 0", name="ck_goods_receipt_line_quantity"
        ),
    )


class MaterialChangeRequest(db.Model):
    """Solicitud de material no contemplado (SMNC)."""

    __tablename__ = "material_change_requests"

    id = db.Column(db.Integer, primary_key=True)
    folio = db.Column(db.String(30), nullable=False, unique=True, index=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey("centros_costo.id", ondelete="RESTRICT"), nullable=False
    )
    garantia_id = db.Column(
        db.Integer,
        db.ForeignKey("garantias_obras.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    estado = db.Column(
        db.String(22),
        nullable=False,
        default="PENDIENTE_AUTORIZACION",
        server_default="PENDIENTE_AUTORIZACION",
    )
    requested_by_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    rejection_reason = db.Column(db.String(300))
    approved_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    project = db.relationship("CentroCosto")
    garantia = db.relationship("GarantiaObra", back_populates="smnc")
    requested_by = db.relationship("Usuario", foreign_keys=[requested_by_id])
    approved_by = db.relationship("Usuario", foreign_keys=[approved_by_id])
    details = db.relationship(
        "MaterialChangeRequestLine",
        back_populates="request",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "estado IN ('PENDIENTE_AUTORIZACION','APROBADA','RECHAZADA')",
            name="ck_material_change_request_status",
        ),
    )

    @property
    def total_estimado(self) -> Decimal:
        return money(sum((line.importe_estimado for line in self.details), Decimal("0")))


class MaterialChangeRequestLine(db.Model):
    __tablename__ = "material_change_request_lines"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer,
        db.ForeignKey("material_change_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    budget_item_id = db.Column(
        db.Integer, db.ForeignKey("budget_items.id", ondelete="RESTRICT"), nullable=False
    )
    existing_explosion_item_id = db.Column(
        db.Integer, db.ForeignKey("budget_explosion_items.id", ondelete="SET NULL")
    )
    action_type = db.Column(db.String(10), nullable=False)
    supply_key = db.Column(db.String(40))
    supply_type = db.Column(db.String(20), nullable=False)
    clasificacion = db.Column(
        db.String(40), nullable=False, default="NORMAL", server_default="NORMAL"
    )
    descripcion = db.Column(db.String(180), nullable=False)
    unidad = db.Column(db.String(20), nullable=False)
    cantidad = db.Column(db.Numeric(16, 4), nullable=False)
    precio_estimado = db.Column(db.Numeric(16, 4), nullable=False)
    justificacion_tipo = db.Column(db.String(30), nullable=False)
    justificacion = db.Column(db.String(500), nullable=False)
    generated_explosion_item_id = db.Column(
        db.Integer, db.ForeignKey("budget_explosion_items.id", ondelete="SET NULL")
    )

    request = db.relationship("MaterialChangeRequest", back_populates="details")
    budget_item = db.relationship("BudgetItem")
    existing_explosion_item = db.relationship(
        "BudgetExplosionItem", foreign_keys=[existing_explosion_item_id]
    )
    generated_explosion_item = db.relationship(
        "BudgetExplosionItem", foreign_keys=[generated_explosion_item_id]
    )

    __table_args__ = (
        CheckConstraint(
            "action_type IN ('NUEVO','AUMENTO')", name="ck_smnc_action_type"
        ),
        CheckConstraint("cantidad > 0", name="ck_smnc_quantity"),
        CheckConstraint("precio_estimado >= 0", name="ck_smnc_price"),
        CheckConstraint(
            "justificacion_tipo IN ('MATERIAL_NO_CONTEMPLADO','ERROR_CUANTIFICACION','CAMBIO_PROYECTO')",
            name="ck_smnc_justification_type",
        ),
        CheckConstraint(
            "clasificacion IN ('NORMAL','OPERATIVO','EQUIPO_ESPECIAL','ELECTRODOMESTICO')",
            name="ck_smnc_classification",
        ),
    )

    @property
    def importe_estimado(self) -> Decimal:
        return money(decimal_value(self.cantidad) * decimal_value(self.precio_estimado))


class PurchaseNotification(db.Model):
    """Notificación interna; no depende de un servicio externo."""

    __tablename__ = "purchase_notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    tipo = db.Column(db.String(50), nullable=False)
    mensaje = db.Column(db.String(500), nullable=False)
    enlace = db.Column(db.String(300))
    leida = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )

    user = db.relationship("Usuario")


class SupplierAdvanceMovement(db.Model):
    """Aplicación o reembolso de un saldo a favor originado por anticipo."""

    __tablename__ = "supplier_advance_movements"

    id = db.Column(db.Integer, primary_key=True)
    source_order_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_order_line_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_order_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
    )
    target_order_line_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"),
    )
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    company_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payment_method_id = db.Column(
        db.Integer,
        db.ForeignKey("payment_methods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tipo = db.Column(db.String(12), nullable=False)
    fecha = db.Column(db.Date, nullable=False, index=True)
    monto = db.Column(db.Numeric(14, 2), nullable=False)
    referencia = db.Column(db.String(120))
    notas = db.Column(db.String(500))
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    source_order = db.relationship(
        "PurchaseOrder",
        foreign_keys=[source_order_id],
        back_populates="advance_movements_out",
    )
    source_order_line = db.relationship(
        "PurchaseOrderLine",
        foreign_keys=[source_order_line_id],
        back_populates="advance_movements_out",
    )
    target_order = db.relationship(
        "PurchaseOrder",
        foreign_keys=[target_order_id],
        back_populates="advance_movements_in",
    )
    target_order_line = db.relationship(
        "PurchaseOrderLine",
        foreign_keys=[target_order_line_id],
        back_populates="advance_movements_in",
    )
    supplier = db.relationship("Supplier")
    company = db.relationship("Company")
    payment_method = db.relationship("PaymentMethod")
    created_by = db.relationship("Usuario")

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('APLICACION','REEMBOLSO')", name="ck_supplier_advance_type"
        ),
        CheckConstraint("monto > 0", name="ck_supplier_advance_amount"),
        CheckConstraint(
            "(tipo = 'APLICACION' AND target_order_id IS NOT NULL AND target_order_line_id IS NOT NULL) "
            "OR (tipo = 'REEMBOLSO' AND target_order_id IS NULL AND target_order_line_id IS NULL)",
            name="ck_supplier_advance_target",
        ),
    )


class CreditCard(db.Model):
    """Tarjeta de una empresa pagadora; nunca almacena el número completo."""

    __tablename__ = "tarjetas_credito"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    numero_tarjeta = db.Column(db.String(30), nullable=False)
    fecha_corte = db.Column(db.Date, nullable=False, index=True)
    fecha_pago = db.Column(db.Date, nullable=False, index=True)
    limite_credito = db.Column(db.Numeric(14, 2), nullable=False)
    saldo_actual = db.Column(
        db.Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    activa = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    payment_due_notified_on = db.Column(db.Date)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    empresa = db.relationship("Company")
    pagos = db.relationship(
        "CreditCardPayment",
        back_populates="tarjeta",
        cascade="all, delete-orphan",
        order_by="CreditCardPayment.fecha.desc()",
    )

    __table_args__ = (
        CheckConstraint(
            "limite_credito >= 0", name="ck_credit_card_credit_limit"
        ),
        CheckConstraint("saldo_actual >= 0", name="ck_credit_card_balance"),
        CheckConstraint(
            "fecha_pago >= fecha_corte", name="ck_credit_card_cycle_dates"
        ),
    )

    @property
    def disponible(self) -> Decimal:
        return money(decimal_value(self.limite_credito) - decimal_value(self.saldo_actual))

    def dias_para_pago(self, today: date | None = None) -> int:
        return (self.fecha_pago - (today or date.today())).days


class CreditCardPayment(db.Model):
    """Pago aplicado a una tarjeta con saldos antes/después auditables."""

    __tablename__ = "tarjetas_credito_pagos"

    id = db.Column(db.Integer, primary_key=True)
    tarjeta_id = db.Column(
        db.Integer,
        db.ForeignKey("tarjetas_credito.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fecha = db.Column(db.Date, nullable=False, index=True)
    monto = db.Column(db.Numeric(14, 2), nullable=False)
    saldo_anterior = db.Column(db.Numeric(14, 2), nullable=False)
    saldo_nuevo = db.Column(db.Numeric(14, 2), nullable=False)
    referencia = db.Column(db.String(120))
    notas = db.Column(db.String(500))
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    tarjeta = db.relationship("CreditCard", back_populates="pagos")
    created_by = db.relationship("Usuario")

    __table_args__ = (
        CheckConstraint("monto > 0", name="ck_credit_card_payment_amount"),
        CheckConstraint(
            "saldo_anterior >= 0 AND saldo_nuevo >= 0",
            name="ck_credit_card_payment_balances",
        ),
    )


class PurchaseAlertRun(db.Model):
    """Bitácora que garantiza una sola ejecución automática por día."""

    __tablename__ = "purchase_alert_runs"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, unique=True, index=True)
    requisiciones_vencidas = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    entregas_vencidas = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    pagos_por_vencer = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    tarjetas_por_vencer = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    executed_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )


# Alias que coinciden con los nombres funcionales usados en el documento.
BudgetInsumo = BudgetExplosionItem
Requisicion = PurchaseRequisition
RequisicionDetalle = PurchaseRequisitionLine
Cotizacion = Quotation
CotizacionDetalle = QuotationLine
OrdenCompra = PurchaseOrder
OrdenCompraDetalle = PurchaseOrderLine
Recepcion = GoodsReceipt
SMNC = MaterialChangeRequest
SMNCDetalle = MaterialChangeRequestLine
ProveedorInsumo = SupplierSupplyItem
