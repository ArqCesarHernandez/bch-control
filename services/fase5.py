"""Servicios transaccionales y de soporte para la Fase 5."""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from flask import current_app, url_for
from sqlalchemy import func
from sqlalchemy.exc import OperationalError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from compras_models import PurchaseNotification, PurchaseOrder
from fase5_models import (
    AvancePartida,
    CertificacionSubcontrato,
    ConciliacionFactura,
    Fase5AlertRun,
    Licitacion,
    NoConformidad,
)
from models import (
    BitacoraAuditoria,
    CentroCosto,
    Usuario,
    db,
    usuario_centros_nomina,
    utc_now,
)
from nominas_models import BudgetItem, Subcontract
from utils.project_scope import obra_activa_id


MONEY_STEP = Decimal("0.01")


def decimal_value(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def money(value) -> Decimal:
    return decimal_value(value).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def obras_accesibles(
    usuario,
    *,
    incluir_inactivas: bool = False,
    respetar_obra_activa: bool = True,
):
    """Devuelve las obras visibles según el alcance explícito del usuario."""

    query = CentroCosto.query.filter(CentroCosto.tipo == "obra")
    if not incluir_inactivas:
        query = query.filter(CentroCosto.estado == "activa")
    if not usuario.acceso_global_obras:
        query = query.join(usuario_centros_nomina).filter(
            usuario_centros_nomina.c.user_id == usuario.id
        )
    if usuario.rol == "supervisor" and respetar_obra_activa:
        selected_id = obra_activa_id(
            usuario,
            incluir_inactivas=incluir_inactivas,
        )
        query = query.filter(CentroCosto.id == (selected_id or -1))
    return query.order_by(CentroCosto.nombre).all()


def usuario_tiene_obra(usuario, centro_costo_id: int) -> bool:
    if usuario.acceso_global_obras:
        return True
    if usuario.centro_costo_id == centro_costo_id:
        return True
    return any(project.id == centro_costo_id for project in usuario.projects)


def usuarios_con_permiso(
    modulo: str,
    accion: str = "ver",
    *,
    centro_costo_id: int | None = None,
) -> list[Usuario]:
    """Resuelve destinatarios activos sin ampliar su alcance por obra."""

    usuarios = Usuario.query.filter_by(activo=True).all()
    return [
        usuario
        for usuario in usuarios
        if usuario.tiene_permiso(modulo, accion)
        and (
            centro_costo_id is None
            or usuario_tiene_obra(usuario, centro_costo_id)
        )
    ]


def notificar(
    usuarios,
    tipo: str,
    mensaje: str,
    enlace: str | None = None,
) -> None:
    """Usa el centro de notificaciones ya existente, sin duplicar destinatarios."""

    ids = {
        usuario.id
        for usuario in usuarios
        if usuario is not None and getattr(usuario, "activo", False)
    }
    for usuario_id in ids:
        db.session.add(
            PurchaseNotification(
                user_id=usuario_id,
                tipo=tipo[:50],
                mensaje=mensaje[:500],
                enlace=enlace[:300] if enlace else None,
            )
        )


def auditar(
    usuario_id: int,
    accion: str,
    tabla: str,
    registro_id: int | None = None,
    detalle: str | None = None,
) -> None:
    db.session.add(
        BitacoraAuditoria(
            usuario_id=usuario_id,
            accion=accion[:100],
            tabla_afectada=tabla[:50],
            registro_id=registro_id,
            detalle=detalle,
        )
    )


def carpeta_archivos_fase5() -> Path:
    configured = current_app.config.get("FASE5_UPLOAD_FOLDER")
    base = Path(configured) if configured else Path(current_app.instance_path) / "fase5_uploads"
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def guardar_archivo(
    archivo: FileStorage | None,
    categoria: str,
) -> str | None:
    """Guarda un adjunto con nombre no predecible y devuelve su ruta relativa."""

    if not archivo or not archivo.filename:
        return None
    original = secure_filename(archivo.filename)
    extension = Path(original).suffix.lower()
    if not extension:
        raise ValueError("El archivo adjunto debe tener una extensión válida.")
    relative = Path(secure_filename(categoria)) / (
        f"{uuid.uuid4().hex}{extension}"
    )
    target = carpeta_archivos_fase5() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    archivo.save(target)
    return relative.as_posix()


def archivo_fase5_absoluto(ruta_relativa: str) -> Path:
    """Resuelve un adjunto sin permitir escapar de la carpeta privada."""

    base = carpeta_archivos_fase5()
    candidate = (base / (ruta_relativa or "")).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise FileNotFoundError("Ruta de archivo inválida.") from exc
    if not candidate.is_file():
        raise FileNotFoundError("El archivo solicitado no existe.")
    return candidate


def actualizar_avance_partida(partida_id: int) -> Decimal:
    """Recalcula el porcentaje real y sincroniza subcontratos de esa partida."""

    partida = db.session.get(BudgetItem, partida_id)
    if not partida:
        return Decimal("0")
    ejecutado = decimal_value(
        db.session.query(func.coalesce(func.sum(AvancePartida.cantidad_ejecutada), 0))
        .filter(AvancePartida.partida_id == partida.id)
        .scalar()
    )
    objetivo = decimal_value(partida.cantidad_objetivo)
    porcentaje = (
        min(Decimal("100"), ejecutado * Decimal("100") / objetivo)
        if objetivo > 0
        else Decimal("0")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    partida.porcentaje_avance_real = porcentaje
    for subcontrato in Subcontract.query.filter_by(
        budget_item_id=partida.id, activo=True
    ).all():
        subcontrato.avance_fisico = porcentaje / Decimal("100")
    return porcentaje


def conciliacion_aprobada_para_pago(order: PurchaseOrder) -> bool:
    """Confirma que la última factura de una OC superó la conciliación."""

    if not order.requiere_conciliacion:
        return True
    conciliacion = (
        ConciliacionFactura.query.filter_by(orden_compra_id=order.id)
        .order_by(ConciliacionFactura.id.desc())
        .first()
    )
    return bool(
        conciliacion
        and conciliacion.estado in {"aprobada", "pagada"}
        and conciliacion.coincide
    )


def actualizar_conciliacion_pagada(order: PurchaseOrder) -> None:
    conciliacion = (
        ConciliacionFactura.query.filter_by(orden_compra_id=order.id)
        .order_by(ConciliacionFactura.id.desc())
        .first()
    )
    if not conciliacion:
        return
    conciliacion.monto_pagado = money(order.monto_pagado)
    if order.saldo_pendiente <= 0 and conciliacion.estado == "aprobada":
        conciliacion.estado = "pagada"


def fecha_operativa() -> date:
    configured = current_app.config.get("FASE5_TODAY")
    if isinstance(configured, date):
        return configured
    if configured:
        return datetime.strptime(str(configured), "%Y-%m-%d").date()
    return date.today()


def run_daily_phase5_alerts(*, force: bool = False) -> dict[str, int]:
    """Genera avisos diarios idempotentes para los pendientes de la Fase 5."""

    current = fecha_operativa()
    zero = {"ncr": 0, "certificaciones": 0, "licitaciones": 0}
    try:
        previous = Fase5AlertRun.query.filter_by(fecha=current).first()
    except OperationalError:
        # Permite que una instancia antigua arranque para ejecutar la migración.
        db.session.rollback()
        return zero
    if previous and not force:
        return {
            "ncr": previous.ncr_por_vencer,
            "certificaciones": previous.certificaciones_pendientes,
            "licitaciones": previous.licitaciones_sin_adjudicar,
        }

    counts = dict(zero)
    ncrs = NoConformidad.query.filter(
        NoConformidad.estado.in_({"abierta", "en_proceso"}),
        NoConformidad.fecha_limite <= current + timedelta(days=3),
    ).all()
    for ncr in ncrs:
        notificar(
            usuarios_con_permiso(
                "no_conformidades", "ver", centro_costo_id=ncr.centro_costo_id
            ),
            "NCR_POR_VENCER",
            f"NCR #{ncr.id} de {ncr.centro_costo.nombre} vence el "
            f"{ncr.fecha_limite:%d/%m/%Y}.",
            f"/campo/no-conformidades/{ncr.id}",
        )
        counts["ncr"] += 1

    pendientes = CertificacionSubcontrato.query.filter_by(estado="pendiente").all()
    for certificacion in pendientes:
        project_id = certificacion.subcontrato.project_id
        notificar(
            usuarios_con_permiso(
                "certificaciones", "aprobar", centro_costo_id=project_id
            ),
            "CERTIFICACION_PENDIENTE",
            f"Certificación #{certificacion.id} pendiente por "
            f"{money(certificacion.monto_solicitado)} MXN.",
            f"/campo/certificaciones/{certificacion.id}",
        )
        counts["certificaciones"] += 1

    licitaciones = Licitacion.query.filter_by(estado="cerrada").all()
    for licitacion in licitaciones:
        if licitacion.oferta_ganadora:
            continue
        project_id = licitacion.requisicion.project_id
        notificar(
            usuarios_con_permiso(
                "licitaciones", "editar", centro_costo_id=project_id
            ),
            "LICITACION_SIN_ADJUDICAR",
            f"Licitación #{licitacion.id} cerrada sin adjudicación.",
            f"/compras/licitaciones/{licitacion.id}",
        )
        counts["licitaciones"] += 1

    run = previous or Fase5AlertRun(fecha=current)
    run.ncr_por_vencer = counts["ncr"]
    run.certificaciones_pendientes = counts["certificaciones"]
    run.licitaciones_sin_adjudicar = counts["licitaciones"]
    run.executed_at = utc_now()
    db.session.add(run)
    db.session.commit()
    return counts
