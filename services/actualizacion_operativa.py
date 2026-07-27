"""Reglas compartidas de la actualización operativa posterior a Fase 5."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_

from compras_models import (
    BudgetExplosionItem,
    ExplosionRevision,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderPaymentSchedule,
    PurchaseOrderRevision,
    PurchaseRequisition,
)
from models import CentroCosto, Usuario, db, usuario_centros_nomina, utc_now
from nominas_models import decimal_value, money
from utils.project_scope import obra_activa_id


def centros_operativos_accesibles(
    usuario,
    *,
    incluir_obras_inactivas: bool = False,
) -> list[CentroCosto]:
    """Obras normales y centros de garantía dentro del alcance del usuario."""

    query = CentroCosto.query.filter(
        CentroCosto.tipo.in_(("obra", "garantia"))
    )
    if not incluir_obras_inactivas:
        query = query.filter(CentroCosto.estado == "activa")
    if not usuario.acceso_global_obras:
        query = query.join(usuario_centros_nomina).filter(
            usuario_centros_nomina.c.user_id == usuario.id
        )
    if usuario.rol == "supervisor":
        selected_id = obra_activa_id(
            usuario,
            incluir_inactivas=incluir_obras_inactivas,
        )
        query = query.filter(
            or_(
                CentroCosto.id == (selected_id or -1),
                CentroCosto.tipo == "garantia",
            )
        )
    return query.order_by(CentroCosto.nombre).all()


def asignar_obra_a_compradores(obra: CentroCosto) -> None:
    """Añade una obra nueva a todos los compradores activos e inactivos."""

    if obra.tipo != "obra":
        return
    for comprador in Usuario.query.filter_by(rol="comprador").all():
        if all(project.id != obra.id for project in comprador.projects):
            comprador.projects.append(obra)


def asignar_todas_las_obras_comprador(usuario: Usuario) -> None:
    """Sincroniza la relación explícita del Comprador con todas las obras."""

    if usuario.rol != "comprador":
        return
    usuario.projects = (
        CentroCosto.query.filter(CentroCosto.tipo == "obra")
        .order_by(CentroCosto.id)
        .all()
    )


def ajustar_reserva_pendiente(
    explosion_item_id: int,
    delta: Decimal,
) -> BudgetExplosionItem:
    """Ajusta atómicamente la reserva de borrador y valida el saldo final.

    La suma se ejecuta dentro de la base de datos. En SQLite, dos escrituras
    concurrentes se serializan; la segunda vuelve a validar el saldo ya
    actualizado y se revierte si excede el presupuesto.
    """

    delta = decimal_value(delta)
    updated = (
        BudgetExplosionItem.query.filter_by(id=explosion_item_id)
        .update(
            {
                BudgetExplosionItem.cantidad_reservada_borrador:
                BudgetExplosionItem.cantidad_reservada_borrador + delta,
                BudgetExplosionItem.updated_at: utc_now(),
            },
            synchronize_session=False,
        )
    )
    if not updated:
        raise ValueError("El material seleccionado ya no está disponible.")
    db.session.flush()
    db.session.expire_all()
    entry = db.session.get(BudgetExplosionItem, explosion_item_id)
    reserved = decimal_value(entry.cantidad_reservada_borrador)
    if reserved < 0:
        raise ValueError("La reserva del material no puede ser negativa.")
    if entry.saldo_disponible_crudo < 0:
        maximum = max(Decimal("0"), delta + entry.saldo_disponible_crudo)
        raise ValueError(
            "La cantidad solicitada excede la disponible. "
            f"Cantidad máxima permitida: {maximum:.4f} "
            f"{entry.supply_item.unidad}."
        )
    return entry


def liberar_reservas_pendientes(requisition: PurchaseRequisition) -> None:
    """Libera las líneas todavía pendientes antes de cancelar o eliminar."""

    for line in requisition.lines:
        if line.estado_linea == "PENDIENTE":
            ajustar_reserva_pendiente(
                line.explosion_item_id,
                -decimal_value(line.cantidad_solicitada),
            )


def revision_explosion_vigente(project_id: int) -> ExplosionRevision | None:
    return (
        ExplosionRevision.query.filter_by(
            project_id=project_id,
            es_vigente=True,
            estado="VIGENTE",
        )
        .order_by(
            ExplosionRevision.numero_revision.desc(),
            ExplosionRevision.id.desc(),
        )
        .first()
    )


def items_explosion_vigente(project_id: int) -> list[BudgetExplosionItem]:
    """Renglones vigentes, con respaldo para instalaciones aún no migradas."""

    revision = revision_explosion_vigente(project_id)
    query = BudgetExplosionItem.query.filter_by(project_id=project_id, activo=True)
    if revision:
        query = query.filter(BudgetExplosionItem.revision_id == revision.id)
    else:
        query = query.filter(BudgetExplosionItem.revision_id.is_(None))
    return query.order_by(
        BudgetExplosionItem.budget_item_id,
        BudgetExplosionItem.id,
    ).all()


def siguiente_revision_explosion(project_id: int) -> int:
    current = (
        db.session.query(func.coalesce(func.max(ExplosionRevision.numero_revision), 0))
        .filter(ExplosionRevision.project_id == project_id)
        .scalar()
    )
    return int(current or 0) + 1


def activar_revision_explosion(revision: ExplosionRevision) -> None:
    """Vuelve vigente una revisión sin borrar ni reescribir sus antecesoras."""

    now = utc_now()
    previous = ExplosionRevision.query.filter(
        ExplosionRevision.project_id == revision.project_id,
        ExplosionRevision.id != revision.id,
        ExplosionRevision.es_vigente.is_(True),
    ).all()
    for item in previous:
        item.es_vigente = False
        item.estado = "HISTORICA"
        item.vigente_hasta = now
        for line in item.items:
            line.activo = False
    revision.es_vigente = True
    revision.estado = "VIGENTE"
    revision.vigente_desde = now
    revision.vigente_hasta = None
    for line in revision.items:
        line.activo = True


def clasificar_y_liberar_requisicion(
    requisition: PurchaseRequisition,
    *,
    usuario_id: int,
) -> None:
    """Libera por renglón y materializa una RFQ con los conceptos disponibles."""

    now = utc_now()
    for line in requisition.lines:
        requires = bool(line.explosion_item.requiere_autorizacion_previa)
        line.requiere_autorizacion_previa = requires
        if requires:
            line.estado_linea = "PENDIENTE"
            line.cantidad_aprobada = Decimal("0")
            line.liberada_at = None
        else:
            if line.estado_linea == "PENDIENTE":
                ajustar_reserva_pendiente(
                    line.explosion_item_id,
                    -decimal_value(line.cantidad_solicitada),
                )
            line.estado_linea = "APROBADA"
            line.cantidad_aprobada = line.cantidad_solicitada
            line.liberada_at = now
    sincronizar_estado_requisicion(requisition)
    crear_o_actualizar_rfq_liberada(requisition, usuario_id=usuario_id)


def sincronizar_estado_requisicion(requisition: PurchaseRequisition) -> None:
    states = {line.estado_linea for line in requisition.lines}
    if "PENDIENTE" in states:
        requisition.estado = (
            "PARCIAL" if "APROBADA" in states else "PENDIENTE_AUTORIZACION"
        )
    elif "APROBADA" in states:
        requisition.estado = "APROBADA"
    else:
        requisition.estado = "RECHAZADA"


def crear_o_actualizar_rfq_liberada(
    requisition: PurchaseRequisition,
    *,
    usuario_id: int,
):
    """Crea una sola RFQ y añade únicamente renglones ya liberados."""

    from fase5_models import Licitacion, LicitacionLinea

    released = [
        line
        for line in requisition.lines
        if line.estado_linea == "APROBADA"
        and decimal_value(line.cantidad_aprobada) > 0
    ]
    if not released:
        return None
    rfq = (
        Licitacion.query.filter_by(requisicion_id=requisition.id)
        .order_by(Licitacion.id)
        .first()
    )
    if not rfq:
        rfq = Licitacion(
            requisicion_id=requisition.id,
            estado="preparacion",
            fecha_limite=max(date.today(), requisition.fecha_requerida),
            creado_por_id=usuario_id,
        )
        db.session.add(rfq)
        db.session.flush()
    linked = {item.requisicion_linea_id for item in rfq.lineas}
    for line in released:
        if line.id not in linked:
            rfq.lineas.append(
                LicitacionLinea(requisicion_linea_id=line.id)
            )
    return rfq


def crear_programacion_pago(
    order: PurchaseOrder,
    *,
    solicitado_por_id: int,
) -> None:
    """Genera obligaciones programadas sin crear movimientos de pago."""

    if order.payment_schedules:
        if order.estado != "BORRADOR":
            raise ValueError("La programación de una OC emitida no se reemplaza.")
        order.payment_schedules.clear()
        db.session.flush()

    total = order.subtotal_sin_iva
    if total <= 0:
        raise ValueError("La OC debe contener un importe mayor que cero.")

    if order.modalidad_pago == "ANTICIPO":
        advance = money(order.anticipo_monto)
        if advance <= 0 or advance > total:
            raise ValueError("El anticipo debe ser mayor que cero y no exceder la OC.")
        percentage = (
            decimal_value(order.anticipo_porcentaje)
            or (advance * Decimal("100") / total)
        )
        order.payment_schedules.append(
            PurchaseOrderPaymentSchedule(
                secuencia=1,
                tipo="ANTICIPO",
                condicion="SOLICITADO",
                monto_programado=advance,
                porcentaje=percentage,
                estado="SOLICITADO",
                solicitado_por_id=solicitado_por_id,
                justificacion=order.justificacion_anticipo,
            )
        )
        balance = money(total - advance)
        if balance > 0:
            order.payment_schedules.append(
                PurchaseOrderPaymentSchedule(
                    secuencia=2,
                    tipo="SALDO",
                    condicion=order.condicion_saldo,
                    monto_programado=balance,
                    porcentaje=Decimal("100") - percentage,
                    estado="PENDIENTE_RECEPCION",
                    solicitado_por_id=solicitado_por_id,
                )
            )
    else:
        order.modalidad_pago = "PAGO_CONTRA_ENTREGA"
        order.anticipo_monto = Decimal("0")
        order.anticipo_porcentaje = Decimal("0")
        order.anticipo_pendiente = Decimal("0")
        order.justificacion_anticipo = None
        order.payment_schedules.append(
            PurchaseOrderPaymentSchedule(
                secuencia=1,
                tipo="SALDO",
                condicion=order.condicion_saldo,
                monto_programado=total,
                porcentaje=Decimal("100"),
                estado="PENDIENTE_RECEPCION",
                solicitado_por_id=solicitado_por_id,
            )
        )


def sincronizar_programacion_recepcion(order: PurchaseOrder) -> None:
    """Actualiza la bandeja financiera sin registrar un pago."""

    for schedule in order.payment_schedules:
        if schedule.tipo != "SALDO" or schedule.estado in {"PAGADO", "CANCELADO"}:
            continue
        if schedule.monto_liberado > 0:
            schedule.estado = (
                "PARCIAL"
                if schedule.monto_liberado < schedule.pendiente
                else "AUTORIZADO"
            )
        else:
            schedule.estado = "PENDIENTE_RECEPCION"


def snapshot_orden(order: PurchaseOrder) -> dict:
    """Representación JSON estable para una revisión auditable."""

    return {
        "version": order.version_actual,
        "folio": order.folio,
        "project_id": order.project_id,
        "supplier_id": order.supplier_id,
        "beneficiario_libre": order.beneficiario_libre,
        "fecha_entrega_estimada": order.fecha_entrega_estimada.isoformat(),
        "notas": order.notas,
        "modalidad_pago": order.modalidad_pago,
        "anticipo_monto": str(order.anticipo_monto or 0),
        "condicion_saldo": order.condicion_saldo,
        "lineas": [
            {
                "id": line.id,
                "explosion_item_id": line.explosion_item_id,
                "cantidad": str(line.cantidad),
                "precio_unitario_sin_iva": str(line.precio_unitario_sin_iva),
                "importe_sin_iva": str(line.importe_sin_iva),
                "observacion_operativa": line.observacion_operativa,
            }
            for line in order.lines
        ],
    }


def registrar_revision_orden(
    order: PurchaseOrder,
    *,
    valores_anteriores: dict,
    motivo: str,
    usuario_id: int,
) -> PurchaseOrderRevision:
    order.version_actual = int(order.version_actual or 1) + 1
    revision = PurchaseOrderRevision(
        order=order,
        version=order.version_actual,
        motivo=motivo.strip(),
        valores_anteriores=valores_anteriores,
        valores_nuevos=snapshot_orden(order),
        usuario_id=usuario_id,
    )
    db.session.add(revision)
    return revision
