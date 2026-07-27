"""Modelos del módulo de nóminas recuperado de PythonAnywhere.

Las tablas y reglas monetarias conservan el diseño del sistema original del
17 de julio de 2026. Únicamente se sustituyeron sus tablas duplicadas de
usuarios y obras por ``Usuario`` y ``CentroCosto`` del ERP V2.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy import CheckConstraint, UniqueConstraint, event

from models import CentroCosto, Usuario, db, utc_now


MONEY_STEP = Decimal("0.01")


def decimal_value(value) -> Decimal:
    """Convierte importes de SQLAlchemy o formularios sin propagar nulos."""

    if value in (None, ""):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError, ValueError):
        return Decimal("0")


def money(value) -> Decimal:
    """Aplica el redondeo financiero usado por el sistema original."""

    return decimal_value(value).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


class Company(db.Model):
    """Empresa legal o bancaria desde la cual se efectúa un pago."""

    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    codigo = db.Column(db.String(20), nullable=False, unique=True)
    activa = db.Column(db.Boolean, nullable=False, default=True, server_default="1")


class WeeklyResourceAvailability(db.Model):
    """Fondos que Administración confirma como disponibles para una semana."""

    __tablename__ = "weekly_resource_availability"

    id = db.Column(db.Integer, primary_key=True)
    semana_inicio = db.Column(db.Date, nullable=False, index=True)
    metodo = db.Column(db.String(20), nullable=False)
    monto_disponible = db.Column(
        db.Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    updated_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    updated_by = db.relationship("Usuario")

    __table_args__ = (
        UniqueConstraint(
            "semana_inicio", "metodo", name="uq_weekly_resource_method"
        ),
        CheckConstraint(
            "metodo IN ('EFECTIVO','TRANSFERENCIA')",
            name="ck_weekly_resource_method",
        ),
        CheckConstraint(
            "monto_disponible >= 0", name="ck_weekly_resource_amount"
        ),
    )


class BudgetItem(db.Model):
    """Partida o subpartida de presupuesto; ``parent_id`` crea la jerarquía."""

    __tablename__ = "budget_items"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_items.id", ondelete="SET NULL"),
    )
    codigo = db.Column(db.String(40), nullable=False)
    nombre = db.Column(db.String(180), nullable=False)
    categoria = db.Column(
        db.String(25), nullable=False, default="MANO_OBRA", server_default="MANO_OBRA"
    )
    presupuesto = db.Column(
        db.Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    cantidad_objetivo = db.Column(
        db.Numeric(16, 4), nullable=False, default=0, server_default="0"
    )
    unidad_medida = db.Column(db.String(20))
    porcentaje_avance_real = db.Column(
        db.Numeric(6, 2), nullable=False, default=0, server_default="0"
    )
    activa = db.Column(db.Boolean, nullable=False, default=True, server_default="1")

    project = db.relationship("CentroCosto", back_populates="budget_items")
    parent = db.relationship("BudgetItem", remote_side=[id], backref="children")

    __table_args__ = (
        UniqueConstraint(
            "project_id", "codigo", name="uq_budget_code_project"
        ),
        CheckConstraint(
            "categoria IN ('MANO_OBRA','SUBCONTRATO','INDIRECTO','ADICIONAL')",
            name="ck_budget_category",
        ),
        CheckConstraint(
            "cantidad_objetivo >= 0",
            name="ck_budget_item_target_quantity",
        ),
        CheckConstraint(
            "porcentaje_avance_real >= 0 AND porcentaje_avance_real <= 100",
            name="ck_budget_item_progress",
        ),
    )

    @property
    def etiqueta(self):
        return f"{self.codigo} · {self.nombre}"


class Employee(db.Model):
    """Maestro de trabajadores y valores predeterminados de nómina.

    ``budget_item_id`` se conserva nullable únicamente por compatibilidad con
    instalaciones anteriores. La asignación presupuestaria operativa vive en
    cada ``PayrollLine`` y nunca se toma de este maestro.
    """

    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    nombre_completo = db.Column(db.String(180), nullable=False, index=True)
    fecha_ingreso = db.Column(db.Date, nullable=False)
    fecha_baja = db.Column(db.Date)
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    puesto = db.Column(db.String(120), nullable=False)
    cuadrilla = db.Column(db.String(100))
    supervisor = db.Column(db.String(120))
    empresa_operativa = db.Column(db.String(80))
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="SET NULL"),
    )
    budget_item_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_items.id", ondelete="SET NULL"),
    )
    salario_semanal = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )

    # El sueldo acordado es libre. IMSS es costo patronal y no se descuenta al
    # trabajador; Infonavit sí permanece como deducción personal.
    registrado_imss = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )
    nss = db.Column(db.String(30))
    empresa_imss_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="SET NULL"),
    )
    descuento_infonavit = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    imss_tipo = db.Column(
        db.String(15), nullable=False, default="FIJO", server_default="FIJO"
    )
    descuento_imss = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )

    transferencia_predeterminada = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    empresa_transferencia_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="SET NULL"),
    )
    empresa_efectivo_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="SET NULL"),
    )
    notas = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    project = db.relationship("CentroCosto")
    budget_item = db.relationship("BudgetItem")
    empresa_imss = db.relationship("Company", foreign_keys=[empresa_imss_id])
    empresa_transferencia = db.relationship(
        "Company", foreign_keys=[empresa_transferencia_id]
    )
    empresa_efectivo = db.relationship(
        "Company", foreign_keys=[empresa_efectivo_id]
    )

    __table_args__ = (
        CheckConstraint(
            "imss_tipo IN ('FIJO','PORCENTAJE')",
            name="ck_employee_imss_type",
        ),
    )


class Payroll(db.Model):
    """Encabezado de nómina de una obra u oficina para una semana."""

    __tablename__ = "payrolls"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
    )
    semana_inicio = db.Column(db.Date, nullable=False)
    semana_fin = db.Column(db.Date, nullable=False)
    estado = db.Column(
        db.String(15), nullable=False, default="borrador", server_default="borrador", index=True
    )
    notas = db.Column(db.Text)
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    closed_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )
    closed_at = db.Column(db.DateTime(timezone=True))
    paid_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    paid_at = db.Column(db.DateTime(timezone=True))
    reconciled_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    reconciled_at = db.Column(db.DateTime(timezone=True))

    project = db.relationship("CentroCosto")
    created_by = db.relationship("Usuario", foreign_keys=[created_by_id])
    closed_by = db.relationship("Usuario", foreign_keys=[closed_by_id])
    paid_by = db.relationship("Usuario", foreign_keys=[paid_by_id])
    reconciled_by = db.relationship("Usuario", foreign_keys=[reconciled_by_id])
    lines = db.relationship(
        "PayrollLine",
        back_populates="payroll",
        cascade="all, delete-orphan",
        order_by="PayrollLine.nombre_trabajador",
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "semana_inicio", name="uq_payroll_project_week"
        ),
        CheckConstraint(
            "estado IN ('borrador','enviada','aprobada','pagada','conciliada')",
            name="ck_payroll_status",
        ),
    )

    @property
    def total_devengado(self):
        return sum(
            (
                decimal_value(line.monto_devengado)
                + decimal_value(line.pago_extra)
                for line in self.lines
            ),
            Decimal("0"),
        )

    @property
    def total_neto(self):
        return sum(
            (decimal_value(line.neto_pagar) for line in self.lines),
            Decimal("0"),
        )

    @property
    def total_costo_mano_obra(self):
        return sum(
            (
                decimal_value(line.monto_devengado)
                + decimal_value(line.pago_extra)
                + decimal_value(line.descuento_imss)
                for line in self.lines
            ),
            Decimal("0"),
        )


class PayrollLine(db.Model):
    """Foto histórica de un trabajador dentro de una semana específica."""

    __tablename__ = "payroll_lines"

    id = db.Column(db.Integer, primary_key=True)
    payroll_id = db.Column(
        db.Integer,
        db.ForeignKey("payrolls.id", ondelete="CASCADE"),
        nullable=False,
    )
    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
    )
    budget_item_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    partida_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_items.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    subpartida_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_items.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    nombre_trabajador = db.Column(db.String(180), nullable=False)
    puesto = db.Column(db.String(120), nullable=False)
    cuadrilla = db.Column(db.String(100))
    supervisor = db.Column(db.String(120))
    empresa_operativa = db.Column(db.String(80))
    salario_semanal = db.Column(db.Numeric(12, 2), nullable=False)

    lunes = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    martes = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    miercoles = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    jueves = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    viernes = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    dias_trabajados = db.Column(
        db.Numeric(4, 2), nullable=False, default=5, server_default="5"
    )
    numero_faltas = db.Column(
        db.Numeric(4, 2), nullable=False, default=0, server_default="0"
    )
    sueldo_diario = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    descuento_faltas = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    monto_devengado = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )

    pago_extra = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    descuento_infonavit = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    descuento_imss = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    descuento_prestamo = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    otro_descuento = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    concepto_otro_descuento = db.Column(db.String(180))
    vales_gasolina = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )

    pago_transferencia = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    empresa_transferencia_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="RESTRICT"),
    )
    pago_efectivo = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    empresa_efectivo_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="RESTRICT"),
    )
    neto_pagar = db.Column(
        db.Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    notas = db.Column(db.Text)

    payroll = db.relationship("Payroll", back_populates="lines")
    employee = db.relationship("Employee")
    # ``budget_item`` representa el ítem efectivo legado: la subpartida cuando
    # existe o, en caso contrario, la partida. Se mantiene sincronizado para
    # no romper integraciones ni reportes históricos.
    budget_item = db.relationship("BudgetItem", foreign_keys=[budget_item_id])
    partida = db.relationship("BudgetItem", foreign_keys=[partida_id])
    subpartida = db.relationship("BudgetItem", foreign_keys=[subpartida_id])
    empresa_transferencia = db.relationship(
        "Company", foreign_keys=[empresa_transferencia_id]
    )
    empresa_efectivo = db.relationship(
        "Company", foreign_keys=[empresa_efectivo_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "payroll_id", "employee_id", name="uq_line_employee_payroll"
        ),
    )

    @property
    def partida_resuelta(self):
        """Partida raíz, incluyendo el fallback de filas históricas."""

        if self.partida is not None:
            return self.partida
        item = self.budget_item
        if item is None:
            return None
        return item.parent if item.parent_id is not None else item

    @property
    def subpartida_resuelta(self):
        """Subpartida explícita o la inferida del ítem histórico."""

        if self.subpartida is not None:
            return self.subpartida
        item = self.budget_item
        if item is not None and item.parent_id is not None:
            return item
        return None

    @property
    def budget_item_efectivo(self):
        """Ítem que recibe el consumo presupuestal de la línea."""

        return self.subpartida_resuelta or self.partida_resuelta

    @property
    def asignacion_presupuestaria(self) -> str:
        """Etiqueta legible de partida y subpartida."""

        partida = self.partida_resuelta
        subpartida = self.subpartida_resuelta
        if not partida:
            return "Sin asignar"
        if subpartida:
            return f"{partida.etiqueta} / {subpartida.etiqueta}"
        return partida.etiqueta


@event.listens_for(PayrollLine, "before_insert")
@event.listens_for(PayrollLine, "before_update")
def sync_payroll_line_budget_item(_mapper, _connection, line: PayrollLine) -> None:
    """Mantiene la llave histórica alineada con la selección semanal."""

    if line.subpartida_id is not None:
        line.budget_item_id = line.subpartida_id
    elif line.partida_id is not None:
        line.budget_item_id = line.partida_id


class Loan(db.Model):
    __tablename__ = "loans"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Fotografía de la obra al momento de entregar el capital. El trabajador
    # puede cambiar de obra después; los reportes históricos no deben moverse
    # con su asignación actual.
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        index=True,
    )
    fecha_prestamo = db.Column(db.Date, nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    tasa_interes = db.Column(
        db.Float, nullable=False, default=5.0, server_default="5.0"
    )
    total_pagar = db.Column(db.Numeric(12, 2), nullable=False)
    retencion_semanal = db.Column(db.Numeric(12, 2), nullable=False)
    metodo_entrega = db.Column(
        db.String(20), nullable=False, default="EFECTIVO", server_default="EFECTIVO"
    )
    payment_method_id = db.Column(
        db.Integer,
        db.ForeignKey("payment_methods.id"),
        index=True,
    )
    company_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="SET NULL"),
    )
    concepto = db.Column(db.String(220))
    estado = db.Column(
        db.String(15), nullable=False, default="pendiente", server_default="pendiente", index=True
    )
    solicitante_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    aprobador_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
    )
    fecha_aprobacion = db.Column(db.DateTime(timezone=True))
    motivo_rechazo = db.Column(db.String(500))
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    employee = db.relationship("Employee")
    project = db.relationship("CentroCosto")
    company = db.relationship("Company")
    payment_method = db.relationship("PaymentMethod")
    created_by = db.relationship("Usuario", foreign_keys=[created_by_id])
    solicitante = db.relationship("Usuario", foreign_keys=[solicitante_id])
    aprobador = db.relationship("Usuario", foreign_keys=[aprobador_id])
    payments = db.relationship(
        "LoanPayment", back_populates="loan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("monto > 0", name="ck_loan_amount"),
        CheckConstraint("tasa_interes >= 0", name="ck_loan_interest"),
        CheckConstraint("total_pagar >= monto", name="ck_loan_total"),
        CheckConstraint("retencion_semanal > 0", name="ck_loan_weekly"),
        CheckConstraint(
            "metodo_entrega IN ('EFECTIVO','TRANSFERENCIA')",
            name="ck_loan_delivery_method",
        ),
        CheckConstraint(
            "estado IN ('pendiente','aprobado','rechazado','activo','liquidado')",
            name="ck_loan_status",
        ),
    )

    @property
    def abonado(self):
        return sum(
            (decimal_value(payment.monto) for payment in self.payments),
            Decimal("0"),
        )

    @property
    def restante(self):
        """Alias histórico del saldo pendiente, ahora incluyendo intereses."""

        return self.saldo_pendiente

    @property
    def empresa_entrega_id(self):
        """Alias de negocio de la FK histórica ``company_id``."""

        return self.company_id

    @empresa_entrega_id.setter
    def empresa_entrega_id(self, value):
        self.company_id = value

    @property
    def empresa_entrega(self):
        return self.company

    @property
    def obra_entrega(self):
        """Obra fotografiada, con fallback para filas históricas."""

        return self.project or (self.employee.project if self.employee else None)

    @property
    def saldo_pendiente(self):
        return max(Decimal("0"), money(self.total_pagar) - self.abonado)

    def calcular_total_pagar(self):
        """Fija el total contractual con redondeo monetario a centavos."""

        tasa = decimal_value(self.tasa_interes if self.tasa_interes is not None else 5)
        self.tasa_interes = float(tasa)
        self.total_pagar = money(
            decimal_value(self.monto) * (Decimal("1") + tasa / Decimal("100"))
        )
        return self.total_pagar


@event.listens_for(Loan, "before_insert")
def calculate_new_loan_total(_mapper, _connection, loan: Loan) -> None:
    """Garantiza el cálculo incluso en altas hechas fuera de las rutas web."""

    if loan.solicitante_id is None:
        loan.solicitante_id = loan.created_by_id
    if loan.total_pagar is None:
        loan.calcular_total_pagar()


class LoanPayment(db.Model):
    __tablename__ = "loan_payments"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(
        db.Integer,
        db.ForeignKey("loans.id", ondelete="CASCADE"),
        nullable=False,
    )
    payroll_line_id = db.Column(
        db.Integer,
        db.ForeignKey("payroll_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    loan = db.relationship("Loan", back_populates="payments")
    payroll_line = db.relationship("PayrollLine")

    __table_args__ = (
        UniqueConstraint(
            "loan_id", "payroll_line_id", name="uq_loan_line_payment"
        ),
    )


class AdditionalPayment(db.Model):
    __tablename__ = "additional_payments"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
    )
    budget_item_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Estos vínculos se incorporan en Compras. Permanecen anulables para
    # conservar pagos históricos capturados antes de existir la explosión.
    explosion_item_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_explosion_items.id", ondelete="RESTRICT"),
        index=True,
    )
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="RESTRICT"),
        index=True,
    )
    purchase_order_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        index=True,
    )
    purchase_order_line_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_order_lines.id"),
        index=True,
    )
    payment_method_id = db.Column(
        db.Integer,
        db.ForeignKey("payment_methods.id", ondelete="SET NULL"),
        index=True,
    )
    payment_schedule_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "purchase_order_payment_schedules.id", ondelete="SET NULL"
        ),
        index=True,
    )
    beneficiario = db.Column(db.String(180), nullable=False)
    concepto = db.Column(db.String(240), nullable=False)
    monto_capturado = db.Column(db.Numeric(12, 2), nullable=False)
    tipo_monto = db.Column(
        db.String(15), nullable=False, default="SIN_IVA", server_default="SIN_IVA"
    )
    monto_sin_iva = db.Column(db.Numeric(12, 2), nullable=False)
    metodo_pago = db.Column(db.String(20), nullable=False)
    company_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    notas = db.Column(db.Text)
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
    explosion_item = db.relationship("BudgetExplosionItem")
    supplier = db.relationship("Supplier")
    purchase_order = db.relationship("PurchaseOrder")
    purchase_order_line = db.relationship(
        "PurchaseOrderLine", back_populates="payments", foreign_keys=[purchase_order_line_id]
    )
    payment_method = db.relationship("PaymentMethod")
    payment_schedule = db.relationship(
        "PurchaseOrderPaymentSchedule",
        back_populates="payments",
        foreign_keys=[payment_schedule_id],
    )
    company = db.relationship("Company")
    created_by = db.relationship("Usuario")


class Contractor(db.Model):
    __tablename__ = "contractors"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(180), nullable=False, unique=True)
    especialidad = db.Column(db.String(140))
    telefono = db.Column(db.String(50))
    email = db.Column(db.String(180))
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    notas = db.Column(db.Text)


class Subcontract(db.Model):
    __tablename__ = "subcontracts"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
    )
    budget_item_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    contractor_id = db.Column(
        db.Integer,
        db.ForeignKey("contractors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    especialidad = db.Column(db.String(140), nullable=False)
    presupuesto_sin_iva = db.Column(db.Numeric(14, 2), nullable=False)
    avance_fisico = db.Column(
        db.Numeric(6, 4), nullable=False, default=0, server_default="0"
    )
    umbral_alerta = db.Column(
        db.Numeric(6, 4), nullable=False, default=Decimal("0.15"), server_default="0.15"
    )
    observaciones = db.Column(db.Text)
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    project = db.relationship("CentroCosto")
    budget_item = db.relationship("BudgetItem")
    contractor = db.relationship("Contractor")
    payments = db.relationship(
        "SubcontractPayment",
        back_populates="subcontract",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "contractor_id",
            "especialidad",
            name="uq_subcontract_scope",
        ),
    )

    @property
    def pagado_sin_iva(self):
        return sum(
            (decimal_value(payment.monto_sin_iva) for payment in self.payments),
            Decimal("0"),
        )

    @property
    def comprometido(self):
        return money(
            decimal_value(self.presupuesto_sin_iva)
            * decimal_value(self.avance_fisico)
        )

    @property
    def saldo_vs_avance(self):
        return money(self.comprometido - self.pagado_sin_iva)

    @property
    def saldo_total(self):
        return money(decimal_value(self.presupuesto_sin_iva) - self.pagado_sin_iva)

    @property
    def porcentaje_pagado(self):
        presupuesto = decimal_value(self.presupuesto_sin_iva)
        return Decimal("0") if presupuesto == 0 else self.pagado_sin_iva / presupuesto

    @property
    def proximo_pago_sugerido(self):
        return max(Decimal("0"), self.saldo_vs_avance)

    @property
    def estatus_control(self):
        presupuesto = decimal_value(self.presupuesto_sin_iva)
        saldo = self.saldo_vs_avance
        if saldo < Decimal("-1"):
            return "PAGO SOBREESTIMADO"
        if presupuesto and saldo / presupuesto > decimal_value(self.umbral_alerta):
            return "FALTA DE PAGO"
        if decimal_value(self.avance_fisico) > 0 and self.pagado_sin_iva == 0:
            return "SIN PAGO"
        if abs(saldo) <= Decimal("1"):
            return "EXACTO"
        return "EN CONTROL"


class SubcontractPayment(db.Model):
    __tablename__ = "subcontract_payments"

    id = db.Column(db.Integer, primary_key=True)
    subcontract_id = db.Column(
        db.Integer,
        db.ForeignKey("subcontracts.id", ondelete="CASCADE"),
        nullable=False,
    )
    fecha = db.Column(db.Date, nullable=False)
    concepto = db.Column(db.String(180), nullable=False)
    monto_capturado = db.Column(db.Numeric(12, 2), nullable=False)
    tipo_monto = db.Column(
        db.String(15), nullable=False, default="SIN_IVA", server_default="SIN_IVA"
    )
    monto_sin_iva = db.Column(db.Numeric(12, 2), nullable=False)
    metodo_pago = db.Column(db.String(20), nullable=False)
    payment_method_id = db.Column(
        db.Integer,
        db.ForeignKey("payment_methods.id"),
        index=True,
    )
    company_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    notas = db.Column(db.Text)
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    subcontract = db.relationship("Subcontract", back_populates="payments")
    company = db.relationship("Company")
    payment_method = db.relationship("PaymentMethod")
    created_by = db.relationship("Usuario")


class OfficeExpense(db.Model):
    __tablename__ = "office_expenses"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=False,
    )
    budget_item_id = db.Column(
        db.Integer,
        db.ForeignKey("budget_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    proveedor = db.Column(db.String(180), nullable=False)
    concepto = db.Column(db.String(240), nullable=False)
    monto_capturado = db.Column(db.Numeric(12, 2), nullable=False)
    tipo_monto = db.Column(
        db.String(15), nullable=False, default="SIN_IVA", server_default="SIN_IVA"
    )
    monto_sin_iva = db.Column(db.Numeric(12, 2), nullable=False)
    metodo_pago = db.Column(db.String(20), nullable=False)
    payment_method_id = db.Column(
        db.Integer,
        db.ForeignKey("payment_methods.id"),
        index=True,
    )
    company_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    notas = db.Column(db.Text)
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
    company = db.relationship("Company")
    payment_method = db.relationship("PaymentMethod")
    created_by = db.relationship("Usuario")


# Nombres de compatibilidad usados únicamente dentro de la lógica restaurada.
Project = CentroCosto
User = Usuario
