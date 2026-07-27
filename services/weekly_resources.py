"""Fuente única del recurso semanal requerido.

La entrega inicial de un préstamo es una salida de caja o banco. Sus
retenciones posteriores únicamente reducen el neto de la nómina y, por diseño,
este módulo no importa ni consulta ``LoanPayment``.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Iterable

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from nominas_models import (
    AdditionalPayment,
    Employee,
    Loan,
    OfficeExpense,
    Payroll,
    PayrollLine,
    Subcontract,
    SubcontractPayment,
    WeeklyResourceAvailability,
    decimal_value,
    money,
)


RESOURCE_COMPONENTS = (
    "nomina",
    "prestamos",
    "gastos_operativos",
    "pagos_adicionales",
    "subcontratos",
)
LOAN_DISBURSED_STATES = ("activo", "liquidado")


def payment_channel(method: str | None) -> str:
    """Normaliza caja contra banco.

    Los préstamos nuevos solo aceptan efectivo o transferencia. ``CHEQUE`` se
    conserva para datos históricos y se agrupa con transferencia.
    """

    return "EFECTIVO" if (method or "").strip().upper() == "EFECTIVO" else "TRANSFERENCIA"


def week_start_for(value: date) -> date:
    """Devuelve el lunes de la semana operativa que contiene ``value``."""

    return value - timedelta(days=value.weekday())


def week_starts_between(start: date, end: date) -> list[date]:
    """Enumera los lunes de todas las semanas tocadas por el intervalo."""

    first = week_start_for(start)
    last = week_start_for(end)
    result: list[date] = []
    current = first
    while current <= last:
        result.append(current)
        current += timedelta(days=7)
    return result


def _empty_method_values() -> dict:
    return {
        "nomina": Decimal("0"),
        "prestamos": Decimal("0"),
        "gastos_operativos": Decimal("0"),
        "pagos_adicionales": Decimal("0"),
        # Alias de compatibilidad para consumidores anteriores.
        "adicionales": Decimal("0"),
        "subcontratos": Decimal("0"),
        "requerido": Decimal("0"),
        "disponible": None,
        "diferencia": None,
    }


def _additional_payment_component(payment: AdditionalPayment) -> str:
    """Clasifica cada pago adicional en exactamente una categoría."""

    order = payment.purchase_order
    if order and (
        (order.categoria_pago or "").upper() == "OPERACIONES"
        or (order.tipo_oc or "").upper() == "OPERACIONES"
    ):
        return "gastos_operativos"
    return "pagos_adicionales"


def weekly_resource_breakdown(
    week_start: date,
    project_ids: Iterable[int] | None = None,
    *,
    draft_refresher: Callable[[Payroll], int] | None = None,
) -> dict:
    """Calcula las salidas de una semana, por método y sin duplicar abonos.

    ``project_ids=None`` representa el consolidado global. Una lista, incluso
    vacía, representa un alcance restringido y nunca expone disponibilidad
    global.
    """

    week_start = week_start_for(week_start)
    week_end = week_start + timedelta(days=4)
    selected_ids = list(project_ids) if project_ids is not None else None
    values = {
        "EFECTIVO": _empty_method_values(),
        "TRANSFERENCIA": _empty_method_values(),
    }

    payroll_query = Payroll.query.filter(Payroll.semana_inicio == week_start)
    if selected_ids is not None:
        payroll_query = payroll_query.filter(
            Payroll.project_id.in_(selected_ids or [-1])
        )
    payrolls = payroll_query.options(
        joinedload(Payroll.lines).joinedload(PayrollLine.empresa_transferencia),
        joinedload(Payroll.lines).joinedload(PayrollLine.empresa_efectivo),
    ).all()
    for payroll in payrolls:
        if payroll.estado == "borrador" and draft_refresher is not None:
            draft_refresher(payroll)
        for line in payroll.lines:
            values["EFECTIVO"]["nomina"] += decimal_value(line.pago_efectivo)
            values["TRANSFERENCIA"]["nomina"] += decimal_value(
                line.pago_transferencia
            )

    # La obra del préstamo se fotografía al entregarlo. COALESCE mantiene
    # compatibles las filas históricas que todavía no tengan esa fotografía.
    loan_project_id = func.coalesce(Loan.project_id, Employee.project_id)
    loan_query = (
        Loan.query.join(Employee, Employee.id == Loan.employee_id)
        .filter(
            Loan.fecha_prestamo.between(week_start, week_end),
            Loan.estado.in_(LOAN_DISBURSED_STATES),
        )
    )
    if selected_ids is not None:
        loan_query = loan_query.filter(
            loan_project_id.in_(selected_ids or [-1])
        )
    for loan in loan_query.all():
        values[payment_channel(loan.metodo_entrega)]["prestamos"] += decimal_value(
            loan.monto
        )

    additional_query = AdditionalPayment.query.options(
        joinedload(AdditionalPayment.purchase_order)
    ).filter(AdditionalPayment.fecha.between(week_start, week_end))
    office_query = OfficeExpense.query.filter(
        OfficeExpense.fecha.between(week_start, week_end)
    )
    subcontract_query = SubcontractPayment.query.join(Subcontract).filter(
        SubcontractPayment.fecha.between(week_start, week_end)
    )
    if selected_ids is not None:
        additional_query = additional_query.filter(
            AdditionalPayment.project_id.in_(selected_ids or [-1])
        )
        office_query = office_query.filter(
            OfficeExpense.project_id.in_(selected_ids or [-1])
        )
        subcontract_query = subcontract_query.filter(
            Subcontract.project_id.in_(selected_ids or [-1])
        )

    for payment in additional_query.all():
        component = _additional_payment_component(payment)
        values[payment_channel(payment.metodo_pago)][component] += decimal_value(
            payment.monto_capturado
        )
    for expense in office_query.all():
        values[payment_channel(expense.metodo_pago)][
            "gastos_operativos"
        ] += decimal_value(expense.monto_capturado)
    for payment in subcontract_query.all():
        values[payment_channel(payment.metodo_pago)]["subcontratos"] += decimal_value(
            payment.monto_capturado
        )

    availability = {
        row.metodo: money(row.monto_disponible)
        for row in WeeklyResourceAvailability.query.filter_by(
            semana_inicio=week_start
        ).all()
    }
    for method in ("EFECTIVO", "TRANSFERENCIA"):
        for component in RESOURCE_COMPONENTS:
            values[method][component] = money(values[method][component])
        values[method]["adicionales"] = money(
            values[method]["gastos_operativos"]
            + values[method]["pagos_adicionales"]
        )
        values[method]["requerido"] = money(
            sum(
                (values[method][component] for component in RESOURCE_COMPONENTS),
                Decimal("0"),
            )
        )
        if method in availability and selected_ids is None:
            values[method]["disponible"] = availability[method]
            values[method]["diferencia"] = money(
                availability[method] - values[method]["requerido"]
            )

    return {
        "week_start": week_start,
        "week_end": week_end,
        "methods": values,
        "requerido_total": money(
            values["EFECTIVO"]["requerido"]
            + values["TRANSFERENCIA"]["requerido"]
        ),
        "disponible_total": (
            money(
                availability.get("EFECTIVO", Decimal("0"))
                + availability.get("TRANSFERENCIA", Decimal("0"))
            )
            if selected_ids is None and len(availability) == 2
            else None
        ),
    }
