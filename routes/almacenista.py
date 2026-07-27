"""Recepción móvil de materiales y discrepancias de almacén."""

from __future__ import annotations

from datetime import timedelta
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
from flask_login import current_user
from sqlalchemy.orm import joinedload, selectinload

from compras_models import (
    ACTIVE_ORDER_STATES,
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
)
from fase5_forms import RecepcionMaterialForm, ResolverDiscrepanciaForm
from fase5_models import DiscrepanciaRecepcion
from models import db, utc_now
from routes.compras import next_folio, refresh_order_status
from services.fase5 import (
    archivo_fase5_absoluto,
    auditar,
    decimal_value,
    guardar_archivo,
    notificar,
)
from services.actualizacion_operativa import (
    centros_operativos_accesibles,
    sincronizar_programacion_recepcion,
)
from utils.access import verificar_acceso_obra
from utils.decorators import permission_required


almacen_bp = Blueprint("almacen", __name__, url_prefix="/almacen")


RECEIVABLE_STATES = ACTIVE_ORDER_STATES - {
    "CERRADA",
    "RECEPCION_TOTAL",
    "PENDIENTE_ANTICIPO",
}


def _pending_orders():
    project_ids = [
        obra.id for obra in centros_operativos_accesibles(current_user)
    ]
    orders = (
        PurchaseOrder.query.options(
            joinedload(PurchaseOrder.project),
            joinedload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.lines).selectinload(
                PurchaseOrderLine.receipt_lines
            ),
        )
        .filter(
            PurchaseOrder.project_id.in_(project_ids or [-1]),
            PurchaseOrder.estado.in_(RECEIVABLE_STATES),
        )
        .order_by(PurchaseOrder.fecha_entrega_estimada, PurchaseOrder.id)
        .all()
    )
    return [
        order
        for order in orders
        if any(line.cantidad_pendiente > 0 for line in order.lines)
    ]


@almacen_bp.get("/")
@permission_required("recepcion_materiales", "ver")
def pendientes():
    project_id = request.args.get("obra", type=int)
    if project_id:
        verificar_acceso_obra(current_user, project_id)
    orders = [
        order
        for order in _pending_orders()
        if not project_id or order.project_id == project_id
    ]
    discrepancies = (
        DiscrepanciaRecepcion.query.options(
            joinedload(DiscrepanciaRecepcion.orden_compra).joinedload(
                PurchaseOrder.project
            )
        )
        .filter(
            DiscrepanciaRecepcion.orden_compra_id.in_(
                [order.id for order in orders] or [-1]
            ),
            DiscrepanciaRecepcion.estado == "abierta",
        )
        .order_by(DiscrepanciaRecepcion.fecha_reporte.desc())
        .all()
    )
    orders_by_project = []
    accessible_centers = centros_operativos_accesibles(current_user)
    for project in accessible_centers:
        project_orders = [order for order in orders if order.project_id == project.id]
        if project_orders:
            orders_by_project.append((project, project_orders))
    return render_template(
        "almacen/pendientes.html",
        ordenes=orders,
        ordenes_por_obra=orders_by_project,
        discrepancias=discrepancies,
        obras=accessible_centers,
        selected_project=project_id,
    )


