"""Formularios de autenticación y administración del ERP V2.

Flask-WTF incorpora el token CSRF automáticamente mediante ``hidden_tag()``.
Las validaciones se ejecutan nuevamente en el servidor, aunque el navegador
también muestre restricciones HTML.
"""

from __future__ import annotations

import re
from datetime import date

from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import (
    BooleanField,
    DateField,
    DecimalField,
    FileField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

from models import CentroCosto, Usuario, db


def validate_full_name(_form, field) -> None:
    """Exige al menos nombre y apellido para evitar altas incompletas."""

    words = [word for word in re.split(r"\s+", (field.data or "").strip()) if word]
    if len(words) < 2:
        raise ValidationError(
            "Escribe el nombre completo, incluyendo por lo menos un apellido."
        )


class LoginForm(FlaskForm):
    """Credenciales necesarias para iniciar sesión."""

    correo = StringField(
        "Correo electrónico",
        validators=[
            DataRequired(message="El correo es obligatorio."),
            Email(message="Escribe un correo electrónico válido."),
            Length(max=120, message="El correo no puede superar 120 caracteres."),
        ],
        filters=[lambda value: (value or "").strip().lower()],
    )
    contrasena = PasswordField(
        "Contraseña",
        validators=[DataRequired(message="La contraseña es obligatoria.")],
    )
    submit = SubmitField("Iniciar sesión")


class InitialAdminRegistrationForm(FlaskForm):
    """Formulario disponible únicamente cuando la tabla usuarios está vacía."""

    nombre_completo = StringField(
        "Nombre completo",
        validators=[
            DataRequired(message="El nombre completo es obligatorio."),
            Length(
                min=5,
                max=150,
                message="El nombre debe tener entre 5 y 150 caracteres.",
            ),
            validate_full_name,
        ],
        filters=[lambda value: " ".join((value or "").strip().split())],
    )
    correo = StringField(
        "Correo electrónico",
        validators=[
            DataRequired(message="El correo es obligatorio."),
            Email(message="Escribe un correo electrónico válido."),
            Length(max=120, message="El correo no puede superar 120 caracteres."),
        ],
        filters=[lambda value: (value or "").strip().lower()],
    )
    contrasena = PasswordField(
        "Contraseña",
        validators=[
            DataRequired(message="La contraseña es obligatoria."),
            Length(
                min=8,
                max=128,
                message="La contraseña debe tener entre 8 y 128 caracteres.",
            ),
        ],
    )
    confirmar_contrasena = PasswordField(
        "Confirmar contraseña",
        validators=[
            DataRequired(message="Confirma la contraseña."),
            EqualTo("contrasena", message="Las contraseñas no coinciden."),
        ],
    )
    submit = SubmitField("Crear administrador inicial")

    def validate_correo(self, field) -> None:
        """Evita duplicados incluso si el formulario se reutiliza en pruebas."""

        if Usuario.query.filter_by(correo=field.data).first():
            raise ValidationError("Ya existe un usuario con ese correo.")


class LogoutForm(FlaskForm):
    """Formulario POST para cerrar sesión con protección CSRF."""

    submit = SubmitField("Cerrar sesión")


class CentroCostoForm(FlaskForm):
    """Alta y edición de obras u oficinas usadas como centros de costo."""

    nombre = StringField(
        "Nombre del centro de costo",
        validators=[
            DataRequired(message="El nombre del centro de costo es obligatorio."),
            Length(
                min=3,
                max=150,
                message="El nombre debe tener entre 3 y 150 caracteres.",
            ),
        ],
        filters=[lambda value: " ".join((value or "").strip().split())],
    )
    codigo = StringField(
        "Código",
        validators=[
            DataRequired(message="El código del centro es obligatorio."),
            Length(
                min=2,
                max=40,
                message="El código debe tener entre 2 y 40 caracteres.",
            ),
        ],
        filters=[lambda value: (value or "").strip().upper()],
        description="Ejemplo: PEDREGAL, L8021 u OF-ADM.",
    )
    tipo = SelectField(
        "Tipo",
        choices=[("obra", "Obra"), ("oficina", "Oficina")],
        validators=[DataRequired(message="Selecciona el tipo de centro.")],
    )
    fecha_apertura = DateField(
        "Fecha de apertura",
        format="%Y-%m-%d",
        validators=[Optional()],
        description="Si se deja vacía, se utilizará la fecha actual.",
    )
    presupuesto_total = DecimalField(
        "Presupuesto total sin IVA",
        places=2,
        default=0,
        validators=[
            InputRequired(message="Captura el presupuesto total; puede ser cero."),
            NumberRange(min=0, message="El presupuesto no puede ser negativo."),
        ],
    )
    presupuesto_mano_obra = DecimalField(
        "Presupuesto de mano de obra sin IVA",
        places=2,
        default=0,
        validators=[
            InputRequired(message="Captura el presupuesto de mano de obra; puede ser cero."),
            NumberRange(min=0, message="El presupuesto no puede ser negativo."),
        ],
    )
    descripcion = TextAreaField(
        "Descripción / notas",
        validators=[Optional(), Length(max=2000)],
        filters=[lambda value: (value or "").strip() or None],
    )
    submit = SubmitField("Guardar centro de costo")

    def __init__(self, *args, centro_actual=None, **kwargs):
        """Recibe el centro editado para no confundirlo con un duplicado."""

        super().__init__(*args, **kwargs)
        self.centro_actual = centro_actual

    def validate_nombre(self, field) -> None:
        """Evita nombres repetidos sin distinguir mayúsculas y minúsculas."""

        existente = CentroCosto.query.filter(
            func.lower(CentroCosto.nombre) == field.data.lower()
        ).first()
        if existente and (
            self.centro_actual is None or existente.id != self.centro_actual.id
        ):
            raise ValidationError("Ya existe un centro de costo con ese nombre.")

    def validate_codigo(self, field) -> None:
        """El código alimenta importaciones, filtros y reportes de nómina."""

        existente = CentroCosto.query.filter(
            func.lower(CentroCosto.codigo) == field.data.lower()
        ).first()
        if existente and (
            self.centro_actual is None or existente.id != self.centro_actual.id
        ):
            raise ValidationError("Ya existe un centro de costo con ese código.")

    def validate_fecha_apertura(self, field) -> None:
        """Impide aperturas futuras o posteriores al cierre registrado."""

        if field.data and field.data > date.today():
            raise ValidationError("La fecha de apertura no puede ser futura.")

        fecha_cierre = (
            self.centro_actual.fecha_cierre if self.centro_actual else None
        )
        if field.data and fecha_cierre and field.data > fecha_cierre:
            raise ValidationError(
                "La fecha de apertura no puede ser posterior a la fecha de cierre."
            )


class UsuarioForm(FlaskForm):
    """Alta de usuarios operativos y administrativos del ERP."""

    nombre_completo = StringField(
        "Nombre completo",
        validators=[
            DataRequired(message="El nombre completo es obligatorio."),
            Length(
                min=5,
                max=150,
                message="El nombre debe tener entre 5 y 150 caracteres.",
            ),
            validate_full_name,
        ],
        filters=[lambda value: " ".join((value or "").strip().split())],
    )
    correo = StringField(
        "Correo electrónico",
        validators=[
            DataRequired(message="El correo es obligatorio."),
            Email(message="Escribe un correo electrónico válido."),
            Length(max=120, message="El correo no puede superar 120 caracteres."),
        ],
        filters=[lambda value: (value or "").strip().lower()],
    )
    contrasena = PasswordField(
        "Contraseña temporal",
        validators=[
            DataRequired(message="La contraseña es obligatoria."),
            Length(
                min=8,
                max=128,
                message="La contraseña debe tener entre 8 y 128 caracteres.",
            ),
        ],
    )
    rol = SelectField(
        "Rol",
        choices=[
            ("capturista", "Capturista de nómina"),
            ("supervisor", "Supervisor de obra"),
            ("comprador", "Comprador"),
            ("costos", "Costos"),
            ("admin", "Administrador"),
        ],
        validators=[DataRequired(message="Selecciona un rol.")],
    )
    centro_costo_id = SelectField(
        "Centro de costo asignado",
        choices=[],
        coerce=int,
        validators=[Optional()],
        description="Es obligatorio para capturistas y supervisores.",
    )
    submit = SubmitField("Crear usuario")

    def validate_correo(self, field) -> None:
        """Evita correos duplicados aun si cambian mayúsculas o espacios."""

        existente = Usuario.query.filter(
            func.lower(Usuario.correo) == field.data.lower()
        ).first()
        if existente:
            raise ValidationError("Ya existe un usuario con ese correo.")

    def validate_centro_costo_id(self, field) -> None:
        """Exige a los capturistas un centro existente y actualmente activo."""

        if self.rol.data not in {"capturista", "supervisor"}:
            return

        if not field.data:
            raise ValidationError(
                "Selecciona un centro de costo para el rol operativo."
            )

        centro = db.session.get(CentroCosto, field.data)
        if centro is None or centro.estado != "activa":
            raise ValidationError(
                "El centro seleccionado no existe o actualmente está cerrado."
            )


class UsuarioEditForm(UsuarioForm):
    """Edición de usuario; la contraseña solo cambia cuando se captura."""

    contrasena = PasswordField(
        "Nueva contraseña (opcional)",
        validators=[
            Optional(),
            Length(
                min=8,
                max=128,
                message="La contraseña debe tener entre 8 y 128 caracteres.",
            ),
        ],
    )
    submit = SubmitField("Guardar usuario y permisos")

    def __init__(self, *args, usuario_actual=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario_actual = usuario_actual

    def validate_correo(self, field) -> None:
        existente = Usuario.query.filter(
            func.lower(Usuario.correo) == field.data.lower()
        ).first()
        if existente and (
            self.usuario_actual is None or existente.id != self.usuario_actual.id
        ):
            raise ValidationError("Ya existe un usuario con ese correo.")


class ActionForm(FlaskForm):
    """Formulario mínimo para acciones POST protegidas por CSRF."""

    submit = SubmitField("Confirmar")


# Formularios de Compras. Las rutas aplican además validaciones cruzadas de
# obra, requisición, cantidades y saldos directamente contra la base de datos.


class SupplierForm(FlaskForm):
    codigo = StringField("Código", validators=[DataRequired(), Length(max=40)])
    nombre = StringField("Nombre / razón social", validators=[DataRequired(), Length(max=180)])
    rfc = StringField("RFC", validators=[Optional(), Length(max=13)])
    contacto = StringField("Contacto", validators=[Optional(), Length(max=150)])
    telefono = StringField("Teléfono", validators=[Optional(), Length(max=50)])
    email = StringField(
        "Correo", validators=[DataRequired(), Email(), Length(max=180)]
    )
    company_id = IntegerField("Empresa relacionada", validators=[Optional()])
    tiene_credito = BooleanField("Tenemos línea de crédito")
    limite_credito = DecimalField("Monto de la línea", places=2, default=0, validators=[NumberRange(min=0)])
    dias_credito = IntegerField("Días de crédito", default=0, validators=[NumberRange(min=0)])
    notas = TextAreaField("Notas", validators=[Optional(), Length(max=2000)])


class ExplosionUploadForm(FlaskForm):
    project_id = IntegerField("Obra", validators=[DataRequired()])
    archivo = FileField("Explosión de insumos .xlsx", validators=[DataRequired()])


class PurchaseRequisitionForm(FlaskForm):
    project_id = IntegerField("Obra", validators=[DataRequired()])
    tipo_requisicion = SelectField(
        "Tipo de requisición",
        choices=[
            ("OPERACIONES", "Operaciones"),
            ("COMPRAS", "Compras / explosión de insumos"),
        ],
        validators=[DataRequired()],
    )
    fecha_requerida = DateField("Fecha requerida", validators=[DataRequired()])
    motivo = StringField("Motivo / frente de trabajo", validators=[DataRequired(), Length(max=240)])
    observaciones = TextAreaField("Comentario general", validators=[Optional(), Length(max=2000)])


class PurchaseRequisitionLineForm(FlaskForm):
    explosion_item_id = IntegerField("Partida → insumo", validators=[DataRequired()])
    cantidad_solicitada = DecimalField(
        "Cantidad", places=4, validators=[DataRequired(), NumberRange(min=0.0001)]
    )
    notas = TextAreaField(
        "Comentarios / especificaciones del supervisor",
        validators=[Optional(), Length(max=240)],
    )
    proveedor_sugerido = StringField(
        "Proveedor sugerido", validators=[Optional(), Length(max=180)]
    )


class QuotationResponseForm(FlaskForm):
    fecha_respuesta = DateField("Fecha de respuesta", validators=[DataRequired()])
    fecha_entrega_ofertada = DateField("Entrega ofertada", validators=[DataRequired()])
    notas = TextAreaField("Notas", validators=[Optional(), Length(max=2000)])


class PurchaseOrderForm(FlaskForm):
    project_id = HiddenField(validators=[DataRequired()])
    tipo_oc = SelectField(
        "Tipo de OC",
        choices=[("OPERACIONES", "Operaciones"), ("COMPRAS", "Compras")],
        validators=[DataRequired()],
    )
    supplier_id = IntegerField("Proveedor", validators=[DataRequired()])
    supplier_search = StringField(
        "Buscar proveedor", validators=[Optional(), Length(max=240)]
    )
    company_id = IntegerField("Empresa pagadora", validators=[DataRequired()])
    # El modal puede enviar temporalmente ``new:NOMBRE``; la ruta lo convierte
    # de forma segura en un registro del catálogo compartido.
    payment_method_id = StringField("Método de pago", validators=[DataRequired()])
    modalidad_pago = SelectField("Modalidad", choices=[("CREDITO", "Crédito"), ("ANTICIPO", "Anticipo")], validators=[DataRequired()])
    fecha_entrega_estimada = DateField("Fecha estimada de surtido", validators=[DataRequired()])
    anticipo_monto = DecimalField("Monto del anticipo", places=2, validators=[Optional(), NumberRange(min=0)])
    justificacion_anticipo = TextAreaField("Justificación", validators=[Optional(), Length(max=500)])
    notas = TextAreaField("Notas", validators=[Optional(), Length(max=2000)])
    nuevo_metodo_pago = StringField(
        "Nuevo método de pago", validators=[Optional(), Length(max=80)]
    )


class PurchaseOrderFiltersForm(FlaskForm):
    project_id = IntegerField("Obra", validators=[Optional()])
    supplier_id = IntegerField("Proveedor", validators=[Optional()])
    estado = SelectField(
        "Estado",
        choices=[
            ("", "Todos"),
            ("BORRADOR", "Borrador"),
            ("EMITIDA", "Emitida"),
            ("RECEPCION_PARCIAL", "Recibida parcial"),
            ("RECEPCION_TOTAL", "Recibida total"),
            ("CERRADA", "Cerrada"),
            ("CANCELADA", "Cancelada"),
        ],
        validators=[Optional()],
    )
    fecha_desde = DateField("Desde", validators=[Optional()])
    fecha_hasta = DateField("Hasta", validators=[Optional()])


class PurchaseRequisitionFiltersForm(FlaskForm):
    project_id = IntegerField("Obra", validators=[Optional()])
    requested_by_id = IntegerField("Solicitante", validators=[Optional()])
    tipo_requisicion = SelectField(
        "Tipo",
        choices=[("", "Todos"), ("OPERACIONES", "Operaciones"), ("COMPRAS", "Compras")],
        validators=[Optional()],
    )
    estado = StringField("Estado", validators=[Optional(), Length(max=24)])


class SupplierFiltersForm(FlaskForm):
    company_id = IntegerField("Empresa", validators=[Optional()])
    estado_credito = SelectField(
        "Estado de crédito",
        choices=[("", "Todos"), ("ACTIVO", "Activo"), ("VENCIDO", "Vencido")],
        validators=[Optional()],
    )
    nombre = StringField("Nombre", validators=[Optional(), Length(max=180)])


class SupplierPaymentFiltersForm(FlaskForm):
    supplier_id = IntegerField("Proveedor", validators=[Optional()])
    fecha_desde = DateField("Desde", validators=[Optional()])
    fecha_hasta = DateField("Hasta", validators=[Optional()])
    tipo_pago = SelectField(
        "Tipo de pago",
        choices=[
            ("", "Todos"),
            ("NOMINA", "Proveedores nómina"),
            ("COMPRAS", "Proveedores compras"),
            ("CREDITO", "Crédito"),
        ],
        validators=[Optional()],
    )


class QuotationWhatsAppForm(FlaskForm):
    notas_whatsapp = TextAreaField(
        "Notas de contacto", validators=[Optional(), Length(max=500)]
    )


class GoodsReceiptForm(FlaskForm):
    fecha_recepcion = DateField("Fecha de recepción", validators=[DataRequired()])
    documento_proveedor = StringField("Factura / remisión", validators=[Optional(), Length(max=80)])
    fecha_factura = DateField("Fecha de factura", validators=[Optional()])
    notas_recepcion = TextAreaField("Notas", validators=[Optional(), Length(max=2000)])


class PaymentMethodForm(FlaskForm):
    nombre = StringField("Nombre", validators=[DataRequired(), Length(max=80)])
    descripcion = StringField("Descripción", validators=[Optional(), Length(max=240)])


class SupplierPaymentForm(FlaskForm):
    purchase_order_id = IntegerField("Orden de Compra", validators=[DataRequired()])
    order_line_id = IntegerField("Renglón", validators=[DataRequired()])
    fecha = DateField("Fecha", validators=[DataRequired()])
    monto_capturado = DecimalField("Monto", places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    tipo_monto = SelectField("Tipo de monto", choices=[("SIN_IVA", "Sin IVA"), ("CON_IVA", "Con IVA")])
    payment_method_id = IntegerField("Método", validators=[DataRequired()])
    company_id = IntegerField("Empresa", validators=[DataRequired()])
    concepto = StringField("Concepto", validators=[DataRequired(), Length(max=240)])
    notas = TextAreaField("Notas", validators=[Optional(), Length(max=2000)])


class CreditCardForm(FlaskForm):
    empresa_id = IntegerField("Empresa pagadora", validators=[DataRequired()])
    numero_tarjeta = StringField(
        "Número enmascarado",
        validators=[DataRequired(), Length(min=4, max=30)],
        description="Ejemplo: **** **** **** 1234. Nunca captures el número completo.",
    )
    fecha_corte = DateField("Fecha de corte", validators=[DataRequired()])
    fecha_pago = DateField("Fecha límite de pago", validators=[DataRequired()])
    limite_credito = DecimalField(
        "Límite de crédito", places=2, validators=[InputRequired(), NumberRange(min=0)]
    )
    saldo_actual = DecimalField(
        "Saldo actual", places=2, validators=[InputRequired(), NumberRange(min=0)]
    )
    submit = SubmitField("Guardar tarjeta")


class CreditCardPaymentForm(FlaskForm):
    fecha = DateField("Fecha del pago", validators=[DataRequired()])
    monto = DecimalField(
        "Monto pagado", places=2, validators=[DataRequired(), NumberRange(min=0.01)]
    )
    referencia = StringField("Referencia", validators=[Optional(), Length(max=120)])
    notas = TextAreaField("Notas", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Registrar pago")


class MaterialChangeRequestForm(FlaskForm):
    project_id = IntegerField("Obra", validators=[DataRequired()])
    budget_item_id = IntegerField("Partida", validators=[DataRequired()])
    action_type = SelectField("Acción", choices=[("NUEVO", "Nuevo"), ("AUMENTO", "Aumento")])
    existing_explosion_item_id = IntegerField("Insumo existente", validators=[Optional()])
    supply_key = StringField("Clave", validators=[Optional(), Length(max=40)])
    supply_type = SelectField("Tipo", choices=[(value, value) for value in ["MATERIAL", "EQUIPO", "MANO_OBRA", "SUBCONTRATO", "INDIRECTO"]])
    descripcion = StringField("Descripción", validators=[Optional(), Length(max=180)])
    unidad = StringField("Unidad", validators=[Optional(), Length(max=20)])
    cantidad = DecimalField("Cantidad", places=4, validators=[DataRequired(), NumberRange(min=0.0001)])
    precio_estimado = DecimalField("Precio estimado", places=4, validators=[DataRequired(), NumberRange(min=0.0001)])
    justificacion_tipo = SelectField("Causa", choices=[("MATERIAL_NO_CONTEMPLADO", "Material no contemplado"), ("ERROR_CUANTIFICACION", "Error de cuantificación"), ("CAMBIO_PROYECTO", "Cambio de proyecto")])
    justificacion = TextAreaField("Justificación", validators=[DataRequired(), Length(max=500)])
