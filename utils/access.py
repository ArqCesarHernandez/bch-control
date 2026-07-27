"""Políticas compartidas de alcance por obra.

Las rutas no deben confiar en que una obra fue ocultada en el menú o filtrada
en una lista. Toda operación sobre un documento vuelve a comprobar aquí que el
usuario tenga alcance sobre su centro de costo.
"""

from __future__ import annotations

from flask import abort


def verificar_asignacion_obra(usuario, centro_costo_id: int) -> bool:
    """Valida la asignación persistente sin considerar la obra activa."""

    try:
        centro_id = int(centro_costo_id)
    except (TypeError, ValueError):
        abort(404)

    if (
        not getattr(usuario, "is_authenticated", False)
        or not getattr(usuario, "is_active", False)
    ):
        abort(404)

    if getattr(usuario, "acceso_global_obras", False):
        return True
    if getattr(usuario, "centro_costo_id", None) == centro_id:
        return True
    if any(
        getattr(obra, "id", None) == centro_id
        for obra in getattr(usuario, "projects", ())
    ):
        return True
    abort(404)


def verificar_acceso_obra(
    usuario,
    centro_costo_id: int,
    *,
    respetar_obra_activa: bool = True,
) -> bool:
    """Confirma que ``usuario`` puede operar el centro indicado.

    Los perfiles con alcance global conservan acceso a todas las obras. Para
    los demás perfiles se acepta tanto el centro principal legado como la
    relación de obras asignadas. Ante cualquier diferencia se responde 404
    para no confirmar que el documento o la obra existen.
    """

    verificar_asignacion_obra(usuario, centro_costo_id)
    if respetar_obra_activa and getattr(usuario, "rol", None) == "supervisor":
        from utils.project_scope import obra_activa_id

        if obra_activa_id(usuario, incluir_inactivas=False) != int(
            centro_costo_id
        ):
            abort(404)
    return True