@almacen_bp.route("/ordenes/<int:order_id>/recibir", methods=["GET", "POST"])
@permission_required("recepcion_materiales", "crear")
def recibir(order_id):
    order = (
        PurchaseOrder.query.options(
            joinedload(PurchaseOrder.project),
            joinedload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.lines).joinedload(
                PurchaseOrderLine.explosion_item
            ),
            selectinload(PurchaseOrder.lines).selectinload(
                PurchaseOrderLine.receipt_lines
            ),
        )
        .filter_by(id=order_id)
        .first_or_404()
    )
    verificar_acceso_obra(current_user, order.project_id)
    if order.estado not in RECEIVABLE_STATES:
        flash("La OC no está habilitada para recepción.", "danger")
        return redirect(url_for("almacen.pendientes"))

    form = RecepcionMaterialForm()
    if request.method == "GET":
        for line in order.lines:
            if line.cantidad_pendiente <= 0:
                continue
            entry = form.lineas.append_entry()
            entry.form.order_line_id.data = str(line.id)
            entry.form.cantidad_recibida.data = Decimal("0")
            entry.form.cantidad_rechazada.data = Decimal("0")
            entry.form.cantidad_faltante.data = Decimal("0")

    if form.validate_on_submit():
        try:
            receipt = GoodsReceipt(
                folio=next_folio(GoodsReceipt, "REC"),
                order_id=order.id,
                fecha=form.fecha.data,
                tipo="PARCIAL",
                documento_proveedor=(
                    form.documento_proveedor.data or form.factura_numero.data or ""
                ).strip()
                or None,
                fecha_factura=form.fecha_factura.data,
                notas=(form.notas.data or "").strip() or None,
                received_by_id=current_user.id,
            )
            db.session.add(receipt)
            activity = False
            discrepancies: list[DiscrepanciaRecepcion] = []
            seen = set()
            for entry in form.lineas.entries:
                raw_id = entry.form.order_line_id.data
                line_id = int(raw_id) if str(raw_id).isdigit() else None
                line = db.session.get(PurchaseOrderLine, line_id)
                if not line or line.order_id != order.id or line.id in seen:
                    raise ValueError("La recepción contiene un renglón inválido.")
                seen.add(line.id)
                received = decimal_value(entry.form.cantidad_recibida.data)
                rejected = decimal_value(entry.form.cantidad_rechazada.data)
                missing = decimal_value(entry.form.cantidad_faltante.data)
                pending = decimal_value(line.cantidad_pendiente)
                if min(received, rejected, missing) < 0:
                    raise ValueError("Las cantidades no pueden ser negativas.")
                if received + rejected > pending:
                    raise ValueError(
                        "La suma recibida y rechazada supera la cantidad pendiente."
                    )
                if missing > pending - received - rejected:
                    raise ValueError(
                        "La suma recibida, rechazada y faltante supera la "
                        "cantidad pendiente del renglón."
                    )
                discrepancy_total = rejected + missing
                reason = (entry.form.motivo_discrepancia.data or "").strip()
                if discrepancy_total > 0 and not reason:
                    raise ValueError(
                        "Describe el motivo del material rechazado o faltante."
                    )
                evidence = None
                if discrepancy_total > 0:
                    evidence = guardar_archivo(
                        entry.form.evidencia_discrepancia.data,
                        "discrepancias_recepcion",
                    )
                    if not evidence:
                        raise ValueError(
                            "Adjunta evidencia de cada renglón con discrepancia."
                        )
                if received > 0:
                    receipt.lines.append(
                        GoodsReceiptLine(
                            order_line=line, cantidad_recibida=received
                        )
                    )
                    activity = True
                for kind, quantity in (
                    ("rechazado", rejected),
                    ("faltante", missing),
                ):
                    if quantity <= 0:
                        continue
                    discrepancy = DiscrepanciaRecepcion(
                        orden_compra_id=order.id,
                        orden_linea_id=line.id,
                        tipo=kind,
                        cantidad=quantity,
                        descripcion=reason,
                        evidencia=evidence,
                        estado="abierta",
                        usuario_reporta_id=current_user.id,
                    )
                    discrepancies.append(discrepancy)
                    db.session.add(discrepancy)
                    activity = True
            if not activity:
                raise ValueError(
                    "Captura al menos una cantidad recibida, rechazada o faltante."
                )

            if form.factura_numero.data:
                order.numero_factura = form.factura_numero.data.strip()
                order.fecha_factura = form.fecha_factura.data
                if order.fecha_factura:
                    order.fecha_vencimiento = order.fecha_factura + timedelta(
                        days=(
                            order.supplier.dias_credito
                            if order.supplier and order.supplier.tiene_credito
                            else 0
                        )
                    )
            db.session.flush()
            for discrepancy in discrepancies:
                discrepancy.recepcion_id = receipt.id
            receipt.tipo = (
                "TOTAL"
                if all(line.cantidad_pendiente <= 0 for line in order.lines)
                else "PARCIAL"
            )
            refresh_order_status(order)
            sincronizar_programacion_recepcion(order)
            notificar(
                [order.buyer],
                "MATERIAL_RECIBIDO",
                f"Almacén registró recepción {receipt.tipo.lower()} de "
                f"{order.folio}; discrepancias: {len(discrepancies)}.",
                url_for("compras.order_detail", order_id=order.id),
            )
            auditar(
                current_user.id,
                "RECIBIR_MATERIAL",
                "goods_receipts",
                receipt.id,
                f"{order.folio} · {len(discrepancies)} discrepancia(s)",
            )
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash(
                "Recepción registrada y comprador notificado."
                + (
                    " Las discrepancias permanecen abiertas."
                    if discrepancies
                    else ""
                ),
                "success",
            )
            return redirect(url_for("almacen.pendientes"))
    return render_template(
        "almacen/recibir.html",
        form=form,
        orden=order,
        lineas_por_id={line.id: line for line in order.lines},
    )


