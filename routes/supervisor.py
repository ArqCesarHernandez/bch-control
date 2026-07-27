"""Rutas móviles de Residente/Supervisor para la operación en campo."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import false, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from compras_models import (
    ACTIVE_ORDER_STATES,
    BudgetExplosionItem,
    ExplosionRevision,
    GoodsReceipt,
    MaterialChangeRequest,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderPaymentSchedule,
    PurchaseRequisition,
    PaymentMethod,
)
from fase5_forms import (
    ActionFormFase5,
    AvancePartidaForm,
    CertificacionDecisionForm,
    CierreNoConformidadForm,
    GarantiaCierreForm,
    GarantiaDecisionForm,
    GarantiaDiagnosticoForm,
    GarantiaObraForm,
    NoConformidadForm,
    ParteDiarioForm,
    PermisoTrabajoForm,
    ReporteHSEForm,
    RFIForm,
    RFIRespuestaForm,
    SolicitudCertificacionForm,
)
from fase5_models import (
    AvancePartida,
    CertificacionSubcontrato,
    GarantiaObra,
    NoConformidad,
    ParteDiario,
    PermisoTrabajo,
    ReporteHSE,
    RFI,
    RFIEvento,
    SolicitudPagoSubcontrato,
)
from models import CentroCosto, Usuario, db, utc_now
from nominas_models import (
    BudgetItem,
    Company,
    AdditionalPayment,
    Payroll,
    PayrollLine,
    Subcontract,
    SubcontractPayment,
    decimal_value,
    money,
)
from services.actualizacion_operativa import (
    activar_revision_explosion,
    items_explosion_vigente,
    revision_explosion_vigente,
    siguiente_revision_explosion,
)
from services.fase5 import (
    actualizar_avance_partida,
    archivo_fase5_absoluto,
    auditar,
    fecha_operativa,
    guardar_archivo,
    notificar,
    obras_accesibles,
    usuarios_con_permiso,
)
from services.weekly_resources import (
    week_start_for,
    weekly_resource_breakdown,
)
from utils.access import verificar_acceso_obra, verificar_asignacion_obra
from utils.decorators import permission_required


campo_bp = Blueprint("campo", __name__, url_prefix="/campo")


def _obras_choices():
    return [
        (obra.id, f"{obra.codigo} · {obra.nombre}")
        for obra in obras_accesibles(current_user)
    ]


def _partidas_accesibles():
    project_ids = [obra.id for obra in obras_accesibles(current_user)]
    return (
        BudgetItem.query.options(joinedload(BudgetItem.project))
        .filter(
            BudgetItem.project_id.in_(project_ids or [-1]),
            BudgetItem.activa.is_(True),
        )
        .order_by(BudgetItem.project_id, BudgetItem.codigo)
        .all()
    )


def _parse_filter_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        flash("El rango de fechas no es válido.", "danger")
        return None


def _load_project(project_id: int) -> CentroCosto:
    project = db.get_or_404(CentroCosto, project_id)
    if project.tipo != "obra":
        abort(404)
    verificar_acceso_obra(current_user, project.id)
    return project


# ---------------------------------------------------------------------------
# Parte diario
# ---------------------------------------------------------------------------


@campo_bp.get("/")
@permission_required("dashboard_supervisor", "ver")
def dashboard():
    return redirect(url_for("campo.supervisor_dashboard"))


@campo_bp.get("/dashboard-supervisor")
@permission_required("dashboard_supervisor", "ver")
def supervisor_dashboard():
    """Panel agregado y estrictamente limitado a las obras asignadas."""

    works = obras_accesibles(current_user, incluir_inactivas=True)
    work_ids = [work.id for work in works]
    scoped = work_ids or [-1]
    resource_summary = weekly_resource_breakdown(
        week_start_for(fecha_operativa()),
        work_ids,
    )

    requisitions = (
        PurchaseRequisition.query.options(
            joinedload(PurchaseRequisition.project),
            joinedload(PurchaseRequisition.requested_by),
        )
        .filter(PurchaseRequisition.project_id.in_(scoped))
        .order_by(PurchaseRequisition.created_at.desc())
        .limit(15)
        .all()
    )
    payment_requests = (
        PurchaseOrderPaymentSchedule.query.options(
            joinedload(PurchaseOrderPaymentSchedule.order)
        )
        .join(PurchaseOrder)
        .filter(
            PurchaseOrder.project_id.in_(scoped),
            PurchaseOrder.tipo_oc == "OPERACIONES",
            PurchaseOrder.created_by_id == current_user.id,
        )
        .order_by(PurchaseOrderPaymentSchedule.fecha_solicitud.desc())
        .limit(12)
        .all()
    )
    receipts = (
        GoodsReceipt.query.options(
            joinedload(GoodsReceipt.order).joinedload(PurchaseOrder.project)
        )
        .join(PurchaseOrder)
        .filter(PurchaseOrder.project_id.in_(scoped))
        .order_by(GoodsReceipt.fecha.desc(), GoodsReceipt.id.desc())
        .limit(10)
        .all()
    )
    operational_orders = (
        PurchaseOrder.query.options(joinedload(PurchaseOrder.project))
        .filter(
            PurchaseOrder.project_id.in_(scoped),
            PurchaseOrder.tipo_oc == "OPERACIONES",
        )
        .order_by(PurchaseOrder.fecha_orden.desc(), PurchaseOrder.id.desc())
        .limit(10)
        .all()
    )
    warranties = (
        GarantiaObra.query.options(
            joinedload(GarantiaObra.obra_principal),
            joinedload(GarantiaObra.centro_garantia),
        )
        .filter(
            GarantiaObra.supervisor_id == current_user.id,
            GarantiaObra.estado.notin_(("cerrada", "rechazada")),
            or_(
                GarantiaObra.obra_principal_id.in_(scoped),
                GarantiaObra.centro_garantia_id.in_(scoped),
            ),
        )
        .order_by(GarantiaObra.fecha_creacion.desc())
        .all()
    )

    payrolls = (
        Payroll.query.options(
            joinedload(Payroll.project),
            joinedload(Payroll.lines).joinedload(PayrollLine.budget_item),
            joinedload(Payroll.lines).joinedload(PayrollLine.partida),
            joinedload(Payroll.lines).joinedload(PayrollLine.subpartida),
        )
        .filter(Payroll.project_id.in_(scoped))
        .order_by(Payroll.semana_inicio.desc(), Payroll.id.desc())
        .all()
    )
    recent_weeks = sorted(
        {payroll.semana_inicio for payroll in payrolls}, reverse=True
    )[:3]
    payroll_weeks = []
    for week in recent_weeks:
        records = [payroll for payroll in payrolls if payroll.semana_inicio == week]
        payroll_weeks.append(
            {
                "inicio": week,
                "fin": max(payroll.semana_fin for payroll in records),
                "obras": len({payroll.project_id for payroll in records}),
                "total": money(
                    sum((payroll.total_neto for payroll in records), Decimal("0"))
                ),
                "estado": (
                    "Pagada"
                    if all(
                        payroll.estado in {"pagada", "conciliada"}
                        for payroll in records
                    )
                    else "En proceso"
                ),
            }
        )

    labor_by_work = []
    for work in works:
        revision = revision_explosion_vigente(work.id)
        budget = None
        if revision:
            budget = money(
                sum(
                    (
                        decimal_value(item.importe_presupuestado)
                        for item in items_explosion_vigente(work.id)
                        if item.supply_item.tipo == "MANO_OBRA"
                    ),
                    Decimal("0"),
                )
            )
        paid = money(
            sum(
                (
                    payroll.total_costo_mano_obra
                    for payroll in payrolls
                    if payroll.project_id == work.id
                    and payroll.estado in {"pagada", "conciliada"}
                ),
                Decimal("0"),
            )
        )
        progress = (
            min(Decimal("100"), paid * Decimal("100") / budget)
            if budget is not None and budget > 0
            else None
        )
        labor_by_work.append(
            {
                "obra": work,
                "revision": revision,
                "presupuesto": budget,
                "pagado": paid,
                "porcentaje": progress,
            }
        )

    labor_by_budget: dict[tuple[int, int | None], dict] = {}
    for payroll in payrolls:
        if payroll.estado not in {"aprobada", "pagada", "conciliada"}:
            continue
        for line in payroll.lines:
            partida = line.partida_resuelta
            subpartida = line.subpartida_resuelta
            if not partida:
                continue
            key = (partida.id, subpartida.id if subpartida else None)
            row = labor_by_budget.setdefault(
                key,
                {
                    "partida": partida,
                    "subpartida": subpartida,
                    "costo": Decimal("0"),
                },
            )
            row["costo"] = money(
                row["costo"]
                + decimal_value(line.monto_devengado)
                + decimal_value(line.pago_extra)
                + decimal_value(line.descuento_imss)
            )
    labor_by_budget_rows = sorted(
        labor_by_budget.values(),
        key=lambda row: (
            row["partida"].codigo,
            row["subpartida"].codigo if row["subpartida"] else "",
        ),
    )

    return render_template(
        "campo/dashboard_supervisor.html",
        obras=works,
        requisiciones=requisitions,
        pagos_solicitados=payment_requests,
        mano_obra=labor_by_work,
        recepciones=receipts,
        nominas_semanas=payroll_weeks,
        ordenes_operaciones=operational_orders,
        garantias=warranties,
        resource_summary=resource_summary,
        mano_obra_partidas=labor_by_budget_rows,
    )


@campo_bp.get("/partes-diarios")
@permission_required("parte_diario", "ver")
def partes_lista():
    project_ids = [obra.id for obra in obras_accesibles(current_user, incluir_inactivas=True)]
    query = ParteDiario.query.options(joinedload(ParteDiario.centro_costo)).filter(
        ParteDiario.centro_costo_id.in_(project_ids or [-1])
    )
    project_id = request.args.get("obra", type=int)
    start = _parse_filter_date(request.args.get("desde"))
    end = _parse_filter_date(request.args.get("hasta"))
    if project_id:
        verificar_acceso_obra(current_user, project_id)
        query = query.filter(ParteDiario.centro_costo_id == project_id)
    if start:
        query = query.filter(ParteDiario.fecha >= start)
    if end:
        query = query.filter(ParteDiario.fecha <= end)
    if start and end and start > end:
        flash("La fecha inicial no puede ser posterior a la final.", "danger")
        query = query.filter(false())
    partes = query.order_by(ParteDiario.fecha.desc(), ParteDiario.id.desc()).all()
    return render_template(
        "campo/partes/lista.html",
        partes=partes,
        obras=obras_accesibles(current_user, incluir_inactivas=True),
        selected_project=project_id,
        desde=request.args.get("desde", ""),
        hasta=request.args.get("hasta", ""),
        action_form=ActionFormFase5(),
    )


def _parte_form(parte: ParteDiario):
    creating = parte.id is None
    form = ParteDiarioForm(obj=parte)
    form.centro_costo_id.choices = _obras_choices()
    if request.method == "POST":
        raw_project_id = request.form.get("centro_costo_id", "")
        if raw_project_id.isdigit():
            _load_project(int(raw_project_id))
    if form.validate_on_submit():
        project = _load_project(form.centro_costo_id.data)
        duplicate = ParteDiario.query.filter_by(
            centro_costo_id=project.id, fecha=form.fecha.data
        )
        if parte.id:
            duplicate = duplicate.filter(ParteDiario.id != parte.id)
        if duplicate.first():
            form.fecha.errors.append("Ya existe un parte diario para esa obra y fecha.")
        else:
            parte.usuario_id = current_user.id
            parte.centro_costo_id = project.id
            parte.fecha = form.fecha.data
            parte.personal_total = form.personal_total.data
            parte.horas_trabajadas = form.horas_trabajadas.data
            parte.equipos_utilizados = (form.equipos_utilizados.data or "").strip() or None
            parte.condiciones_meteorologicas = (
                form.condiciones_meteorologicas.data or ""
            ).strip() or None
            parte.visitas = (form.visitas.data or "").strip() or None
            parte.incidencias = (form.incidencias.data or "").strip() or None
            parte.observaciones = (form.observaciones.data or "").strip() or None
            db.session.add(parte)
            db.session.flush()
            auditar(
                current_user.id,
                "CREAR_PARTE_DIARIO" if creating else "EDITAR_PARTE_DIARIO",
                "partes_diarios",
                parte.id,
                f"{project.codigo} · {parte.fecha.isoformat()}",
            )
            db.session.commit()
            flash("Parte diario guardado correctamente.", "success")
            return redirect(url_for("campo.partes_lista"))
    return render_template(
        "campo/partes/formulario.html", form=form, parte=parte, creating=creating
    )


@campo_bp.route("/partes-diarios/nuevo", methods=["GET", "POST"])
@permission_required("parte_diario", "crear")
def parte_nuevo():
    return _parte_form(ParteDiario(fecha=date.today()))


@campo_bp.route("/partes-diarios/<int:parte_id>/editar", methods=["GET", "POST"])
@permission_required("parte_diario", "editar")
def parte_editar(parte_id):
    parte = db.get_or_404(ParteDiario, parte_id)
    verificar_acceso_obra(current_user, parte.centro_costo_id)
    return _parte_form(parte)


@campo_bp.post("/partes-diarios/<int:parte_id>/eliminar")
@permission_required("parte_diario", "eliminar")
def parte_eliminar(parte_id):
    form = ActionFormFase5()
    if not form.validate_on_submit():
        abort(400)
    parte = db.get_or_404(ParteDiario, parte_id)
    verificar_acceso_obra(current_user, parte.centro_costo_id)
    auditar(
        current_user.id,
        "ELIMINAR_PARTE_DIARIO",
        "partes_diarios",
        parte.id,
        parte.fecha.isoformat(),
    )
    db.session.delete(parte)
    db.session.commit()
    flash("Parte diario eliminado.", "success")
    return redirect(url_for("campo.partes_lista"))


# ---------------------------------------------------------------------------
# Avances físicos
# ---------------------------------------------------------------------------


@campo_bp.get("/avances")
@permission_required("avance_obra", "ver")
def avances_lista():
    project_ids = [obra.id for obra in obras_accesibles(current_user, incluir_inactivas=True)]
    query = (
        AvancePartida.query.options(
            joinedload(AvancePartida.partida).joinedload(BudgetItem.project),
            joinedload(AvancePartida.usuario),
        )
        .join(BudgetItem)
        .filter(BudgetItem.project_id.in_(project_ids or [-1]))
    )
    project_id = request.args.get("obra", type=int)
    if project_id:
        verificar_acceso_obra(current_user, project_id)
        query = query.filter(BudgetItem.project_id == project_id)
    avances = query.order_by(AvancePartida.fecha.desc(), AvancePartida.id.desc()).all()
    return render_template(
        "campo/avances/lista.html",
        avances=avances,
        obras=obras_accesibles(current_user, incluir_inactivas=True),
        selected_project=project_id,
        action_form=ActionFormFase5(),
    )


def _avance_form(avance: AvancePartida):
    creating = avance.id is None
    form = AvancePartidaForm(obj=avance)
    partidas = _partidas_accesibles()
    form.partida_id.choices = [
        (
            item.id,
            f"{item.project.codigo} · {item.codigo} · {item.nombre} "
            f"({item.cantidad_objetivo or 0} {item.unidad_medida or 'sin unidad'})",
        )
        for item in partidas
    ]
    if request.method == "GET" and avance.partida:
        form.unidad.data = avance.unidad
    if form.validate_on_submit():
        partida = db.session.get(BudgetItem, form.partida_id.data)
        if not partida:
            abort(404)
        verificar_acceso_obra(current_user, partida.project_id)
        if partida.unidad_medida and form.unidad.data != partida.unidad_medida.upper():
            form.unidad.errors.append(
                f"La unidad configurada para la partida es {partida.unidad_medida}."
            )
        elif decimal_value(partida.cantidad_objetivo) <= 0:
            form.partida_id.errors.append(
                "La partida no tiene cantidad objetivo. Configúrala antes de capturar avance."
            )
        else:
            previous_partida_id = avance.partida_id
            avance.partida_id = partida.id
            avance.fecha = form.fecha.data
            avance.cantidad_ejecutada = form.cantidad_ejecutada.data
            avance.unidad = form.unidad.data
            avance.usuario_id = current_user.id
            avance.observaciones = (form.observaciones.data or "").strip() or None
            db.session.add(avance)
            db.session.flush()
            porcentaje = actualizar_avance_partida(partida.id)
            if previous_partida_id and previous_partida_id != partida.id:
                actualizar_avance_partida(previous_partida_id)
            auditar(
                current_user.id,
                "CREAR_AVANCE" if creating else "EDITAR_AVANCE",
                "avances_partidas",
                avance.id,
                f"{partida.codigo}: {avance.cantidad_ejecutada} {avance.unidad}",
            )
            db.session.commit()
            flash(f"Avance registrado. La partida quedó en {porcentaje}%.", "success")
            return redirect(url_for("campo.avances_lista"))
    return render_template(
        "campo/avances/formulario.html",
        form=form,
        avance=avance,
        creating=creating,
    )


@campo_bp.route("/avances/nuevo", methods=["GET", "POST"])
@permission_required("avance_obra", "crear")
def avance_nuevo():
    return _avance_form(AvancePartida(fecha=date.today()))


@campo_bp.route("/avances/<int:avance_id>/editar", methods=["GET", "POST"])
@permission_required("avance_obra", "editar")
def avance_editar(avance_id):
    avance = db.get_or_404(AvancePartida, avance_id)
    verificar_acceso_obra(current_user, avance.partida.project_id)
    return _avance_form(avance)


@campo_bp.post("/avances/<int:avance_id>/eliminar")
@permission_required("avance_obra", "eliminar")
def avance_eliminar(avance_id):
    form = ActionFormFase5()
    if not form.validate_on_submit():
        abort(400)
    avance = db.get_or_404(AvancePartida, avance_id)
    partida_id = avance.partida_id
    verificar_acceso_obra(current_user, avance.partida.project_id)
    auditar(current_user.id, "ELIMINAR_AVANCE", "avances_partidas", avance.id)
    db.session.delete(avance)
    db.session.flush()
    actualizar_avance_partida(partida_id)
    db.session.commit()
    flash("Medición eliminada y porcentaje recalculado.", "success")
    return redirect(url_for("campo.avances_lista"))


# ---------------------------------------------------------------------------
# Certificaciones de subcontrato
# ---------------------------------------------------------------------------


def _subcontratos_accesibles():
    project_ids = [obra.id for obra in obras_accesibles(current_user, incluir_inactivas=True)]
    return (
        Subcontract.query.options(
            joinedload(Subcontract.project), joinedload(Subcontract.contractor)
        )
        .filter(
            Subcontract.project_id.in_(project_ids or [-1]),
            Subcontract.activo.is_(True),
        )
        .order_by(Subcontract.project_id, Subcontract.especialidad)
        .all()
    )


@campo_bp.get("/certificaciones")
@permission_required("certificaciones", "ver")
def certificaciones_lista():
    project_ids = [obra.id for obra in obras_accesibles(current_user, incluir_inactivas=True)]
    certificaciones = (
        CertificacionSubcontrato.query.options(
            joinedload(CertificacionSubcontrato.subcontrato).joinedload(
                Subcontract.project
            ),
            joinedload(CertificacionSubcontrato.subcontrato).joinedload(
                Subcontract.contractor
            ),
        )
        .join(Subcontract)
        .filter(Subcontract.project_id.in_(project_ids or [-1]))
        .order_by(CertificacionSubcontrato.id.desc())
        .all()
    )
    return render_template(
        "campo/certificaciones/lista.html", certificaciones=certificaciones
    )


@campo_bp.route("/certificaciones/nueva", methods=["GET", "POST"])
@permission_required("certificaciones", "crear")
def certificacion_nueva():
    form = SolicitudCertificacionForm()
    subcontratos = _subcontratos_accesibles()
    form.subcontrato_id.choices = [
        (
            sub.id,
            f"{sub.project.codigo} · {sub.contractor.nombre} · {sub.especialidad}",
        )
        for sub in subcontratos
    ]
    if form.validate_on_submit():
        subcontrato = db.session.get(Subcontract, form.subcontrato_id.data)
        if not subcontrato:
            abort(404)
        verificar_acceso_obra(current_user, subcontrato.project_id)
        try:
            archivo = guardar_archivo(
                form.archivo_adjunto.data, "certificaciones"
            )
            solicitud = SolicitudPagoSubcontrato(
                subcontrato_id=subcontrato.id,
                fecha_solicitud=form.fecha_solicitud.data,
                monto_solicitado=form.monto_solicitado.data,
                concepto=form.concepto.data.strip(),
                archivo_adjunto=archivo,
                estado="pendiente",
                usuario_id=current_user.id,
            )
            db.session.add(solicitud)
            db.session.flush()
            certificacion = CertificacionSubcontrato(
                subcontrato_id=subcontrato.id,
                solicitud_pago_id=solicitud.id,
                monto_solicitado=form.monto_solicitado.data,
                estado="pendiente",
            )
            db.session.add(certificacion)
            db.session.flush()
            notificar(
                usuarios_con_permiso(
                    "certificaciones",
                    "aprobar",
                    centro_costo_id=subcontrato.project_id,
                ),
                "CERTIFICACION_PENDIENTE",
                f"Nueva certificación #{certificacion.id} por "
                f"${form.monto_solicitado.data:,.2f} MXN.",
                url_for("campo.certificacion_detalle", certificacion_id=certificacion.id),
            )
            auditar(
                current_user.id,
                "CREAR_CERTIFICACION",
                "certificaciones_subcontratos",
                certificacion.id,
                solicitud.concepto,
            )
            db.session.commit()
        except (OSError, ValueError, IntegrityError) as exc:
            db.session.rollback()
            flash(f"No fue posible registrar la certificación: {exc}", "danger")
        else:
            flash("Solicitud enviada para certificación.", "success")
            return redirect(
                url_for(
                    "campo.certificacion_detalle",
                    certificacion_id=certificacion.id,
                )
            )
    return render_template("campo/certificaciones/formulario.html", form=form)


@campo_bp.get("/certificaciones/<int:certificacion_id>")
@permission_required("certificaciones", "ver")
def certificacion_detalle(certificacion_id):
    certificacion = db.get_or_404(CertificacionSubcontrato, certificacion_id)
    verificar_acceso_obra(current_user, certificacion.subcontrato.project_id)
    form = CertificacionDecisionForm(
        monto_aprobado=certificacion.monto_solicitado
    )
    form.company_id.choices = [
        (company.id, f"{company.codigo} · {company.nombre}")
        for company in Company.query.filter_by(activa=True).order_by(Company.nombre)
    ]
    form.payment_method_id.choices = [
        (method.id, method.nombre)
        for method in PaymentMethod.query.filter_by(activo=True).order_by(
            PaymentMethod.nombre
        )
    ]
    return render_template(
        "campo/certificaciones/detalle.html",
        certificacion=certificacion,
        form=form,
    )


@campo_bp.post("/certificaciones/<int:certificacion_id>/resolver")
@permission_required("certificaciones", "aprobar")
def certificacion_resolver(certificacion_id):
    certificacion = db.get_or_404(CertificacionSubcontrato, certificacion_id)
    verificar_acceso_obra(current_user, certificacion.subcontrato.project_id)
    form = CertificacionDecisionForm()
    form.company_id.choices = [
        (company.id, company.nombre)
        for company in Company.query.filter_by(activa=True).all()
    ]
    form.payment_method_id.choices = [
        (method.id, method.nombre)
        for method in PaymentMethod.query.filter_by(activo=True).all()
    ]
    if certificacion.estado != "pendiente":
        flash("La certificación ya fue resuelta.", "info")
        return redirect(
            url_for("campo.certificacion_detalle", certificacion_id=certificacion.id)
        )
    if not form.validate_on_submit():
        flash("Revisa los datos de la decisión.", "danger")
        return redirect(
            url_for("campo.certificacion_detalle", certificacion_id=certificacion.id)
        )

    solicitud = certificacion.solicitud_pago
    if form.decision.data == "rechazar":
        certificacion.estado = "rechazada"
        certificacion.monto_aprobado = Decimal("0")
        solicitud.estado = "rechazada"
    else:
        monto = decimal_value(form.monto_aprobado.data)
        disponible = max(
            Decimal("0"),
            decimal_value(certificacion.subcontrato.comprometido)
            - decimal_value(certificacion.subcontrato.pagado_sin_iva),
        )
        company = db.session.get(Company, form.company_id.data)
        method = db.session.get(PaymentMethod, form.payment_method_id.data)
        if monto <= 0 or monto > decimal_value(certificacion.monto_solicitado):
            flash(
                "El monto aprobado debe ser mayor que cero y no exceder lo solicitado.",
                "danger",
            )
            return redirect(
                url_for("campo.certificacion_detalle", certificacion_id=certificacion.id)
            )
        if monto > disponible:
            flash(
                "El monto aprobado excede el avance real disponible del subcontrato.",
                "danger",
            )
            return redirect(
                url_for("campo.certificacion_detalle", certificacion_id=certificacion.id)
            )
        if not company or not company.activa or not method or not method.activo:
            flash("Selecciona empresa y método de pago activos.", "danger")
            return redirect(
                url_for("campo.certificacion_detalle", certificacion_id=certificacion.id)
            )
        payment = SubcontractPayment(
            subcontract_id=certificacion.subcontrato_id,
            fecha=date.today(),
            concepto=f"CERTIFICACIÓN #{certificacion.id} · {solicitud.concepto}",
            monto_capturado=monto,
            tipo_monto="SIN_IVA",
            monto_sin_iva=monto,
            metodo_pago=method.nombre,
            payment_method_id=method.id,
            company_id=company.id,
            notas=(form.comentario.data or "").strip() or None,
            created_by_id=current_user.id,
        )
        db.session.add(payment)
        db.session.flush()
        certificacion.estado = "aprobada"
        certificacion.monto_aprobado = monto
        certificacion.pago_generado_id = payment.id
        solicitud.estado = "certificada"

    certificacion.supervisor_id = current_user.id
    certificacion.fecha_aprobacion = utc_now()
    certificacion.comentario = (form.comentario.data or "").strip() or None
    notificar(
        [solicitud.usuario],
        "CERTIFICACION_RESUELTA",
        f"La certificación #{certificacion.id} fue {certificacion.estado}.",
        url_for("campo.certificacion_detalle", certificacion_id=certificacion.id),
    )
    auditar(
        current_user.id,
        "RESOLVER_CERTIFICACION",
        "certificaciones_subcontratos",
        certificacion.id,
        certificacion.estado,
    )
    db.session.commit()
    flash(f"Certificación {certificacion.estado}.", "success")
    return redirect(
        url_for("campo.certificacion_detalle", certificacion_id=certificacion.id)
    )


@campo_bp.get("/certificaciones/<int:certificacion_id>/archivo")
@permission_required("certificaciones", "ver")
def certificacion_archivo(certificacion_id):
    certificacion = db.get_or_404(CertificacionSubcontrato, certificacion_id)
    verificar_acceso_obra(current_user, certificacion.subcontrato.project_id)
    if not certificacion.solicitud_pago.archivo_adjunto:
        abort(404)
    try:
        path = archivo_fase5_absoluto(certificacion.solicitud_pago.archivo_adjunto)
    except FileNotFoundError:
        abort(404)
    return send_file(path, as_attachment=True)


# ---------------------------------------------------------------------------
# No conformidades
# ---------------------------------------------------------------------------


@campo_bp.get("/no-conformidades")
@permission_required("no_conformidades", "ver")
def no_conformidades_lista():
    project_ids = [obra.id for obra in obras_accesibles(current_user, incluir_inactivas=True)]
    query = NoConformidad.query.options(
        joinedload(NoConformidad.centro_costo)
    ).filter(NoConformidad.centro_costo_id.in_(project_ids or [-1]))
    estado = request.args.get("estado", "abiertas")
    if estado == "abiertas":
        query = query.filter(NoConformidad.estado != "cerrada")
    elif estado in {"abierta", "en_proceso", "cerrada"}:
        query = query.filter(NoConformidad.estado == estado)
    ncrs = query.order_by(NoConformidad.fecha_limite, NoConformidad.id).all()
    return render_template(
        "campo/ncr/lista.html",
        ncrs=ncrs,
        estado=estado,
        action_form=ActionFormFase5(),
    )


def _ncr_form(ncr: NoConformidad):
    creating = ncr.id is None
    form = NoConformidadForm(obj=ncr)
    form.centro_costo_id.choices = _obras_choices()
    if form.validate_on_submit():
        project = _load_project(form.centro_costo_id.data)
        try:
            evidencia = guardar_archivo(form.evidencia_foto.data, "ncr")
            ncr.centro_costo_id = project.id
            ncr.descripcion = form.descripcion.data.strip()
            ncr.ubicacion = form.ubicacion.data.strip()
            ncr.severidad = form.severidad.data
            ncr.responsable = form.responsable.data.strip()
            ncr.fecha_deteccion = form.fecha_deteccion.data
            ncr.fecha_limite = form.fecha_limite.data
            ncr.estado = form.estado.data
            if creating:
                ncr.usuario_reporta_id = current_user.id
            if evidencia:
                ncr.evidencia_foto = evidencia
            db.session.add(ncr)
            db.session.flush()
            auditar(
                current_user.id,
                "CREAR_NCR" if creating else "EDITAR_NCR",
                "no_conformidades",
                ncr.id,
                ncr.responsable,
            )
            db.session.commit()
        except (OSError, ValueError) as exc:
            db.session.rollback()
            flash(f"No fue posible guardar la evidencia: {exc}", "danger")
        else:
            flash("No conformidad guardada.", "success")
            return redirect(
                url_for("campo.no_conformidad_detalle", ncr_id=ncr.id)
            )
    return render_template(
        "campo/ncr/formulario.html", form=form, ncr=ncr, creating=creating
    )


@campo_bp.route("/no-conformidades/nueva", methods=["GET", "POST"])
@permission_required("no_conformidades", "crear")
def no_conformidad_nueva():
    return _ncr_form(
        NoConformidad(
            fecha_deteccion=date.today(), fecha_limite=date.today(), estado="abierta"
        )
    )


@campo_bp.get("/no-conformidades/<int:ncr_id>")
@permission_required("no_conformidades", "ver")
def no_conformidad_detalle(ncr_id):
    ncr = db.get_or_404(NoConformidad, ncr_id)
    verificar_acceso_obra(current_user, ncr.centro_costo_id)
    return render_template(
        "campo/ncr/detalle.html",
        ncr=ncr,
        cierre_form=CierreNoConformidadForm(),
        action_form=ActionFormFase5(),
    )


@campo_bp.route("/no-conformidades/<int:ncr_id>/editar", methods=["GET", "POST"])
@permission_required("no_conformidades", "editar")
def no_conformidad_editar(ncr_id):
    ncr = db.get_or_404(NoConformidad, ncr_id)
    verificar_acceso_obra(current_user, ncr.centro_costo_id)
    if ncr.estado == "cerrada":
        flash("Una NCR cerrada conserva su trazabilidad y ya no puede editarse.", "danger")
        return redirect(url_for("campo.no_conformidad_detalle", ncr_id=ncr.id))
    return _ncr_form(ncr)


@campo_bp.post("/no-conformidades/<int:ncr_id>/cerrar")
@permission_required("no_conformidades", "editar")
def no_conformidad_cerrar(ncr_id):
    ncr = db.get_or_404(NoConformidad, ncr_id)
    verificar_acceso_obra(current_user, ncr.centro_costo_id)
    form = CierreNoConformidadForm()
    if form.validate_on_submit():
        try:
            evidencia = guardar_archivo(form.evidencia_cierre.data, "ncr_cierres")
            ncr.estado = "cerrada"
            ncr.fecha_cierre = date.today()
            ncr.usuario_resuelve_id = current_user.id
            ncr.accion_correctiva = form.accion_correctiva.data.strip()
            ncr.evidencia_cierre = evidencia
            auditar(
                current_user.id,
                "CERRAR_NCR",
                "no_conformidades",
                ncr.id,
                ncr.accion_correctiva,
            )
            db.session.commit()
        except (OSError, ValueError) as exc:
            db.session.rollback()
            flash(f"No fue posible cerrar la NCR: {exc}", "danger")
        else:
            flash("No conformidad cerrada con evidencia.", "success")
    else:
        flash("La acción correctiva y la evidencia son obligatorias.", "danger")
    return redirect(url_for("campo.no_conformidad_detalle", ncr_id=ncr.id))


@campo_bp.post("/no-conformidades/<int:ncr_id>/eliminar")
@permission_required("no_conformidades", "eliminar")
def no_conformidad_eliminar(ncr_id):
    form = ActionFormFase5()
    if not form.validate_on_submit():
        abort(400)
    ncr = db.get_or_404(NoConformidad, ncr_id)
    verificar_acceso_obra(current_user, ncr.centro_costo_id)
    if ncr.estado == "cerrada":
        flash("Una NCR cerrada no puede eliminarse.", "danger")
    else:
        auditar(current_user.id, "ELIMINAR_NCR", "no_conformidades", ncr.id)
        db.session.delete(ncr)
        db.session.commit()
        flash("No conformidad eliminada.", "success")
    return redirect(url_for("campo.no_conformidades_lista"))


@campo_bp.get("/no-conformidades/<int:ncr_id>/evidencia/<tipo>")
@permission_required("no_conformidades", "ver")
def no_conformidad_evidencia(ncr_id, tipo):
    ncr = db.get_or_404(NoConformidad, ncr_id)
    verificar_acceso_obra(current_user, ncr.centro_costo_id)
    relative = ncr.evidencia_foto if tipo == "apertura" else ncr.evidencia_cierre
    if tipo not in {"apertura", "cierre"} or not relative:
        abort(404)
    try:
        path = archivo_fase5_absoluto(relative)
    except FileNotFoundError:
        abort(404)
    return send_file(path)


# ---------------------------------------------------------------------------
# RFIs
# ---------------------------------------------------------------------------


def _verificar_rfi(rfi: RFI):
    verificar_acceso_obra(current_user, rfi.centro_costo_id)


@campo_bp.get("/rfis")
@permission_required("rfis", "ver")
def rfis_lista():
    project_ids = [obra.id for obra in obras_accesibles(current_user, incluir_inactivas=True)]
    rfis = (
        RFI.query.options(joinedload(RFI.centro_costo))
        .filter(
            db.or_(
                RFI.centro_costo_id.in_(project_ids or [-1]),
                RFI.usuario_solicita_id == current_user.id,
                RFI.destinatario_id == current_user.id,
            )
        )
        .order_by(RFI.fecha_creacion.desc())
        .all()
    )
    return render_template("campo/rfis/lista.html", rfis=rfis)


@campo_bp.route("/rfis/nueva", methods=["GET", "POST"])
@permission_required("rfis", "crear")
def rfi_nueva():
    form = RFIForm()
    form.centro_costo_id.choices = _obras_choices()
    form.destinatario_id.choices = [
        (usuario.id, f"{usuario.nombre_completo} · {usuario.rol_etiqueta}")
        for usuario in Usuario.query.filter(
            Usuario.activo.is_(True), Usuario.id != current_user.id
        ).order_by(Usuario.nombre_completo)
    ]
    if form.validate_on_submit():
        project = _load_project(form.centro_costo_id.data)
        destinatario = db.session.get(Usuario, form.destinatario_id.data)
        if not destinatario or not destinatario.activo:
            abort(404)
        try:
            archivo = guardar_archivo(form.archivo_adjunto.data, "rfis")
            rfi = RFI(
                centro_costo_id=project.id,
                asunto=form.asunto.data.strip(),
                descripcion=form.descripcion.data.strip(),
                estado="abierta",
                usuario_solicita_id=current_user.id,
                destinatario_id=destinatario.id,
                archivo_adjunto=archivo,
            )
            db.session.add(rfi)
            db.session.flush()
            db.session.add(
                RFIEvento(
                    rfi_id=rfi.id,
                    usuario_id=current_user.id,
                    accion="creada",
                    detalle=rfi.descripcion,
                    archivo_adjunto=archivo,
                )
            )
            notificar(
                [destinatario],
                "NUEVA_RFI",
                f"Nueva RFI #{rfi.id}: {rfi.asunto}",
                url_for("campo.rfi_detalle", rfi_id=rfi.id),
            )
            auditar(current_user.id, "CREAR_RFI", "rfis", rfi.id, rfi.asunto)
            db.session.commit()
        except (OSError, ValueError) as exc:
            db.session.rollback()
            flash(f"No fue posible enviar la RFI: {exc}", "danger")
        else:
            flash("RFI enviada y destinatario notificado.", "success")
            return redirect(url_for("campo.rfi_detalle", rfi_id=rfi.id))
    return render_template("campo/rfis/formulario.html", form=form)


@campo_bp.get("/rfis/<int:rfi_id>")
@permission_required("rfis", "ver")
def rfi_detalle(rfi_id):
    rfi = db.get_or_404(RFI, rfi_id)
    _verificar_rfi(rfi)
    return render_template(
        "campo/rfis/detalle.html",
        rfi=rfi,
        respuesta_form=RFIRespuestaForm(),
        action_form=ActionFormFase5(),
    )


@campo_bp.post("/rfis/<int:rfi_id>/responder")
@permission_required("rfis", "editar")
def rfi_responder(rfi_id):
    rfi = db.get_or_404(RFI, rfi_id)
    _verificar_rfi(rfi)
    if current_user.id != rfi.destinatario_id:
        abort(403)
    form = RFIRespuestaForm()
    if form.validate_on_submit():
        try:
            archivo = guardar_archivo(form.archivo_respuesta.data, "rfi_respuestas")
            rfi.respuesta = form.respuesta.data.strip()
            rfi.archivo_respuesta = archivo
            rfi.usuario_responde_id = current_user.id
            rfi.fecha_respuesta = utc_now()
            rfi.estado = "respondida"
            db.session.add(
                RFIEvento(
                    rfi_id=rfi.id,
                    usuario_id=current_user.id,
                    accion="respondida",
                    detalle=rfi.respuesta,
                    archivo_adjunto=archivo,
                )
            )
            notificar(
                [rfi.usuario_solicita],
                "RFI_RESPONDIDA",
                f"La RFI #{rfi.id} fue respondida.",
                url_for("campo.rfi_detalle", rfi_id=rfi.id),
            )
            auditar(current_user.id, "RESPONDER_RFI", "rfis", rfi.id)
            db.session.commit()
        except (OSError, ValueError) as exc:
            db.session.rollback()
            flash(f"No fue posible guardar la respuesta: {exc}", "danger")
        else:
            flash("Respuesta guardada y solicitante notificado.", "success")
    return redirect(url_for("campo.rfi_detalle", rfi_id=rfi.id))


@campo_bp.post("/rfis/<int:rfi_id>/cerrar")
@permission_required("rfis", "editar")
def rfi_cerrar(rfi_id):
    rfi = db.get_or_404(RFI, rfi_id)
    _verificar_rfi(rfi)
    if current_user.id != rfi.usuario_solicita_id:
        abort(403)
    form = ActionFormFase5()
    if not form.validate_on_submit():
        abort(400)
    if rfi.estado != "respondida":
        flash("Solo puede cerrarse una RFI respondida.", "danger")
    else:
        rfi.estado = "cerrada"
        db.session.add(
            RFIEvento(
                rfi_id=rfi.id,
                usuario_id=current_user.id,
                accion="cerrada",
                detalle=(form.comentario.data or "").strip() or None,
            )
        )
        auditar(current_user.id, "CERRAR_RFI", "rfis", rfi.id)
        db.session.commit()
        flash("RFI cerrada.", "success")
    return redirect(url_for("campo.rfi_detalle", rfi_id=rfi.id))


@campo_bp.get("/rfis/<int:rfi_id>/archivo/<tipo>")
@permission_required("rfis", "ver")
def rfi_archivo(rfi_id, tipo):
    rfi = db.get_or_404(RFI, rfi_id)
    _verificar_rfi(rfi)
    relative = rfi.archivo_adjunto if tipo == "consulta" else rfi.archivo_respuesta
    if tipo not in {"consulta", "respuesta"} or not relative:
        abort(404)
    try:
        path = archivo_fase5_absoluto(relative)
    except FileNotFoundError:
        abort(404)
    return send_file(path, as_attachment=True)


# ---------------------------------------------------------------------------
# Seguridad y salud en obra
# ---------------------------------------------------------------------------


@campo_bp.get("/seguridad")
@permission_required("seguridad_obra", "ver")
def seguridad_lista():
    project_ids = [obra.id for obra in obras_accesibles(current_user, incluir_inactivas=True)]
    reportes = (
        ReporteHSE.query.options(joinedload(ReporteHSE.centro_costo))
        .filter(ReporteHSE.centro_costo_id.in_(project_ids or [-1]))
        .order_by(ReporteHSE.fecha.desc(), ReporteHSE.id.desc())
        .all()
    )
    permisos = (
        PermisoTrabajo.query.options(joinedload(PermisoTrabajo.centro_costo))
        .filter(PermisoTrabajo.centro_costo_id.in_(project_ids or [-1]))
        .order_by(PermisoTrabajo.fecha_inicio.desc())
        .all()
    )
    return render_template(
        "campo/seguridad/lista.html", reportes=reportes, permisos=permisos
    )


def _reporte_hse_form(reporte: ReporteHSE):
    creating = reporte.id is None
    form = ReporteHSEForm(obj=reporte)
    form.centro_costo_id.choices = _obras_choices()
    if form.validate_on_submit():
        project = _load_project(form.centro_costo_id.data)
        reporte.centro_costo_id = project.id
        reporte.tipo = form.tipo.data
        reporte.descripcion = form.descripcion.data.strip()
        reporte.ubicacion = form.ubicacion.data.strip()
        reporte.fecha = form.fecha.data
        reporte.acciones = (form.acciones.data or "").strip() or None
        reporte.estado = form.estado.data
        if creating:
            reporte.usuario_reporta_id = current_user.id
        db.session.add(reporte)
        db.session.flush()
        auditar(
            current_user.id,
            "CREAR_REPORTE_HSE" if creating else "EDITAR_REPORTE_HSE",
            "reportes_hse",
            reporte.id,
            reporte.tipo,
        )
        db.session.commit()
        flash("Reporte HSE guardado.", "success")
        return redirect(url_for("campo.seguridad_lista"))
    return render_template(
        "campo/seguridad/reporte_formulario.html",
        form=form,
        reporte=reporte,
        creating=creating,
    )


@campo_bp.route("/seguridad/reportes/nuevo", methods=["GET", "POST"])
@permission_required("seguridad_obra", "crear")
def reporte_hse_nuevo():
    return _reporte_hse_form(ReporteHSE(fecha=date.today(), estado="abierta"))


@campo_bp.route("/seguridad/reportes/<int:reporte_id>/editar", methods=["GET", "POST"])
@permission_required("seguridad_obra", "editar")
def reporte_hse_editar(reporte_id):
    reporte = db.get_or_404(ReporteHSE, reporte_id)
    verificar_acceso_obra(current_user, reporte.centro_costo_id)
    return _reporte_hse_form(reporte)


@campo_bp.route("/seguridad/permisos/nuevo", methods=["GET", "POST"])
@permission_required("seguridad_obra", "crear")
def permiso_trabajo_nuevo():
    form = PermisoTrabajoForm()
    form.centro_costo_id.choices = _obras_choices()
    if form.validate_on_submit():
        project = _load_project(form.centro_costo_id.data)
        if form.fecha_inicio.data < datetime.now().replace(
            second=0, microsecond=0
        ):
            form.fecha_inicio.errors.append("El inicio no puede estar en el pasado.")
        else:
            permiso = PermisoTrabajo(
                centro_costo_id=project.id,
                tipo=form.tipo.data,
                fecha_inicio=form.fecha_inicio.data,
                fecha_fin=form.fecha_fin.data,
                descripcion=(form.descripcion.data or "").strip() or None,
                ubicacion=(form.ubicacion.data or "").strip() or None,
                solicitado_por_id=current_user.id,
                estado="pendiente",
            )
            db.session.add(permiso)
            db.session.flush()
            notificar(
                usuarios_con_permiso(
                    "seguridad_obra", "aprobar", centro_costo_id=project.id
                ),
                "PERMISO_TRABAJO_PENDIENTE",
                f"Permiso de trabajo #{permiso.id} pendiente de aprobación.",
                url_for("campo.permiso_trabajo_detalle", permiso_id=permiso.id),
            )
            auditar(
                current_user.id,
                "SOLICITAR_PERMISO_TRABAJO",
                "permisos_trabajo",
                permiso.id,
                permiso.tipo,
            )
            db.session.commit()
            flash("Permiso enviado para aprobación.", "success")
            return redirect(
                url_for("campo.permiso_trabajo_detalle", permiso_id=permiso.id)
            )
    return render_template("campo/seguridad/permiso_formulario.html", form=form)


@campo_bp.get("/seguridad/permisos/<int:permiso_id>")
@permission_required("seguridad_obra", "ver")
def permiso_trabajo_detalle(permiso_id):
    permiso = db.get_or_404(PermisoTrabajo, permiso_id)
    verificar_acceso_obra(current_user, permiso.centro_costo_id)
    return render_template(
        "campo/seguridad/permiso_detalle.html",
        permiso=permiso,
        action_form=ActionFormFase5(),
    )


@campo_bp.post("/seguridad/permisos/<int:permiso_id>/aprobar")
@permission_required("seguridad_obra", "aprobar")
def permiso_trabajo_aprobar(permiso_id):
    permiso = db.get_or_404(PermisoTrabajo, permiso_id)
    verificar_acceso_obra(current_user, permiso.centro_costo_id)
    form = ActionFormFase5()
    ahora = datetime.now(permiso.fecha_inicio.tzinfo).replace(
        second=0, microsecond=0
    )
    if not form.validate_on_submit():
        abort(400)
    if permiso.estado != "pendiente":
        flash("El permiso ya fue resuelto.", "info")
    elif permiso.fecha_inicio < ahora:
        flash(
            "No puede aprobarse un permiso después de que el trabajo debía iniciar.",
            "danger",
        )
    else:
        permiso.estado = "aprobado"
        permiso.supervisor_aprueba_id = current_user.id
        permiso.fecha_aprobacion = utc_now()
        auditar(
            current_user.id,
            "APROBAR_PERMISO_TRABAJO",
            "permisos_trabajo",
            permiso.id,
            permiso.tipo,
        )
        db.session.commit()
        flash("Permiso aprobado antes del inicio del trabajo.", "success")
    return redirect(
        url_for("campo.permiso_trabajo_detalle", permiso_id=permiso.id)
    )


@campo_bp.post("/seguridad/permisos/<int:permiso_id>/cerrar")
@permission_required("seguridad_obra", "editar")
def permiso_trabajo_cerrar(permiso_id):
    permiso = db.get_or_404(PermisoTrabajo, permiso_id)
    verificar_acceso_obra(current_user, permiso.centro_costo_id)
    form = ActionFormFase5()
    if not form.validate_on_submit():
        abort(400)
    if permiso.estado != "aprobado":
        flash("Solo puede cerrarse un permiso previamente aprobado.", "danger")
    else:
        permiso.estado = "cerrado"
        auditar(
            current_user.id,
            "CERRAR_PERMISO_TRABAJO",
            "permisos_trabajo",
            permiso.id,
            (form.comentario.data or "").strip() or None,
        )
        db.session.commit()
        flash("Permiso de trabajo cerrado.", "success")
    return redirect(
        url_for("campo.permiso_trabajo_detalle", permiso_id=permiso.id)
    )


# ---------------------------------------------------------------------------
# Garantías de obras terminadas
# ---------------------------------------------------------------------------


def _obras_principales_garantia() -> list[CentroCosto]:
    query = CentroCosto.query.filter(
        CentroCosto.tipo == "obra",
        CentroCosto.estado.in_(("cerrada", "inactiva", "finalizada")),
    )
    if not current_user.acceso_global_obras:
        allowed_ids = {
            work.id
            for work in obras_accesibles(
                current_user,
                incluir_inactivas=True,
                respetar_obra_activa=False,
            )
        }
        query = query.filter(CentroCosto.id.in_(allowed_ids or [-1]))
    return query.order_by(CentroCosto.nombre).all()


def _garantia_or_404(garantia_id: int) -> GarantiaObra:
    warranty = (
        GarantiaObra.query.options(
            joinedload(GarantiaObra.obra_principal),
            joinedload(GarantiaObra.centro_garantia),
            joinedload(GarantiaObra.supervisor),
        )
        .filter_by(id=garantia_id)
        .first_or_404()
    )
    if not current_user.acceso_global_obras:
        if warranty.supervisor_id != current_user.id:
            abort(404)
        verificar_asignacion_obra(
            current_user,
            warranty.centro_garantia_id,
        )
    return warranty


def _clone_warranty_explosion(
    main_work: CentroCosto,
    warranty_center: CentroCosto,
) -> ExplosionRevision | None:
    source_revision = revision_explosion_vigente(main_work.id)
    if not source_revision:
        source_revision = (
            ExplosionRevision.query.filter(
                ExplosionRevision.project_id == main_work.id,
                ExplosionRevision.estado != "CANCELADA",
            )
            .order_by(
                ExplosionRevision.numero_revision.desc(),
                ExplosionRevision.id.desc(),
            )
            .first()
        )
    if not source_revision:
        return None

    revision = ExplosionRevision(
        project_id=warranty_center.id,
        numero_revision=siguiente_revision_explosion(warranty_center.id),
        estado="VIGENTE",
        es_vigente=True,
        archivo_origen=f"Garantía desde revisión {source_revision.numero_revision}",
        observaciones=(
            f"Clasificación histórica de {main_work.codigo}; "
            "no constituye presupuesto de ejecución adicional."
        ),
        obra_origen_id=main_work.id,
        loaded_by_id=current_user.id,
    )
    db.session.add(revision)
    db.session.flush()

    budget_map: dict[int, BudgetItem] = {}

    def clone_budget(source: BudgetItem) -> BudgetItem:
        cached = budget_map.get(source.id)
        if cached:
            return cached
        parent = clone_budget(source.parent) if source.parent else None
        cloned = BudgetItem(
            project_id=warranty_center.id,
            parent_id=parent.id if parent else None,
            codigo=source.codigo,
            nombre=source.nombre,
            categoria=source.categoria,
            presupuesto=0,
            cantidad_objetivo=0,
            unidad_medida=source.unidad_medida,
            porcentaje_avance_real=0,
            activa=True,
        )
        db.session.add(cloned)
        db.session.flush()
        budget_map[source.id] = cloned
        return cloned

    for source in source_revision.items:
        if source.origen == "SMNC":
            # La garantía parte de lo presupuestado históricamente, no de
            # ampliaciones posteriores de la ejecución original.
            continue
        budget = clone_budget(source.budget_item)
        revision.items.append(
            BudgetExplosionItem(
                project_id=warranty_center.id,
                budget_item_id=budget.id,
                supply_item_id=source.supply_item_id,
                cantidad_presupuestada=source.cantidad_presupuestada,
                precio_unitario_sin_iva=source.precio_unitario_sin_iva,
                importe_presupuestado=source.importe_presupuestado,
                clasificacion=source.clasificacion,
                requiere_autorizacion_previa=(
                    source.requiere_autorizacion_previa
                ),
                observacion_clasificacion=source.observacion_clasificacion,
                source_explosion_item_id=source.id,
                origen="GARANTIA_HISTORICA",
                activo=True,
                created_by_id=current_user.id,
            )
        )
    return revision


def _warranty_costs(warranty: GarantiaObra) -> tuple[Decimal, Decimal]:
    committed = money(
        db.session.query(
            func.coalesce(func.sum(PurchaseOrderLine.importe_sin_iva), 0)
        )
        .join(PurchaseOrder)
        .filter(
            PurchaseOrder.project_id == warranty.centro_garantia_id,
            PurchaseOrder.estado.in_(ACTIVE_ORDER_STATES),
        )
        .scalar()
    )
    paid = money(
        db.session.query(func.coalesce(func.sum(AdditionalPayment.monto_sin_iva), 0))
        .filter(AdditionalPayment.project_id == warranty.centro_garantia_id)
        .scalar()
    )
    return committed, paid


@campo_bp.get("/garantias")
@permission_required("garantias", "ver")
def garantias_lista():
    query = GarantiaObra.query.options(
        joinedload(GarantiaObra.obra_principal),
        joinedload(GarantiaObra.centro_garantia),
        joinedload(GarantiaObra.supervisor),
    )
    if not current_user.acceso_global_obras:
        query = query.filter(GarantiaObra.supervisor_id == current_user.id)
    warranties = query.order_by(GarantiaObra.fecha_creacion.desc()).all()
    for warranty in warranties:
        warranty.costo_comprometido, warranty.costo_pagado = _warranty_costs(
            warranty
        )
    return render_template(
        "campo/garantias/lista.html",
        garantias=warranties,
    )


@campo_bp.route("/garantias/nueva", methods=["GET", "POST"])
@permission_required("garantias", "crear")
def garantia_nueva():
    form = GarantiaObraForm()
    main_works = _obras_principales_garantia()
    supervisors = (
        Usuario.query.filter_by(rol="supervisor", activo=True)
        .order_by(Usuario.nombre_completo)
        .all()
    )
    form.obra_principal_id.choices = [
        (work.id, f"{work.codigo} · {work.nombre}") for work in main_works
    ]
    form.supervisor_id.choices = [
        (user.id, user.nombre_completo) for user in supervisors
    ]
    if current_user.es_supervisor:
        form.supervisor_id.choices = [
            (current_user.id, current_user.nombre_completo)
        ]
        form.supervisor_id.data = current_user.id
    if form.validate_on_submit():
        main_work = db.session.get(CentroCosto, form.obra_principal_id.data)
        supervisor = db.session.get(Usuario, form.supervisor_id.data)
        valid_main_ids = {work.id for work in main_works}
        if not main_work or main_work.id not in valid_main_ids:
            abort(404)
        if not supervisor or supervisor.rol != "supervisor" or not supervisor.activo:
            abort(404)
        try:
            evidence = guardar_archivo(
                form.evidencia_inicial.data, "garantias/inicial"
            )
            sequence = (
                GarantiaObra.query.filter_by(
                    obra_principal_id=main_work.id
                ).count()
                + 1
            )
            center = CentroCosto(
                nombre=f"Garantía {main_work.nombre} #{sequence}",
                codigo=f"GAR-{main_work.codigo}-{sequence:03d}"[:40],
                tipo="garantia",
                estado="activa",
                fecha_apertura=date.today(),
                fecha_cierre=None,
                presupuesto_total=0,
                presupuesto_mano_obra=0,
                descripcion=(
                    "Centro independiente para costos de garantía; "
                    f"obra principal {main_work.codigo}."
                ),
                obra_principal_id=main_work.id,
            )
            db.session.add(center)
            db.session.flush()
            warranty = GarantiaObra(
                obra_principal_id=main_work.id,
                centro_garantia_id=center.id,
                supervisor_id=supervisor.id,
                reportada_por_id=current_user.id,
                descripcion=form.descripcion.data.strip(),
                ubicacion=form.ubicacion.data.strip(),
                motivo=form.motivo.data.strip(),
                evidencia_inicial=evidence,
                estado="reportada",
            )
            db.session.add(warranty)
            # El centro hijo hereda el alcance operativo de la obra principal
            # (Compras/Almacén incluidos) sin convertirla de nuevo en activa.
            scoped_users = {
                user.id: user
                for user in main_work.users
                if user.activo
            }
            scoped_users[supervisor.id] = supervisor
            for user in scoped_users.values():
                if center not in user.projects:
                    user.projects.append(center)
            source_revision = _clone_warranty_explosion(main_work, center)
            if not source_revision:
                db.session.add(
                    BudgetItem(
                        project_id=center.id,
                        codigo="GARANTIA",
                        nombre="Trabajos de garantía",
                        categoria="ADICIONAL",
                        presupuesto=0,
                        cantidad_objetivo=0,
                        unidad_medida=None,
                        porcentaje_avance_real=0,
                        activa=True,
                    )
                )
            db.session.flush()
            auditar(
                current_user.id,
                "REPORTAR_GARANTIA",
                "garantias_obras",
                warranty.id,
                (
                    f"{main_work.codigo} → {center.codigo}; "
                    f"explosión histórica: {'sí' if source_revision else 'no'}"
                ),
            )
            db.session.commit()
        except (IntegrityError, OSError, ValueError) as exc:
            db.session.rollback()
            flash(f"No fue posible reportar la garantía: {exc}", "danger")
        else:
            notificar(
                [supervisor],
                "GARANTIA_ASIGNADA",
                f"Se te asignó la garantía #{warranty.id} de {main_work.nombre}.",
                url_for("campo.garantia_detalle", garantia_id=warranty.id),
            )
            db.session.commit()
            flash(
                "Garantía reportada sin reactivar la obra principal.",
                "success",
            )
            return redirect(
                url_for("campo.garantia_detalle", garantia_id=warranty.id)
            )
    return render_template(
        "campo/garantias/formulario.html",
        form=form,
    )


@campo_bp.get("/garantias/<int:garantia_id>")
@permission_required("garantias", "ver")
def garantia_detalle(garantia_id):
    warranty = _garantia_or_404(garantia_id)
    committed, paid = _warranty_costs(warranty)
    return render_template(
        "campo/garantias/detalle.html",
        garantia=warranty,
        costo_comprometido=committed,
        costo_pagado=paid,
        decision_form=GarantiaDecisionForm(),
        action_form=ActionFormFase5(),
    )


@campo_bp.route(
    "/garantias/<int:garantia_id>/diagnostico",
    methods=["GET", "POST"],
)
@permission_required("garantias", "editar")
def garantia_diagnostico(garantia_id):
    warranty = _garantia_or_404(garantia_id)
    if warranty.estado not in {"reportada", "diagnostico"}:
        flash("La garantía ya superó la etapa de diagnóstico.", "danger")
        return redirect(
            url_for("campo.garantia_detalle", garantia_id=warranty.id)
        )
    form = GarantiaDiagnosticoForm(obj=warranty)
    if form.validate_on_submit():
        warranty.diagnostico = form.diagnostico.data.strip()
        warranty.trabajos_requeridos = form.trabajos_requeridos.data.strip()
        warranty.fecha_diagnostico = utc_now()
        warranty.estado = "diagnostico"
        auditar(
            current_user.id,
            "DIAGNOSTICAR_GARANTIA",
            "garantias_obras",
            warranty.id,
        )
        db.session.commit()
        flash("Diagnóstico registrado.", "success")
        return redirect(
            url_for("campo.garantia_detalle", garantia_id=warranty.id)
        )
    return render_template(
        "campo/garantias/diagnostico.html",
        garantia=warranty,
        form=form,
    )


@campo_bp.post("/garantias/<int:garantia_id>/resolver")
@permission_required("garantias", "aprobar")
def garantia_resolver(garantia_id):
    warranty = _garantia_or_404(garantia_id)
    form = GarantiaDecisionForm()
    if not form.validate_on_submit():
        abort(400)
    if warranty.estado != "diagnostico":
        flash("La garantía debe tener diagnóstico antes de resolverse.", "danger")
    elif form.decision.data == "autorizar":
        warranty.estado = "autorizada"
        warranty.autorizada_por_id = current_user.id
        warranty.fecha_autorizacion = utc_now()
        auditar(
            current_user.id,
            "AUTORIZAR_GARANTIA",
            "garantias_obras",
            warranty.id,
            form.comentario.data,
        )
        db.session.commit()
        flash("Garantía autorizada.", "success")
    else:
        warranty.estado = "rechazada"
        warranty.rechazada_por_id = current_user.id
        warranty.motivo_rechazo = form.comentario.data.strip()
        warranty.centro_garantia.estado = "cerrada"
        warranty.centro_garantia.fecha_cierre = date.today()
        auditar(
            current_user.id,
            "RECHAZAR_GARANTIA",
            "garantias_obras",
            warranty.id,
            warranty.motivo_rechazo,
        )
        db.session.commit()
        flash("Reporte rechazado como garantía.", "success")
    return redirect(url_for("campo.garantia_detalle", garantia_id=warranty.id))


@campo_bp.post("/garantias/<int:garantia_id>/iniciar")
@permission_required("garantias", "editar")
def garantia_iniciar(garantia_id):
    warranty = _garantia_or_404(garantia_id)
    form = ActionFormFase5()
    if not form.validate_on_submit():
        abort(400)
    if warranty.estado != "autorizada":
        flash("Solo puede iniciarse una garantía autorizada.", "danger")
    else:
        warranty.estado = "en_ejecucion"
        warranty.fecha_inicio = utc_now()
        auditar(
            current_user.id,
            "INICIAR_GARANTIA",
            "garantias_obras",
            warranty.id,
            form.comentario.data,
        )
        db.session.commit()
        flash("Trabajos de garantía iniciados.", "success")
    return redirect(url_for("campo.garantia_detalle", garantia_id=warranty.id))


@campo_bp.route(
    "/garantias/<int:garantia_id>/solicitar-cierre",
    methods=["GET", "POST"],
)
@permission_required("garantias", "editar")
def garantia_solicitar_cierre(garantia_id):
    warranty = _garantia_or_404(garantia_id)
    if warranty.estado != "en_ejecucion":
        flash("La garantía no está en ejecución.", "danger")
        return redirect(
            url_for("campo.garantia_detalle", garantia_id=warranty.id)
        )
    form = GarantiaCierreForm()
    if form.validate_on_submit():
        try:
            evidence = guardar_archivo(
                form.evidencia_final.data, "garantias/final"
            )
            warranty.accion_correctiva = form.accion_correctiva.data.strip()
            warranty.evidencia_final = evidence
            warranty.estado = "pendiente_cierre"
            warranty.fecha_solicitud_cierre = utc_now()
            auditar(
                current_user.id,
                "SOLICITAR_CIERRE_GARANTIA",
                "garantias_obras",
                warranty.id,
            )
            db.session.commit()
        except (OSError, ValueError) as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Cierre enviado para validación.", "success")
            return redirect(
                url_for("campo.garantia_detalle", garantia_id=warranty.id)
            )
    return render_template(
        "campo/garantias/cierre.html",
        garantia=warranty,
        form=form,
    )


@campo_bp.post("/garantias/<int:garantia_id>/cerrar")
@permission_required("garantias", "aprobar")
def garantia_cerrar(garantia_id):
    warranty = _garantia_or_404(garantia_id)
    form = ActionFormFase5()
    if not form.validate_on_submit():
        abort(400)
    if (
        warranty.estado != "pendiente_cierre"
        or not warranty.accion_correctiva
        or not warranty.evidencia_final
    ):
        flash(
            "El cierre requiere acción correctiva y evidencia final.",
            "danger",
        )
    else:
        warranty.estado = "cerrada"
        warranty.cerrada_por_id = current_user.id
        warranty.fecha_cierre = utc_now()
        warranty.centro_garantia.estado = "cerrada"
        warranty.centro_garantia.fecha_cierre = date.today()
        # La obra principal se conserva exactamente en su estado anterior.
        auditar(
            current_user.id,
            "CERRAR_GARANTIA",
            "garantias_obras",
            warranty.id,
            form.comentario.data,
        )
        db.session.commit()
        flash("Garantía cerrada; la obra principal permanece inactiva.", "success")
    return redirect(url_for("campo.garantia_detalle", garantia_id=warranty.id))


@campo_bp.get("/garantias/<int:garantia_id>/evidencia/<tipo>")
@permission_required("garantias", "ver")
def garantia_evidencia(garantia_id, tipo):
    warranty = _garantia_or_404(garantia_id)
    relative = (
        warranty.evidencia_inicial
        if tipo == "inicial"
        else warranty.evidencia_final
        if tipo == "final"
        else None
    )
    if not relative:
        abort(404)
    try:
        path = archivo_fase5_absoluto(relative)
    except FileNotFoundError:
        abort(404)
    return send_file(path, as_attachment=False)
