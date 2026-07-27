"""Dashboard ejecutivo de solo lectura para CEO/Dirección."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from flask import Blueprint, render_template
from sqlalchemy import desc, func

from compras_models import ACTIVE_ORDER_STATES, PurchaseOrder, Supplier
from models import CentroCosto, db
from nominas_models import (
    AdditionalPayment,
    Payroll,
    PayrollLine,
    Subcontract,
    SubcontractPayment,
    WeeklyResourceAvailability,
)
from services.fase5 import fecha_operativa, money
from services.weekly_resources import week_start_for, weekly_resource_breakdown
from utils.decorators import permission_required


ceo_bp = Blueprint("ceo", __name__, url_prefix="/direccion")


def _map_totals(rows):
    return {int(project_id): money(total) for project_id, total in rows}


@ceo_bp.get("/")
@permission_required("dashboard_ejecutivo", "ver")
def dashboard():
    today = fecha_operativa()
    resource_summary = weekly_resource_breakdown(week_start_for(today))
    projects = (
        CentroCosto.query.filter_by(tipo="obra")
        .order_by(CentroCosto.estado.desc(), CentroCosto.nombre)
        .all()
    )
    project_ids = [project.id for project in projects]

    additional = _map_totals(
        db.session.query(
            AdditionalPayment.project_id,
            func.coalesce(func.sum(AdditionalPayment.monto_sin_iva), 0),
        )
        .filter(AdditionalPayment.project_id.in_(project_ids or [-1]))
        .group_by(AdditionalPayment.project_id)
        .all()
    )
    subcontract = _map_totals(
        db.session.query(
            Subcontract.project_id,
            func.coalesce(func.sum(SubcontractPayment.monto_sin_iva), 0),
        )
        .join(SubcontractPayment, SubcontractPayment.subcontract_id == Subcontract.id)
        .filter(Subcontract.project_id.in_(project_ids or [-1]))
        .group_by(Subcontract.project_id)
        .all()
    )
    payroll = _map_totals(
        db.session.query(
            Payroll.project_id,
            func.coalesce(
                func.sum(
                    PayrollLine.monto_devengado
                    + PayrollLine.pago_extra
                    + PayrollLine.descuento_imss
                ),
                0,
            ),
        )
        .join(PayrollLine, PayrollLine.payroll_id == Payroll.id)
        .filter(
            Payroll.project_id.in_(project_ids or [-1]),
            Payroll.estado.in_({"aprobada", "pagada", "conciliada"}),
        )
        .group_by(Payroll.project_id)
        .all()
    )

    budget_rows = []
    for project in projects:
        budget = money(project.presupuesto_total)
        actual = money(
            additional.get(project.id, 0)
            + subcontract.get(project.id, 0)
            + payroll.get(project.id, 0)
        )
        variance = money(actual - budget)
        utilization = (
            (actual / budget * Decimal("100")).quantize(Decimal("0.1"))
            if budget > 0
            else Decimal("0")
        )
        semaphore = (
            "rojo"
            if utilization > 100
            else "amarillo"
            if utilization >= 85
            else "verde"
        )
        budget_rows.append(
            {
                "project": project,
                "budget": budget,
                "actual": actual,
                "variance": variance,
                "utilization": utilization,
                "semaphore": semaphore,
            }
        )

    top_deviations = sorted(
        budget_rows,
        key=lambda row: (row["variance"], row["utilization"]),
        reverse=True,
    )[:5]

    payables = [
        order
        for order in PurchaseOrder.query.filter(
            PurchaseOrder.estado.in_(ACTIVE_ORDER_STATES),
            PurchaseOrder.fecha_vencimiento.isnot(None),
        )
        .order_by(PurchaseOrder.fecha_vencimiento, PurchaseOrder.id)
        .all()
        if order.saldo_pendiente > 0
    ]
    cash_available = money(
        db.session.query(
            func.coalesce(func.sum(WeeklyResourceAvailability.monto_disponible), 0)
        )
        .filter(
            WeeklyResourceAvailability.semana_inicio
            == today - timedelta(days=today.weekday())
        )
        .scalar()
    )
    cash_flow = []
    for days in (7, 14, 30):
        outflow = money(
            sum(
                (
                    order.saldo_pendiente
                    for order in payables
                    if order.fecha_vencimiento <= today + timedelta(days=days)
                ),
                Decimal("0"),
            )
        )
        cash_flow.append(
            {
                "days": days,
                "outflow": outflow,
                "projected": money(cash_available - outflow),
            }
        )

    payroll_aggregate = (
        db.session.query(
            Payroll.semana_inicio,
            func.coalesce(func.sum(PayrollLine.neto_pagar), 0),
            func.count(func.distinct(Payroll.project_id)),
        )
        .join(PayrollLine, PayrollLine.payroll_id == Payroll.id)
        .filter(Payroll.estado.in_({"aprobada", "pagada", "conciliada"}))
        .group_by(Payroll.semana_inicio)
        .order_by(Payroll.semana_inicio.desc())
        .limit(8)
        .all()
    )

    supplier_spend = (
        db.session.query(
            Supplier,
            func.coalesce(func.sum(AdditionalPayment.monto_sin_iva), 0).label(
                "total"
            ),
        )
        .join(AdditionalPayment, AdditionalPayment.supplier_id == Supplier.id)
        .group_by(Supplier.id)
        .order_by(desc("total"))
        .limit(10)
        .all()
    )
    supplier_total = money(sum((money(total) for _supplier, total in supplier_spend), Decimal("0")))
    supplier_rows = [
        {
            "supplier": supplier,
            "total": money(total),
            "share": (
                (money(total) / supplier_total * Decimal("100")).quantize(
                    Decimal("0.1")
                )
                if supplier_total
                else Decimal("0")
            ),
        }
        for supplier, total in supplier_spend
    ]

    return render_template(
        "ceo/dashboard.html",
        today=today,
        cash_available=cash_available,
        cash_flow=cash_flow,
        budget_rows=budget_rows,
        top_deviations=top_deviations,
        payables=payables[:10],
        payroll_aggregate=payroll_aggregate,
        supplier_rows=supplier_rows,
        resource_summary=resource_summary,
    )
