"""Selección y alcance de la obra activa del Supervisor.

La relación ``user_projects`` continúa siendo la autoridad de las obras
asignadas. La sesión solo conserva cuál de ellas está activa para evitar
mezclar información operativa de dos obras en una misma pantalla.
"""

from __future__ import annotations

from flask import has_request_context, session

from models import CentroCosto, Usuario, usuario_centros_nomina


ACTIVE_PROJECT_SESSION_KEY = "active_project_id"


def obras_asignadas_supervisor(
    usuario: Usuario,
    *,
    incluir_inactivas: bool = True,
) -> list[CentroCosto]:
    """Devuelve todas las obras asignadas, sin aplicar la selección de sesión."""

    if not usuario or usuario.rol != "supervisor":
        return []
    query = (
        CentroCosto.query.join(usuario_centros_nomina)
        .filter(
            usuario_centros_nomina.c.user_id == usuario.id,
            CentroCosto.tipo == "obra",
        )
    )
    if not incluir_inactivas:
        query = query.filter(CentroCosto.estado == "activa")
    return query.order_by(CentroCosto.nombre, CentroCosto.id).all()


def obra_activa_supervisor(
    usuario: Usuario,
    *,
    incluir_inactivas: bool = True,
) -> CentroCosto | None:
    """Resuelve una obra válida y corrige una selección de sesión obsoleta."""

    if not has_request_context() or not usuario or usuario.rol != "supervisor":
        return None
    obras = obras_asignadas_supervisor(
        usuario,
        incluir_inactivas=incluir_inactivas,
    )
    if not obras:
        session.pop(ACTIVE_PROJECT_SESSION_KEY, None)
        return None

    ids = {obra.id for obra in obras}
    try:
        selected_id = int(session.get(ACTIVE_PROJECT_SESSION_KEY))
    except (TypeError, ValueError):
        selected_id = None

    if selected_id not in ids:
        preferred_id = (
            usuario.centro_costo_id
            if usuario.centro_costo_id in ids
            else obras[0].id
        )
        session[ACTIVE_PROJECT_SESSION_KEY] = preferred_id
        session.modified = True
        selected_id = preferred_id
    return next(obra for obra in obras if obra.id == selected_id)


def obra_activa_id(
    usuario: Usuario,
    *,
    incluir_inactivas: bool = True,
) -> int | None:
    obra = obra_activa_supervisor(
        usuario,
        incluir_inactivas=incluir_inactivas,
    )
    return obra.id if obra else None


def seleccionar_obra_activa(
    usuario: Usuario,
    project_id: int,
    *,
    incluir_inactivas: bool = False,
) -> CentroCosto | None:
    """Guarda una obra asignada como activa; nunca amplía el alcance."""

    if not has_request_context() or not usuario or usuario.rol != "supervisor":
        return None
    try:
        project_id = int(project_id)
    except (TypeError, ValueError):
        return None
    obra = next(
        (
            item
            for item in obras_asignadas_supervisor(
                usuario,
                incluir_inactivas=incluir_inactivas,
            )
            if item.id == project_id
        ),
        None,
    )
    if obra is None:
        return None
    session[ACTIVE_PROJECT_SESSION_KEY] = obra.id
    session.modified = True
    return obra
