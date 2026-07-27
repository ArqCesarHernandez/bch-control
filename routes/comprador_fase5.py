"""Licitaciones, contratos y conciliación de facturas de la Fase 5."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user
from flask_mail import Message
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app import mail
from compras_models import (
    ACTIVE_ORDER_STATES,
    PaymentMethod,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequisition,
    Supplier,
)
from fase5_forms import (
    ActionFormFase5,
    AdjudicacionForm,
    ConciliacionDecisionForm,
    ConciliacionFacturaForm,
    ContratoForm,
    ContratoModificacionForm,
    LicitacionForm,
    ModificacionDecisionForm,
    OfertaForm,
)
from fase5_models import (
    ConciliacionFactura,
    Contrato,
    ContratoModificacion,
    Licitacion,
    LicitacionLinea,
    LicitacionProveedor,
    Oferta,
)
from models import CentroCosto, db, utc_now
from nominas_models import Company, decimal_value, money
from routes.compras import next_folio, refresh_requisition_status, today_value
from services.fase5 import (
    archivo_fase5_absoluto,
    auditar,
    guardar_archivo,
    notificar,
    obras_accesibles,
    usuarios_con_permiso,
)
from utils.access import verificar_acceso_obra
from utils.decorators import permission_required


comprador_fase5_bp = Blueprint(
    "comprador_fase5", __name__, url_prefix="/compras"
)


def _obra_choices():
    return [
        (obra.id, f"{obra.codigo} · {obra.nombre}")
        for obra in obras_accesibles(current_user)
    ]


def _proveedor_choices():
    return [
        (supplier.id, f"{supplier.codigo} · {supplier.nombre}")
        for supplier in Supplier.query.filter_by(activo=True).order_by(Supplier.nombre)
    ]


def _requisiciones_licitables():
    project_ids = [obra.id for obra in obras_accesibles(current_user)]
    return (
        PurchaseRequisition.query.options(joinedload(PurchaseRequisition.project))
        .filter(
            PurchaseRequisition.project_id.in_(project_ids or [-1]),
            PurchaseRequisition.estado.in_({"APROBADA", "PARCIAL"}),
            PurchaseRequisition.tipo_requisicion == "COMPRAS",
        )
        .order_by(PurchaseRequisition.fecha_solicitud.desc())
        .all()
    )


def _verificar_licitacion(licitacion: Licitacion):
    verificar_acceso_obra(current_user, licitacion.requisicion.project_id)


def _documento_rfq(licitacion: Licitacion, supplier: Supplier) -> tuple[str, str]:
    lines = [
        "BCH Control · Solicitud de cotización",
        f"Licitación: #{licitacion.id}",
        f"Requisición: {licitacion.requisicion.folio}",
        f"Obra: {licitacion.requisicion.project.codigo} · "
        f"{licitacion.requisicion.project.nombre}",
        f"Fecha límite: {licitacion.fecha_limite:%d/%m/%Y}",
        "",
        "Partidas solicitadas:",
    ]
    released_lines = (
        [item.requisicion_linea for item in licitacion.lineas]
        if licitacion.lineas
        else licitacion.requisicion.lines
    )
    for line in released_lines:
        if line.estado_linea == "APROBADA" and line.cantidad_pendiente_compra > 0:
            lines.append(
                f"- {line.explosion_item.supply_item.clave} · "
                f"{line.explosion_item.supply_item.descripcion}: "
                f"{line.cantidad_pendiente_compra} "
                f"{line.explosion_item.supply_item.unidad}"
            )
    lines.extend(
        [
            "",
            "Favor de indicar precio sin IVA, plazo de entrega y condiciones comerciales.",
            "Este documento es una RFQ y no representa una orden de compra.",
        ]
    )
    subject = (
        f"RFQ BCH Control #{licitacion.id} · "
        f"{licitacion.requisicion.project.codigo}"
    )
    return subject, "\n".join(lines)


# ---------------------------------------------------------------------------
# Licitaciones y ofertas
# ---------------------------------------------------------------------------


@comprador_fase5_bp.get("/licitaciones")
@permission_required("licitaciones", "ver")
def licitaciones_lista():
    project_ids = [obra.id for obra in obras_accesibles(current_user, incluir_inactivas=True)]
    licitaciones = (
        Licitacion.query.options(
            joinedload(Licitacion.requisicion).joinedload(
                PurchaseRequisition.project
            ),
            joinedload(Licitacion.ofertas),
        )
        .join(PurchaseRequisition)
        .filter(PurchaseRequisition.project_id.in_(project_ids or [-1]))
        .order_by(Licitacion.id.desc())
        .all()
    )
    return render_template(
        "compras/fase5/licitaciones/lista.html", licitaciones=licitaciones
    )


@comprador_fase5_bp.route("/licitaciones/nueva", methods=["GET", "POST"])
@permission_required("licitaciones", "crear")
def licitacion_nueva():
    form = LicitacionForm()
    requisiciones = _requisiciones_licitables()
    suppliers = Supplier.query.filter_by(activo=True).order_by(Supplier.nombre).all()
    form.requisicion_id.choices = [
        (
            req.id,
            f"{req.folio} · {req.project.codigo} · "
            f"${req.total_pendiente_compra:,.2f}",
        )
        for req in requisiciones
    ]
    form.proveedor_ids.choices = [
        (supplier.id, supplier.nombre) for supplier in suppliers
    ]
    if form.validate_on_submit():
        requisition = db.session.get(PurchaseRequisition, form.requisicion_id.data)
        if not requisition:
            abort(404)
        verificar_acceso_obra(current_user, requisition.project_id)
        if requisition.estado not in {"APROBADA", "PARCIAL"}:
            form.requisicion_id.errors.append(
                "La requisición ya no está disponible para licitar."
            )
        else:
            invited = Supplier.query.filter(
                Supplier.id.in_(form.proveedor_ids.data),
                Supplier.activo.is_(True),
            ).all()
            if len(invited) != len(set(form.proveedor_ids.data)):
                form.proveedor_ids.errors.append(
                    "Uno de los proveedores ya no está activo."
                )
            else:
                licitacion = (
                    Licitacion.query.filter_by(
                        requisicion_id=requisition.id,
                        estado="preparacion",
                    )
                    .order_by(Licitacion.id)
                    .first()
                )
                if not licitacion:
                    licitacion = Licitacion(
                        requisicion_id=requisition.id,
                        estado="preparacion",
                        fecha_limite=form.fecha_limite.data,
                        creado_por_id=current_user.id,
                    )
                    for line in requisition.lines:
                        if (
                            line.estado_linea == "APROBADA"
                            and line.cantidad_pendiente_compra > 0
                        ):
                            licitacion.lineas.append(
                                LicitacionLinea(requisicion_linea_id=line.id)
                            )
                else:
                    licitacion.fecha_limite = form.fecha_limite.data
                    licitacion.proveedores.clear()
                for supplier in invited:
                    licitacion.proveedores.append(
                        LicitacionProveedor(
                            proveedor_id=supplier.id, estado="invitado"
                        )
                    )
                db.session.add(licitacion)
                db.session.flush()
                auditar(
                    current_user.id,
                    "CREAR_LICITACION",
                    "licitaciones",
                    licitacion.id,
                    requisition.folio,
                )
                db.session.commit()
                flash(
                    "Licitación creada en preparación. Revísala y envía la RFQ.",
                    "success",
                )
                return redirect(
                    url_for(
                        "comprador_fase5.licitacion_detalle",
                        licitacion_id=licitacion.id,
                    )
                )
    return render_template(
        "compras/fase5/licitaciones/formulario.html", form=form
    )


@comprador_fase5_bp.get("/licitaciones/<int:licitacion_id>")
@permission_required("licitaciones", "ver")
def licitacion_detalle(licitacion_id):
    licitacion = db.get_or_404(Licitacion, licitacion_id)
    _verificar_licitacion(licitacion)
    return render_template(
        "compras/fase5/licitaciones/detalle.html",
        licitacion=licitacion,
        action_form=ActionFormFase5(),
    )


@comprador_fase5_bp.post("/licitaciones/<int:licitacion_id>/enviar")
@permission_required("licitaciones", "editar")
def licitacion_enviar(licitacion_id):
    licitacion = db.get_or_404(Licitacion, licitacion_id)
    _verificar_licitacion(licitacion)
    form = ActionFormFase5()
    if not form.validate_on_submit():
        abort(400)
    if licitacion.estado != "preparacion":
        flash("La licitación ya fue enviada o cerrada.", "info")
        return redirect(
            url_for(
                "comprador_fase5.licitacion_detalle",
                licitacion_id=licitacion.id,
            )
        )

    sent = failed = 0
    for invitation in licitacion.proveedores:
        supplier = invitation.proveedor
        subject, body = _documento_rfq(licitacion, supplier)
        if not supplier.email:
            invitation.error_envio = "Proveedor sin correo registrado."
            failed += 1
            continue
        try:
            message = Message(subject=subject, recipients=[supplier.email], body=body)
            if not current_app.config.get("MAIL_SUPPRESS_SEND"):
                if not current_app.config.get("MAIL_SERVER"):
                    raise RuntimeError("MAIL_SERVER no está configurado")
            mail.send(message)
        except Exception as exc:
            invitation.error_envio = str(exc)[:500]
            failed += 1
        else:
            invitation.fecha_envio = utc_now()
            invitation.estado = "enviado"
            invitation.error_envio = None
            sent += 1

    if sent:
        licitacion.estado = "enviada"
    auditar(
        current_user.id,
        "ENVIAR_LICITACION",
        "licitaciones",
        licitacion.id,
        f"Enviadas: {sent}; con error: {failed}",
    )
    db.session.commit()
    if failed:
        flash(
            f"RFQ enviadas: {sent}. Proveedores con error: {failed}; revisa el detalle.",
            "warning",
        )
    else:
        flash(f"RFQ enviada a {sent} proveedor(es).", "success")
    return redirect(
        url_for(
            "comprador_fase5.licitacion_detalle", licitacion_id=licitacion.id
        )
    )


@comprador_fase5_bp.route(
    "/licitaciones/<int:licitacion_id>/ofertas/nueva", methods=["GET", "POST"]
)
@permission_required("licitaciones", "editar")
def oferta_nueva(licitacion_id):
    licitacion = db.get_or_404(Licitacion, licitacion_id)
    _verificar_licitacion(licitacion)
    if licitacion.estado == "cerrada":
        flash("La licitación está cerrada.", "danger")
        return redirect(
            url_for(
                "comprador_fase5.licitacion_detalle",
                licitacion_id=licitacion.id,
            )
        )
    form = OfertaForm()
    invited_ids = {invitation.proveedor_id for invitation in licitacion.proveedores}
    existing_ids = {offer.proveedor_id for offer in licitacion.ofertas}
    available = [
        invitation.proveedor
        for invitation in licitacion.proveedores
        if invitation.proveedor_id not in existing_ids
    ]
    form.proveedor_id.choices = [
        (supplier.id, supplier.nombre) for supplier in available
    ]
    if form.validate_on_submit():
        if form.proveedor_id.data not in invited_ids:
            abort(404)
        try:
            archivo = guardar_archivo(form.archivo_adjunto.data, "ofertas")
            oferta = Oferta(
                licitacion_id=licitacion.id,
                proveedor_id=form.proveedor_id.data,
                monto_total=form.monto_total.data,
                plazo_entrega=form.plazo_entrega.data,
                condiciones=(form.condiciones.data or "").strip() or None,
                archivo_adjunto=archivo,
                estado="recibida",
            )
            db.session.add(oferta)
            invitation = next(
                item
                for item in licitacion.proveedores
                if item.proveedor_id == oferta.proveedor_id
            )
            invitation.estado = "respondido"
            invitation.fecha_respuesta = utc_now()
            db.session.flush()
            auditar(
                current_user.id,
                "REGISTRAR_OFERTA",
                "ofertas",
                oferta.id,
                f"${oferta.monto_total}",
            )
            db.session.commit()
        except (IntegrityError, OSError, ValueError) as exc:
            db.session.rollback()
            flash(f"No fue posible registrar la oferta: {exc}", "danger")
        else:
            flash("Oferta registrada en la matriz comparativa.", "success")
            return redirect(
                url_for(
                    "comprador_fase5.licitacion_matriz",
                    licitacion_id=licitacion.id,
                )
            )
    return render_template(
        "compras/fase5/licitaciones/oferta_formulario.html",
        form=form,
        licitacion=licitacion,
    )


@comprador_fase5_bp.get("/licitaciones/<int:licitacion_id>/matriz")
@permission_required("licitaciones", "ver")
def licitacion_matriz(licitacion_id):
    licitacion = db.get_or_404(Licitacion, licitacion_id)
    _verificar_licitacion(licitacion)
    ofertas = sorted(
        licitacion.ofertas,
        key=lambda offer: (decimal_value(offer.monto_total), offer.plazo_entrega),
    )
    return render_template(
        "compras/fase5/licitaciones/matriz.html",
        licitacion=licitacion,
        ofertas=ofertas,
        action_form=ActionFormFase5(),
    )


@comprador_fase5_bp.post("/licitaciones/<int:licitacion_id>/cerrar")
@permission_required("licitaciones", "editar")
def licitacion_cerrar(licitacion_id):
    licitacion = db.get_or_404(Licitacion, licitacion_id)
    _verificar_licitacion(licitacion)
    form = ActionFormFase5()
    if not form.validate_on_submit():
        abort(400)
    if licitacion.estado == "preparacion":
        flash("Envía la RFQ antes de cerrar la licitación.", "danger")
    elif not licitacion.ofertas:
        flash("Registra por lo menos una oferta antes de cerrar.", "danger")
    else:
        licitacion.estado = "cerrada"
        for offer in licitacion.ofertas:
            if offer.estado == "recibida":
                offer.estado = "evaluada"
        auditar(
            current_user.id,
            "CERRAR_LICITACION",
            "licitaciones",
            licitacion.id,
        )
        db.session.commit()
        flash("Licitación cerrada; ya puede adjudicarse.", "success")
    return redirect(
        url_for(
            "comprador_fase5.licitacion_matriz", licitacion_id=licitacion.id
        )
    )


def _allocate_offer(order: PurchaseOrder, requisition, offer: Oferta):
    rfq_lines = (
        [item.requisicion_linea for item in offer.licitacion.lineas]
        if offer.licitacion.lineas
        else requisition.lines
    )
    eligible = [
        line
        for line in rfq_lines
        if line.estado_linea == "APROBADA" and line.cantidad_pendiente_compra > 0
    ]
    if not eligible:
        raise ValueError("La requisición ya no tiene cantidades pendientes de compra.")
    estimated = [
        money(
            line.cantidad_pendiente_compra
            * decimal_value(line.explosion_item.precio_unitario_sin_iva)
        )
        for line in eligible
    ]
    estimated_total = sum(estimated, Decimal("0"))
    if estimated_total <= 0:
        estimated = [Decimal("1") for _line in eligible]
        estimated_total = Decimal(len(eligible))

    allocated = Decimal("0")
    offer_total = money(offer.monto_total)
    for index, line in enumerate(eligible):
        quantity = decimal_value(line.cantidad_pendiente_compra)
        if index == len(eligible) - 1:
            line_total = money(offer_total - allocated)
        else:
            line_total = money(offer_total * estimated[index] / estimated_total)
            allocated += line_total
        price = (line_total / quantity).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        order.lines.append(
            PurchaseOrderLine(
                requisition_line_id=line.id,
                explosion_item_id=line.explosion_item_id,
                cantidad=quantity,
                precio_unitario_sin_iva=price,
                importe_sin_iva=money(quantity * price),
                notas=f"Precio distribuido desde oferta #{offer.id}; editable en borrador.",
            )
        )


def _create_order_from_offer(
    licitacion: Licitacion, offer: Oferta, form: AdjudicacionForm
) -> PurchaseOrder:
    company = db.session.get(Company, form.company_id.data)
    method = db.session.get(PaymentMethod, form.payment_method_id.data)
    if not company or not company.activa or not method or not method.activo:
        raise ValueError("Selecciona empresa pagadora y método de pago activos.")
    requisition = licitacion.requisicion
    delivery = today_value() + timedelta(days=offer.plazo_entrega)
    order = PurchaseOrder(
        folio=next_folio(PurchaseOrder, "OC"),
        project_id=requisition.project_id,
        requisition_id=requisition.id,
        supplier_id=offer.proveedor_id,
        company_id=company.id,
        buyer_id=current_user.id,
        payment_method_id=method.id,
        fecha_orden=today_value(),
        fecha_entrega_estimada=delivery,
        fecha_limite=requisition.fecha_limite_oc or today_value(),
        tipo_oc="COMPRAS",
        categoria_pago="COMPRAS",
        estado="BORRADOR",
        modalidad_pago="CREDITO",
        requiere_conciliacion=True,
        notas=f"Generada desde licitación #{licitacion.id}, oferta #{offer.id}.",
        direccion_entrega=requisition.project.direccion_entrega,
        created_by_id=current_user.id,
    )
    _allocate_offer(order, requisition, offer)
    db.session.add(order)
    db.session.flush()
    refresh_requisition_status(requisition)
    return order


def _create_contract_from_offer(
    licitacion: Licitacion, offer: Oferta, form: AdjudicacionForm
) -> Contrato:
    if not form.fecha_inicio.data or not form.fecha_fin.data:
        raise ValueError("Captura las fechas de inicio y fin del contrato.")
    if form.fecha_fin.data < form.fecha_inicio.data:
        raise ValueError("La fecha final no puede ser anterior al inicio.")
    conditions = (form.condiciones_pago.data or offer.condiciones or "").strip()
    if not conditions:
        raise ValueError("Captura las condiciones de pago del contrato.")
    contract = Contrato(
        proveedor_id=offer.proveedor_id,
        centro_costo_id=licitacion.requisicion.project_id,
        tipo=form.tipo_contrato.data or "suma_alzada",
        monto_total=offer.monto_total,
        fecha_inicio=form.fecha_inicio.data,
        fecha_fin=form.fecha_fin.data,
        estado="borrador",
        condiciones_pago=conditions,
        retencion_garantia=form.retencion_garantia.data or 0,
        hitos=[],
        licitacion_id=licitacion.id,
        oferta_id=offer.id,
        creado_por_id=current_user.id,
    )
    db.session.add(contract)
    db.session.flush()
    return contract


@comprador_fase5_bp.route(
    "/licitaciones/<int:licitacion_id>/ofertas/<int:oferta_id>/adjudicar",
    methods=["GET", "POST"],
)
@permission_required("licitaciones", "aprobar")
def oferta_adjudicar(licitacion_id, oferta_id):
    licitacion = db.get_or_404(Licitacion, licitacion_id)
    _verificar_licitacion(licitacion)
    offer = db.get_or_404(Oferta, oferta_id)
    if offer.licitacion_id != licitacion.id:
        abort(404)
    if licitacion.estado != "cerrada" or licitacion.oferta_ganadora:
        flash("La licitación debe estar cerrada y sin adjudicación previa.", "danger")
        return redirect(
            url_for(
                "comprador_fase5.licitacion_matriz",
                licitacion_id=licitacion.id,
            )
        )
    form = AdjudicacionForm()
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
    if request.method == "GET":
        form.condiciones_pago.data = offer.condiciones
        form.fecha_inicio.data = date.today()
        form.fecha_fin.data = date.today() + timedelta(days=offer.plazo_entrega)
    if form.validate_on_submit():
        try:
            if form.destino.data == "orden_compra":
                result = _create_order_from_offer(licitacion, offer, form)
            else:
                result = _create_contract_from_offer(licitacion, offer, form)
            offer.estado = "adjudicada"
            offer.adjudicada_por_id = current_user.id
            offer.fecha_adjudicacion = utc_now()
            offer.resultado_tipo = form.destino.data
            offer.resultado_id = result.id
            for other in licitacion.ofertas:
                if other.id != offer.id:
                    other.estado = "rechazada"
            licitacion.adjudicada_por_id = current_user.id
            licitacion.fecha_adjudicacion = utc_now()
            auditar(
                current_user.id,
                "ADJUDICAR_LICITACION",
                "licitaciones",
                licitacion.id,
                f"{form.destino.data} #{result.id}",
            )
            db.session.commit()
        except (ValueError, IntegrityError) as exc:
            db.session.rollback()
            flash(f"No fue posible adjudicar la oferta: {exc}", "danger")
        else:
            flash("Oferta adjudicada y documento generado en borrador.", "success")
            if form.destino.data == "orden_compra":
                return redirect(
                    url_for("compras.order_detail", order_id=result.id)
                )
            return redirect(
                url_for(
                    "comprador_fase5.contrato_detalle", contrato_id=result.id
                )
            )
    return render_template(
        "compras/fase5/licitaciones/adjudicar.html",
        form=form,
        licitacion=licitacion,
        oferta=offer,
    )


@comprador_fase5_bp.get("/ofertas/<int:oferta_id>/archivo")
@permission_required("licitaciones", "ver")
def oferta_archivo(oferta_id):
    offer = db.get_or_404(Oferta, oferta_id)
    _verificar_licitacion(offer.licitacion)
    if not offer.archivo_adjunto:
        abort(404)
    try:
        path = archivo_fase5_absoluto(offer.archivo_adjunto)
    except FileNotFoundError:
        abort(404)
    return send_file(path, as_attachment=True)


# ---------------------------------------------------------------------------
# Contratos y modificaciones
# ---------------------------------------------------------------------------


@comprador_fase5_bp.get("/contratos")
@permission_required("contratos", "ver")
def contratos_lista():
    project_ids = [obra.id for obra in obras_accesibles(current_user, incluir_inactivas=True)]
    contracts = (
        Contrato.query.options(
            joinedload(Contrato.centro_costo), joinedload(Contrato.proveedor)
        )
        .filter(Contrato.centro_costo_id.in_(project_ids or [-1]))
        .order_by(Contrato.id.desc())
        .all()
    )
    return render_template(
        "compras/fase5/contratos/lista.html", contratos=contracts
    )


def _contrato_form(contract: Contrato):
    creating = contract.id is None
    form = ContratoForm(obj=contract)
    form.proveedor_id.choices = _proveedor_choices()
    form.centro_costo_id.choices = _obra_choices()
    if request.method == "GET" and not creating:
        form.hitos_texto.data = "\n".join(
            str(item.get("nombre", "")) for item in (contract.hitos or [])
        )
    if form.validate_on_submit():
        project = db.session.get(CentroCosto, form.centro_costo_id.data)
        supplier = db.session.get(Supplier, form.proveedor_id.data)
        if not project or project.tipo != "obra" or not supplier or not supplier.activo:
            abort(404)
        verificar_acceso_obra(current_user, project.id)
        contract.proveedor_id = supplier.id
        contract.centro_costo_id = project.id
        contract.tipo = form.tipo.data
        contract.monto_total = form.monto_total.data
        contract.fecha_inicio = form.fecha_inicio.data
        contract.fecha_fin = form.fecha_fin.data
        contract.estado = form.estado.data
        contract.condiciones_pago = form.condiciones_pago.data.strip()
        contract.retencion_garantia = form.retencion_garantia.data
        contract.hitos = [
            {"nombre": line.strip(), "estado": "pendiente"}
            for line in (form.hitos_texto.data or "").splitlines()
            if line.strip()
        ]
        if creating:
            contract.creado_por_id = current_user.id
        db.session.add(contract)
        db.session.flush()
        auditar(
            current_user.id,
            "CREAR_CONTRATO" if creating else "EDITAR_CONTRATO",
            "contratos",
            contract.id,
            f"versión {contract.version_actual}",
        )
        db.session.commit()
        flash("Contrato guardado.", "success")
        return redirect(
            url_for(
                "comprador_fase5.contrato_detalle", contrato_id=contract.id
            )
        )
    return render_template(
        "compras/fase5/contratos/formulario.html",
        form=form,
        contrato=contract,
        creating=creating,
    )


@comprador_fase5_bp.route("/contratos/nuevo", methods=["GET", "POST"])
@permission_required("contratos", "crear")
def contrato_nuevo():
    return _contrato_form(
        Contrato(estado="borrador", retencion_garantia=0, hitos=[])
    )


@comprador_fase5_bp.get("/contratos/<int:contrato_id>")
@permission_required("contratos", "ver")
def contrato_detalle(contrato_id):
    contract = db.get_or_404(Contrato, contrato_id)
    verificar_acceso_obra(current_user, contract.centro_costo_id)
    return render_template(
        "compras/fase5/contratos/detalle.html",
        contrato=contract,
        decision_form=ModificacionDecisionForm(),
    )


@comprador_fase5_bp.route(
    "/contratos/<int:contrato_id>/editar", methods=["GET", "POST"]
)
@permission_required("contratos", "editar")
def contrato_editar(contrato_id):
    contract = db.get_or_404(Contrato, contrato_id)
    verificar_acceso_obra(current_user, contract.centro_costo_id)
    return _contrato_form(contract)


@comprador_fase5_bp.route(
    "/contratos/<int:contrato_id>/modificaciones/nueva",
    methods=["GET", "POST"],
)
@permission_required("contratos", "editar")
def contrato_modificacion_nueva(contrato_id):
    contract = db.get_or_404(Contrato, contrato_id)
    verificar_acceso_obra(current_user, contract.centro_costo_id)
    form = ContratoModificacionForm()
    if form.validate_on_submit():
        if form.tipo.data == "precio" and form.monto_nuevo.data is None:
            form.monto_nuevo.errors.append("Captura el nuevo monto total.")
        elif form.tipo.data == "plazo" and form.fecha_fin_nueva.data is None:
            form.fecha_fin_nueva.errors.append("Captura la nueva fecha de terminación.")
        else:
            version = max(
                [item.version for item in contract.modificaciones] or [0]
            ) + 1
            modification = ContratoModificacion(
                contrato_id=contract.id,
                tipo=form.tipo.data,
                descripcion=form.descripcion.data.strip(),
                monto_original=contract.monto_total,
                monto_nuevo=form.monto_nuevo.data,
                fecha=date.today(),
                usuario_id=current_user.id,
                estado="pendiente",
                version=version,
                fecha_fin_nueva=form.fecha_fin_nueva.data,
            )
            db.session.add(modification)
            db.session.flush()
            notificar(
                usuarios_con_permiso(
                    "contratos", "aprobar", centro_costo_id=contract.centro_costo_id
                ),
                "MODIFICACION_CONTRATO_PENDIENTE",
                f"Orden de cambio v{version} del contrato #{contract.id}.",
                url_for(
                    "comprador_fase5.contrato_detalle",
                    contrato_id=contract.id,
                ),
            )
            auditar(
                current_user.id,
                "CREAR_MODIFICACION_CONTRATO",
                "contrato_modificaciones",
                modification.id,
                f"v{version} · {modification.tipo}",
            )
            db.session.commit()
            flash("Modificación enviada a aprobación.", "success")
            return redirect(
                url_for(
                    "comprador_fase5.contrato_detalle",
                    contrato_id=contract.id,
                )
            )
    return render_template(
        "compras/fase5/contratos/modificacion_formulario.html",
        contrato=contract,
        form=form,
    )


@comprador_fase5_bp.post(
    "/contratos/modificaciones/<int:modificacion_id>/resolver"
)
@permission_required("contratos", "aprobar")
def contrato_modificacion_resolver(modificacion_id):
    modification = db.get_or_404(ContratoModificacion, modificacion_id)
    contract = modification.contrato
    verificar_acceso_obra(current_user, contract.centro_costo_id)
    form = ModificacionDecisionForm()
    if not form.validate_on_submit():
        abort(400)
    if modification.estado != "pendiente":
        flash("La modificación ya fue resuelta.", "info")
    else:
        approved = form.decision.data == "aprobar"
        modification.estado = "aprobada" if approved else "rechazada"
        modification.aprobador_id = current_user.id
        modification.fecha_aprobacion = utc_now()
        modification.comentario_aprobacion = (
            form.comentario.data or ""
        ).strip() or None
        if approved:
            if modification.tipo == "precio":
                contract.monto_total = modification.monto_nuevo
            elif modification.tipo == "plazo":
                contract.fecha_fin = modification.fecha_fin_nueva
            contract.version_actual = modification.version
        auditar(
            current_user.id,
            "RESOLVER_MODIFICACION_CONTRATO",
            "contrato_modificaciones",
            modification.id,
            modification.estado,
        )
        db.session.commit()
        flash(f"Modificación {modification.estado}.", "success")
    return redirect(
        url_for("comprador_fase5.contrato_detalle", contrato_id=contract.id)
    )


# ---------------------------------------------------------------------------
# Conciliación de tres vías
# ---------------------------------------------------------------------------


def _orders_for_reconciliation():
    project_ids = [obra.id for obra in obras_accesibles(current_user, incluir_inactivas=True)]
    return (
        PurchaseOrder.query.options(
            joinedload(PurchaseOrder.project), joinedload(PurchaseOrder.supplier)
        )
        .filter(
            PurchaseOrder.project_id.in_(project_ids or [-1]),
            PurchaseOrder.estado.in_(ACTIVE_ORDER_STATES - {"CERRADA"}),
            PurchaseOrder.tipo_oc == "COMPRAS",
        )
        .order_by(PurchaseOrder.fecha_orden.desc())
        .all()
    )


@comprador_fase5_bp.get("/conciliaciones")
@permission_required("conciliacion_facturas", "ver")
def conciliaciones_lista():
    project_ids = [obra.id for obra in obras_accesibles(current_user, incluir_inactivas=True)]
    reconciliations = (
        ConciliacionFactura.query.options(
            joinedload(ConciliacionFactura.orden_compra).joinedload(
                PurchaseOrder.project
            ),
            joinedload(ConciliacionFactura.orden_compra).joinedload(
                PurchaseOrder.supplier
            ),
        )
        .join(PurchaseOrder)
        .filter(PurchaseOrder.project_id.in_(project_ids or [-1]))
        .order_by(ConciliacionFactura.id.desc())
        .all()
    )
    return render_template(
        "compras/fase5/conciliaciones/lista.html",
        conciliaciones=reconciliations,
    )


def _conciliacion_form(conciliation: ConciliacionFactura):
    creating = conciliation.id is None
    form = ConciliacionFacturaForm(obj=conciliation)
    orders = _orders_for_reconciliation()
    form.orden_compra_id.choices = [
        (
            order.id,
            f"{order.folio} · {order.project.codigo} · {order.supplier.nombre}",
        )
        for order in orders
    ]
    requested_order_id = request.args.get("orden_id", type=int)
    if request.method == "GET" and creating and requested_order_id:
        form.orden_compra_id.data = requested_order_id
        order = db.session.get(PurchaseOrder, requested_order_id)
        if order:
            form.factura_numero.data = order.numero_factura
            form.fecha_factura.data = order.fecha_factura
    if form.validate_on_submit():
        order = db.session.get(PurchaseOrder, form.orden_compra_id.data)
        if not order:
            abort(404)
        verificar_acceso_obra(current_user, order.project_id)
        ordered = money(order.subtotal_sin_iva)
        received = money(order.monto_recibido)
        paid = money(order.monto_pagado)
        billed = money(form.monto_factura.data)
        tolerance = Decimal("0.01")
        matches = (
            abs(ordered - received) <= tolerance
            and abs(received - billed) <= tolerance
        )
        reason = (form.motivo_diferencia.data or "").strip() or None
        if not matches and not reason:
            form.motivo_diferencia.errors.append(
                "Explica la diferencia para mantener el pago bloqueado."
            )
        else:
            duplicate = ConciliacionFactura.query.filter_by(
                orden_compra_id=order.id,
                factura_numero=form.factura_numero.data.strip(),
            )
            if conciliation.id:
                duplicate = duplicate.filter(
                    ConciliacionFactura.id != conciliation.id
                )
            if duplicate.first():
                form.factura_numero.errors.append(
                    "Esa factura ya fue conciliada para la OC."
                )
            else:
                conciliation.orden_compra_id = order.id
                conciliation.factura_numero = form.factura_numero.data.strip()
                conciliation.fecha_factura = form.fecha_factura.data
                conciliation.monto_factura = billed
                conciliation.monto_pedido = ordered
                conciliation.monto_recibido = received
                conciliation.monto_pagado = paid
                conciliation.usuario_id = current_user.id
                conciliation.fecha_conciliacion = utc_now()
                conciliation.motivo_diferencia = reason
                conciliation.estado = "aprobada" if matches else "pendiente"
                if matches:
                    conciliation.aprobador_id = current_user.id
                    conciliation.fecha_aprobacion = utc_now()
                order.numero_factura = conciliation.factura_numero
                order.fecha_factura = conciliation.fecha_factura
                db.session.add(conciliation)
                db.session.flush()
                recipients = usuarios_con_permiso(
                    "conciliacion_facturas",
                    "aprobar",
                    centro_costo_id=order.project_id,
                )
                notificar(
                    recipients,
                    (
                        "FACTURA_LIBERADA"
                        if conciliation.estado == "aprobada"
                        else "FACTURA_CON_DIFERENCIAS"
                    ),
                    f"Factura {conciliation.factura_numero} de {order.folio}: "
                    f"{conciliation.estado}.",
                    url_for(
                        "comprador_fase5.conciliacion_detalle",
                        conciliacion_id=conciliation.id,
                    ),
                )
                auditar(
                    current_user.id,
                    "CREAR_CONCILIACION" if creating else "EDITAR_CONCILIACION",
                    "conciliaciones_facturas",
                    conciliation.id,
                    conciliation.estado,
                )
                db.session.commit()
                flash(
                    (
                        "Factura conciliada y liberada para pago."
                        if matches
                        else "Se detectaron diferencias; el pago permanece bloqueado."
                    ),
                    "success" if matches else "warning",
                )
                return redirect(
                    url_for(
                        "comprador_fase5.conciliacion_detalle",
                        conciliacion_id=conciliation.id,
                    )
                )
    return render_template(
        "compras/fase5/conciliaciones/formulario.html",
        form=form,
        conciliacion=conciliation,
        creating=creating,
    )


@comprador_fase5_bp.route("/conciliaciones/nueva", methods=["GET", "POST"])
@permission_required("conciliacion_facturas", "crear")
def conciliacion_nueva():
    return _conciliacion_form(ConciliacionFactura())


@comprador_fase5_bp.get("/conciliaciones/<int:conciliacion_id>")
@permission_required("conciliacion_facturas", "ver")
def conciliacion_detalle(conciliacion_id):
    conciliation = db.get_or_404(ConciliacionFactura, conciliacion_id)
    verificar_acceso_obra(current_user, conciliation.orden_compra.project_id)
    return render_template(
        "compras/fase5/conciliaciones/detalle.html",
        conciliacion=conciliation,
        decision_form=ConciliacionDecisionForm(),
    )


@comprador_fase5_bp.route(
    "/conciliaciones/<int:conciliacion_id>/editar", methods=["GET", "POST"]
)
@permission_required("conciliacion_facturas", "editar")
def conciliacion_editar(conciliacion_id):
    conciliation = db.get_or_404(ConciliacionFactura, conciliacion_id)
    verificar_acceso_obra(current_user, conciliation.orden_compra.project_id)
    if conciliation.estado == "pagada":
        flash("Una conciliación pagada ya no puede modificarse.", "danger")
        return redirect(
            url_for(
                "comprador_fase5.conciliacion_detalle",
                conciliacion_id=conciliation.id,
            )
        )
    return _conciliacion_form(conciliation)


@comprador_fase5_bp.post(
    "/conciliaciones/<int:conciliacion_id>/resolver"
)
@permission_required("conciliacion_facturas", "aprobar")
def conciliacion_resolver(conciliacion_id):
    conciliation = db.get_or_404(ConciliacionFactura, conciliacion_id)
    verificar_acceso_obra(current_user, conciliation.orden_compra.project_id)
    form = ConciliacionDecisionForm()
    if not form.validate_on_submit():
        abort(400)
    if conciliation.estado == "pagada":
        flash("La factura ya fue pagada.", "info")
    elif form.decision.data == "aprobar" and not conciliation.coincide:
        flash(
            "No puede liberarse mientras pedido, recepción y factura no coincidan.",
            "danger",
        )
    else:
        conciliation.estado = (
            "aprobada" if form.decision.data == "aprobar" else "rechazada"
        )
        conciliation.aprobador_id = current_user.id
        conciliation.fecha_aprobacion = utc_now()
        comment = (form.comentario.data or "").strip()
        if comment:
            conciliation.motivo_diferencia = (
                f"{conciliation.motivo_diferencia or ''}\n{comment}".strip()
            )
        auditar(
            current_user.id,
            "RESOLVER_CONCILIACION",
            "conciliaciones_facturas",
            conciliation.id,
            conciliation.estado,
        )
        db.session.commit()
        flash(f"Conciliación {conciliation.estado}.", "success")
    return redirect(
        url_for(
            "comprador_fase5.conciliacion_detalle",
            conciliacion_id=conciliation.id,
        )
    )
