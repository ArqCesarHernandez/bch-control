"""Formularios Flask-WTF para los flujos de la Fase 5."""

from __future__ import annotations

from datetime import date

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    DateField,
    DateTimeLocalField,
    DecimalField,
    FieldList,
    Form,
    FormField,
    HiddenField,
    IntegerField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)
from wtforms.widgets import CheckboxInput, ListWidget


DOCUMENT_EXTENSIONS = ("pdf", "doc", "docx", "xls", "xlsx", "jpg", "jpeg", "png")
IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp")


def clean_text(value):
    return " ".join((value or "").strip().split()) or None


class ParteDiarioForm(FlaskForm):
    centro_costo_id = SelectField(
        "Obra", choices=[], coerce=int, validators=[DataRequired("Selecciona la obra.")]
    )
    fecha = DateField(
        "Fecha", default=date.today, validators=[DataRequired("Captura la fecha.")]
    )
    personal_total = IntegerField(
        "Personal total",
        default=0,
        validators=[
            InputRequired("Captura el total de personal; puede ser cero."),
            NumberRange(min=0, max=9999, message="El personal no puede ser negativo."),
        ],
    )
    horas_trabajadas = DecimalField(
        "Horas-hombre trabajadas",
        places=2,
        default=0,
        validators=[
            InputRequired("Captura las horas; pueden ser cero."),
            NumberRange(min=0, message="Las horas no pueden ser negativas."),
        ],
    )
    equipos_utilizados = TextAreaField(
        "Equipos utilizados", validators=[Optional(), Length(max=4000)]
    )
    condiciones_meteorologicas = StringField(
        "Condiciones meteorológicas", validators=[Optional(), Length(max=240)]
    )
    visitas = TextAreaField("Visitas", validators=[Optional(), Length(max=4000)])
    incidencias = TextAreaField("Incidencias", validators=[Optional(), Length(max=6000)])
    observaciones = TextAreaField(
        "Observaciones", validators=[Optional(), Length(max=6000)]
    )
    submit = SubmitField("Guardar parte diario")


class AvancePartidaForm(FlaskForm):
    partida_id = SelectField(
        "Partida", choices=[], coerce=int, validators=[DataRequired("Selecciona la partida.")]
    )
    fecha = DateField(
        "Fecha de medición", default=date.today, validators=[DataRequired()]
    )
    cantidad_ejecutada = DecimalField(
        "Cantidad ejecutada",
        places=4,
        validators=[
            InputRequired("Captura la cantidad ejecutada."),
            NumberRange(min=0.0001, message="La cantidad debe ser mayor que cero."),
        ],
    )
    unidad = StringField(
        "Unidad",
        validators=[DataRequired("Captura la unidad."), Length(max=20)],
        filters=[lambda value: (value or "").strip().upper()],
    )
    observaciones = TextAreaField(
        "Observaciones", validators=[Optional(), Length(max=4000)]
    )
    submit = SubmitField("Registrar avance")


class SolicitudCertificacionForm(FlaskForm):
    subcontrato_id = SelectField(
        "Subcontrato", choices=[], coerce=int, validators=[DataRequired()]
    )
    fecha_solicitud = DateField(
        "Fecha de solicitud", default=date.today, validators=[DataRequired()]
    )
    monto_solicitado = DecimalField(
        "Monto solicitado sin IVA",
        places=2,
        validators=[
            InputRequired("Captura el monto solicitado."),
            NumberRange(min=0.01, message="El monto debe ser mayor que cero."),
        ],
    )
    concepto = StringField(
        "Concepto", validators=[DataRequired(), Length(max=240)]
    )
    archivo_adjunto = FileField(
        "Pay application / soporte",
        validators=[
            Optional(),
            FileAllowed(DOCUMENT_EXTENSIONS, "Adjunta un PDF, Office o imagen válida."),
        ],
    )
    submit = SubmitField("Enviar a certificación")