@almacen_bp.get("/discrepancias")
@permission_required("discrepancias_recepcion", "ver")
def discrepancias_lista():
    project_ids = [
        obra.id
        for obra in centros_operativos_accesibles(
            current_user, incluir_obras_inactivas=True
        )
    ]
    discrepancies = (
        DiscrepanciaRecepcion.query.options(
            joinedload(DiscrepanciaRecepcion.orden_compra).joinedload(
                PurchaseOrder.project
            ),
            joinedload(DiscrepanciaRecepcion.orden_linea).joinedload(
                PurchaseOrderLine.explosion_item
            ),
        )
        .join(PurchaseOrder)
        .filter(PurchaseOrder.project_id.in_(project_ids or [-1]))
        .order_by(
            DiscrepanciaRecepcion.estado,
            DiscrepanciaRecepcion.fecha_reporte.desc(),
        )
        .all()
    )
    return render_template(
        "almacen/discrepancias.html",
        discrepancias=discrepancies,
        resolve_form=ResolverDiscrepanciaForm(),
    )


@almacen_bp.get("/discrepancias/<int:discrepancia_id>/evidencia")
@permission_required("discrepancias_recepcion", "ver")
def discrepancia_evidencia(discrepancia_id):
    discrepancy = db.get_or_404(DiscrepanciaRecepcion, discrepancia_id)
    verificar_acceso_obra(current_user, discrepancy.orden_compra.project_id)
    if not discrepancy.evidencia:
        abort(404)
    try:
        path = archivo_fase5_absoluto(discrepancy.evidencia)
    except FileNotFoundError:
        abort(404)
    return send_file(path, as_attachment=False)


@almacen_bp.post("/discrepancias/<int:discrepancia_id>/resolver")
@permission_required("discrepancias_recepcion", "editar")
def discrepancia_resolver(discrepancia_id):
    discrepancy = db.get_or_404(DiscrepanciaRecepcion, discrepancia_id)
    verificar_acceso_obra(current_user, discrepancy.orden_compra.project_id)
    form = ResolverDiscrepanciaForm()
    if not form.validate_on_submit():
        flash("Describe cómo se resolvió la discrepancia.", "danger")
    elif discrepancy.estado == "resuelta":
        flash("La discrepancia ya estaba resuelta.", "info")
    else:
        discrepancy.estado = "resuelta"
        discrepancy.resolucion = form.resolucion.data.strip()
        discrepancy.usuario_resuelve_id = current_user.id
        discrepancy.fecha_resolucion = utc_now()
        auditar(
            current_user.id,
            "RESOLVER_DISCREPANCIA",
            "discrepancias_recepcion",
            discrepancy.id,
            discrepancy.resolucion,
        )
        db.session.commit()
        flash("Discrepancia marcada como resuelta.", "success")
    return redirect(url_for("almacen.discrepancias_lista"))