class CertificacionDecisionForm(FlaskForm):
    decision = SelectField(
        "Decisión",
        choices=[("aprobar", "Aprobar"), ("rechazar", "Rechazar")],
        validators=[DataRequired()],
    )
    monto_aprobado = DecimalField(
        "Monto aprobado sin IVA",
        places=2,
        validators=[Optional(), NumberRange(min=0)],
    )
    company_id = SelectField("Empresa pagadora", choices=[], coerce=int, validators=[Optional()])
    payment_method_id = SelectField(
        "Método de pago", choices=[], coerce=int, validators=[Optional()]
    )
    comentario = TextAreaField(
        "Comentario", validators=[Optional(), Length(max=4000)]
    )
    submit = SubmitField("Registrar decisión")

    def validate_comentario(self, field):
        if self.decision.data == "rechazar" and not (field.data or "").strip():
            raise ValidationError("Explica el motivo del rechazo.")


class NoConformidadForm(FlaskForm):
    centro_costo_id = SelectField("Obra", choices=[], coerce=int, validators=[DataRequired()])
    descripcion = TextAreaField(
        "Descripción", validators=[DataRequired(), Length(max=6000)]
    )
    ubicacion = StringField(
        "Ubicación", validators=[DataRequired(), Length(max=240)]
    )
    severidad = SelectField(
        "Severidad",
        choices=[
            ("leve", "Leve"),
            ("moderada", "Moderada"),
            ("grave", "Grave"),
        ],
        validators=[DataRequired()],
    )
    responsable = StringField(
        "Responsable", validators=[DataRequired(), Length(max=180)]
    )
    fecha_deteccion = DateField(
        "Fecha de detección", default=date.today, validators=[DataRequired()]
    )
    fecha_limite = DateField("Fecha límite", validators=[DataRequired()])
    estado = SelectField(
        "Estado",
        choices=[
            ("abierta", "Abierta"),
            ("en_proceso", "En proceso"),
        ],
        validators=[DataRequired()],
    )
    evidencia_foto = FileField(
        "Evidencia fotográfica",
        validators=[
            Optional(),
            FileAllowed(IMAGE_EXTENSIONS, "Adjunta una imagen JPG, PNG o WEBP."),
        ],
    )
    submit = SubmitField("Guardar no conformidad")

    def validate_fecha_limite(self, field):
        if self.fecha_deteccion.data and field.data < self.fecha_deteccion.data:
            raise ValidationError(
                "La fecha límite no puede ser anterior a la detección."
            )


class CierreNoConformidadForm(FlaskForm):
    accion_correctiva = TextAreaField(
        "Acción correctiva",
        validators=[DataRequired("Describe la acción correctiva."), Length(max=6000)],
    )
    evidencia_cierre = FileField(
        "Evidencia de cierre",
        validators=[
            DataRequired("Adjunta evidencia del cierre."),
            FileAllowed(IMAGE_EXTENSIONS, "Adjunta una imagen JPG, PNG o WEBP."),
        ],
    )
    submit = SubmitField("Cerrar no conformidad")


class RFIForm(FlaskForm):
    centro_costo_id = SelectField("Obra", choices=[], coerce=int, validators=[DataRequired()])
    destinatario_id = SelectField(
        "Destinatario", choices=[], coerce=int, validators=[DataRequired()]
    )
    asunto = StringField("Asunto", validators=[DataRequired(), Length(max=240)])
    descripcion = TextAreaField(
        "Consulta técnica", validators=[DataRequired(), Length(max=10000)]
    )
    archivo_adjunto = FileField(
        "Archivo adjunto",
        validators=[
            Optional(),
            FileAllowed(DOCUMENT_EXTENSIONS, "Adjunta un archivo válido."),
        ],
    )
    submit = SubmitField("Enviar RFI")


class RFIRespuestaForm(FlaskForm):
    respuesta = TextAreaField(
        "Respuesta", validators=[DataRequired(), Length(max=10000)]
    )
    archivo_respuesta = FileField(
        "Archivo de respuesta",
        validators=[
            Optional(),
            FileAllowed(DOCUMENT_EXTENSIONS, "Adjunta un archivo válido."),
        ],
    )
    submit = SubmitField("Responder RFI")


class ReporteHSEForm(FlaskForm):
    centro_costo_id = SelectField("Obra", choices=[], coerce=int, validators=[DataRequired()])
    tipo = SelectField(
        "Tipo",
        choices=[
            ("acto_inseguro", "Acto inseguro"),
            ("condicion_insegura", "Condición insegura"),
            ("observacion", "Observación"),
        ],
        validators=[DataRequired()],
    )
    descripcion = TextAreaField(
        "Descripción", validators=[DataRequired(), Length(max=6000)]
    )
    ubicacion = StringField(
        "Ubicación", validators=[DataRequired(), Length(max=240)]
    )
    fecha = DateField("Fecha", default=date.today, validators=[DataRequired()])
    acciones = TextAreaField("Acciones", validators=[Optional(), Length(max=6000)])
    estado = SelectField(
        "Estado",
        choices=[
            ("abierta", "Abierta"),
            ("en_proceso", "En proceso"),
            ("cerrada", "Cerrada"),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField("Guardar reporte HSE")


class PermisoTrabajoForm(FlaskForm):
    centro_costo_id = SelectField("Obra", choices=[], coerce=int, validators=[DataRequired()])
    tipo = SelectField(
        "Tipo de permiso",
        choices=[
            ("caliente", "Trabajo en caliente"),
            ("altura", "Trabajo en altura"),
            ("excavacion", "Excavación"),
            ("electrico", "Trabajo eléctrico"),
            ("espacio_confinado", "Espacio confinado"),
        ],
        validators=[DataRequired()],
    )
    fecha_inicio = DateTimeLocalField(
        "Inicio programado", format="%Y-%m-%dT%H:%M", validators=[DataRequired()]
    )
    fecha_fin = DateTimeLocalField(
        "Fin programado", format="%Y-%m-%dT%H:%M", validators=[DataRequired()]
    )
    ubicacion = StringField("Ubicación", validators=[Optional(), Length(max=240)])
    descripcion = TextAreaField(
        "Alcance y controles", validators=[Optional(), Length(max=6000)]
    )
    submit = SubmitField("Solicitar permiso")

    def validate_fecha_fin(self, field):
        if self.fecha_inicio.data and field.data <= self.fecha_inicio.data:
            raise ValidationError("El fin debe ser posterior al inicio.")


class ProveedoresCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class LicitacionForm(FlaskForm):
    requisicion_id = SelectField(
        "Requisición aprobada", choices=[], coerce=int, validators=[DataRequired()]
    )
    fecha_limite = DateField("Fecha límite de respuesta", validators=[DataRequired()])
    proveedor_ids = ProveedoresCheckboxField(
        "Proveedores invitados",
        choices=[],
        coerce=int,
        validators=[DataRequired("Selecciona al menos un proveedor.")],
    )
    submit = SubmitField("Crear licitación")

    def validate_fecha_limite(self, field):
        if field.data < date.today():
            raise ValidationError("La fecha límite no puede estar en el pasado.")


class OfertaForm(FlaskForm):
    proveedor_id = SelectField("Proveedor", choices=[], coerce=int, validators=[DataRequired()])
    monto_total = DecimalField(
        "Monto total sin IVA",
        places=2,
        validators=[InputRequired(), NumberRange(min=0.01)],
    )
    plazo_entrega = IntegerField(
        "Plazo de entrega (días)",
        validators=[InputRequired(), NumberRange(min=0, max=3650)],
    )
    condiciones = TextAreaField(
        "Condiciones comerciales", validators=[Optional(), Length(max=8000)]
    )
    archivo_adjunto = FileField(
        "Oferta adjunta",
        validators=[
            Optional(),
            FileAllowed(DOCUMENT_EXTENSIONS, "Adjunta un archivo válido."),
        ],
    )
    submit = SubmitField("Registrar oferta")


class AdjudicacionForm(FlaskForm):
    destino = SelectField(
        "Convertir oferta en",
        choices=[
            ("orden_compra", "Orden de compra"),
            ("contrato", "Contrato"),
        ],
        validators=[DataRequired()],
    )
    company_id = SelectField("Empresa pagadora", choices=[], coerce=int, validators=[Optional()])
    payment_method_id = SelectField(
        "Método de pago", choices=[], coerce=int, validators=[Optional()]
    )
    tipo_contrato = SelectField(
        "Tipo de contrato",
        choices=[
            ("precio_unitario", "Precio unitario"),
            ("suma_alzada", "Suma alzada"),
            ("mixto", "Mixto"),
        ],
        validators=[Optional()],
    )
    fecha_inicio = DateField("Inicio del contrato", validators=[Optional()])
    fecha_fin = DateField("Fin del contrato", validators=[Optional()])
    condiciones_pago = TextAreaField(
        "Condiciones de pago", validators=[Optional(), Length(max=8000)]
    )
    retencion_garantia = DecimalField(
        "Retención de garantía (%)",
        places=2,
        default=0,
        validators=[Optional(), NumberRange(min=0, max=100)],
    )
    submit = SubmitField("Adjudicar")


class ContratoForm(FlaskForm):
    proveedor_id = SelectField("Proveedor", choices=[], coerce=int, validators=[DataRequired()])
    centro_costo_id = SelectField("Obra", choices=[], coerce=int, validators=[DataRequired()])
    tipo = SelectField(
        "Tipo",
        choices=[
            ("precio_unitario", "Precio unitario"),
            ("suma_alzada", "Suma alzada"),
            ("mixto", "Mixto"),
        ],
        validators=[DataRequired()],
    )
    monto_total = DecimalField(
        "Monto total sin IVA",
        places=2,
        validators=[InputRequired(), NumberRange(min=0)],
    )
    fecha_inicio = DateField("Fecha de inicio", validators=[DataRequired()])
    fecha_fin = DateField("Fecha de fin", validators=[DataRequired()])
    estado = SelectField(
        "Estado",
        choices=[
            ("borrador", "Borrador"),
            ("activo", "Activo"),
            ("suspendido", "Suspendido"),
            ("finalizado", "Finalizado"),
        ],
        validators=[DataRequired()],
    )
    condiciones_pago = TextAreaField(
        "Condiciones de pago", validators=[DataRequired(), Length(max=8000)]
    )
    retencion_garantia = DecimalField(
        "Retención de garantía (%)",
        places=2,
        default=0,
        validators=[InputRequired(), NumberRange(min=0, max=100)],
    )
    hitos_texto = TextAreaField(
        "Hitos (uno por línea)", validators=[Optional(), Length(max=8000)]
    )
    submit = SubmitField("Guardar contrato")

    def validate_fecha_fin(self, field):
        if self.fecha_inicio.data and field.data < self.fecha_inicio.data:
            raise ValidationError("La fecha final no puede ser anterior al inicio.")


class ContratoModificacionForm(FlaskForm):
    tipo = SelectField(
        "Tipo de modificación",
        choices=[
            ("alcance", "Alcance"),
            ("precio", "Precio"),
            ("plazo", "Plazo"),
        ],
        validators=[DataRequired()],
    )
    descripcion = TextAreaField(
        "Descripción y justificación", validators=[DataRequired(), Length(max=8000)]
    )
    monto_nuevo = DecimalField(
        "Nuevo monto total", places=2, validators=[Optional(), NumberRange(min=0)]
    )
    fecha_fin_nueva = DateField("Nueva fecha de terminación", validators=[Optional()])
    submit = SubmitField("Enviar modificación")


class ModificacionDecisionForm(FlaskForm):
    decision = SelectField(
        "Decisión",
        choices=[("aprobar", "Aprobar"), ("rechazar", "Rechazar")],
        validators=[DataRequired()],
    )
    comentario = TextAreaField(
        "Comentario", validators=[Optional(), Length(max=4000)]
    )
    submit = SubmitField("Registrar decisión")


class ConciliacionFacturaForm(FlaskForm):
    orden_compra_id = SelectField(
        "Orden de compra", choices=[], coerce=int, validators=[DataRequired()]
    )
    factura_numero = StringField(
        "Número de factura", validators=[DataRequired(), Length(max=80)]
    )
    fecha_factura = DateField("Fecha de factura", validators=[DataRequired()])
    monto_factura = DecimalField(
        "Monto facturado sin IVA",
        places=2,
        validators=[InputRequired(), NumberRange(min=0)],
    )
    motivo_diferencia = TextAreaField(
        "Explicación de diferencias", validators=[Optional(), Length(max=6000)]
    )
    submit = SubmitField("Conciliar factura")


class ConciliacionDecisionForm(FlaskForm):
    decision = SelectField(
        "Decisión",
        choices=[("aprobar", "Liberar para pago"), ("rechazar", "Rechazar")],
        validators=[DataRequired()],
    )
    comentario = TextAreaField(
        "Comentario", validators=[Optional(), Length(max=4000)]
    )
    submit = SubmitField("Registrar decisión")


class RecepcionLineaForm(Form):
    order_line_id = HiddenField(validators=[DataRequired()])
    cantidad_recibida = DecimalField(
        "Recibida", places=4, default=0, validators=[Optional(), NumberRange(min=0)]
    )
    cantidad_rechazada = DecimalField(
        "Rechazada", places=4, default=0, validators=[Optional(), NumberRange(min=0)]
    )
    cantidad_faltante = DecimalField(
        "Faltante", places=4, default=0, validators=[Optional(), NumberRange(min=0)]
    )
    motivo_discrepancia = StringField(
        "Motivo de discrepancia", validators=[Optional(), Length(max=500)]
    )
    evidencia_discrepancia = FileField(
        "Evidencia",
        validators=[Optional(), FileAllowed(IMAGE_EXTENSIONS, "Adjunta una imagen válida.")],
    )


class RecepcionMaterialForm(FlaskForm):
    fecha = DateField("Fecha de recepción", default=date.today, validators=[DataRequired()])
    documento_proveedor = StringField(
        "Albarán / remisión", validators=[Optional(), Length(max=80)]
    )
    factura_numero = StringField(
        "Número de factura", validators=[Optional(), Length(max=80)]
    )
    fecha_factura = DateField("Fecha de factura", validators=[Optional()])
    notas = TextAreaField("Notas", validators=[Optional(), Length(max=4000)])
    lineas = FieldList(FormField(RecepcionLineaForm), min_entries=0)
    submit = SubmitField("Confirmar recepción")


class ResolverDiscrepanciaForm(FlaskForm):
    resolucion = TextAreaField(
        "Resolución", validators=[DataRequired(), Length(max=4000)]
    )
    submit = SubmitField("Marcar resuelta")


class GarantiaObraForm(FlaskForm):
    obra_principal_id = SelectField(
        "Obra principal terminada o inactiva",
        choices=[],
        coerce=int,
        validators=[DataRequired("Selecciona la obra principal.")],
    )
    supervisor_id = SelectField(
        "Supervisor responsable",
        choices=[],
        coerce=int,
        validators=[DataRequired("Selecciona al Supervisor.")],
    )
    descripcion = TextAreaField(
        "Descripción de la garantía",
        validators=[DataRequired(), Length(min=10, max=6000)],
    )
    ubicacion = StringField(
        "Ubicación", validators=[DataRequired(), Length(max=240)]
    )
    motivo = TextAreaField(
        "Motivo por el que se reporta como garantía",
        validators=[DataRequired(), Length(min=5, max=500)],
    )
    evidencia_inicial = FileField(
        "Evidencia inicial",
        validators=[
            DataRequired("Adjunta evidencia inicial."),
            FileAllowed(IMAGE_EXTENSIONS, "Adjunta una imagen válida."),
        ],
    )
    submit = SubmitField("Reportar garantía")


class GarantiaDiagnosticoForm(FlaskForm):
    diagnostico = TextAreaField(
        "Diagnóstico", validators=[DataRequired(), Length(min=10, max=6000)]
    )
    trabajos_requeridos = TextAreaField(
        "Trabajos requeridos",
        validators=[DataRequired(), Length(min=10, max=6000)],
    )
    submit = SubmitField("Guardar diagnóstico")


class GarantiaDecisionForm(FlaskForm):
    decision = SelectField(
        "Decisión",
        choices=[
            ("autorizar", "Autorizar garantía"),
            ("rechazar", "Rechazar: no corresponde a garantía"),
        ],
        validators=[DataRequired()],
    )
    comentario = TextAreaField(
        "Motivo del rechazo / comentario",
        validators=[Optional(), Length(max=500)],
    )
    submit = SubmitField("Registrar decisión")

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        if self.decision.data == "rechazar" and not (
            self.comentario.data or ""
        ).strip():
            self.comentario.errors.append(
                "Captura el motivo por el que se rechaza la garantía."
            )
            valid = False
        return valid


class GarantiaCierreForm(FlaskForm):
    accion_correctiva = TextAreaField(
        "Acción correctiva realizada",
        validators=[DataRequired(), Length(min=10, max=6000)],
    )
    evidencia_final = FileField(
        "Evidencia final",
        validators=[
            DataRequired("Adjunta evidencia final."),
            FileAllowed(IMAGE_EXTENSIONS, "Adjunta una imagen válida."),
        ],
    )
    submit = SubmitField("Solicitar cierre")


class ActionFormFase5(FlaskForm):
    comentario = TextAreaField("Comentario", validators=[Optional(), Length(max=4000)])
    submit = SubmitField("Confirmar")
