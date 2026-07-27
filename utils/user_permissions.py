"""Reglas de seguridad para administrar roles y permisos de usuarios."""

from __future__ import annotations

from collections.abc import Mapping

from flask import abort

from models import (
    ACCIONES_PERMISO,
    MODULOS_PERMISOS,
    permisos_predeterminados_rol,
)


ROLES_VALIDOS = {
    "admin",
    "admin_financiero",
    "capturista",
    "supervisor",
    "comprador",
    "almacenista",
    "ceo",
    "costos",
}


def normalizar_rol(valor: str) -> str:
    """Convierte el alias histórico y rechaza roles fuera del catálogo."""

    rol = "admin" if valor == "administrador" else valor
    if rol not in ROLES_VALIDOS:
        abort(403)
    return rol


def matriz_permisos_efectivos(usuario) -> dict[str, dict[str, bool]]:
    """Materializa la matriz efectiva completa de un usuario."""

    return {
        modulo: {
            accion: usuario.tiene_permiso(modulo, accion)
            for accion in ACCIONES_PERMISO
        }
        for modulo in MODULOS_PERMISOS
    }


def matriz_permisos_formulario(formulario: Mapping[str, str]) -> dict[str, dict[str, bool]]:
    """Lee únicamente las claves de permisos reconocidas por el servidor."""

    return {
        modulo: {
            accion: formulario.get(f"perm_{modulo}_{accion}") == "on"
            for accion in ACCIONES_PERMISO
        }
        for modulo in MODULOS_PERMISOS
    }


def verificar_rol_otorgable(
    actor,
    nuevo_rol: str,
    *,
    rol_actual: str | None = None,
) -> str:
    """Impide conceder mediante un rol capacidades superiores a las propias."""

    rol = normalizar_rol(nuevo_rol)
    if rol == rol_actual:
        return rol

    # El rol administrador también habilita decisiones codificadas por rol y
    # alcance global; por eso no puede delegarlo un perfil no administrador.
    if rol in {"admin", "admin_financiero"} and getattr(actor, "rol", None) != "admin":
        abort(403)

    for modulo, acciones in permisos_predeterminados_rol(rol).items():
        for accion, habilitado in acciones.items():
            if habilitado and not actor.tiene_permiso(modulo, accion):
                abort(403)

    return rol


def verificar_cambio_rol(actor, usuario_objetivo, nuevo_rol: str) -> str:
    """Valida un cambio de rol y bloquea cualquier autoedición del rol."""

    rol = normalizar_rol(nuevo_rol)
    if actor.id == usuario_objetivo.id and rol != usuario_objetivo.rol:
        abort(403, description="No puedes modificar tu propio rol o permisos.")
    if usuario_objetivo.id == 1 and rol != "admin":
        abort(403, description="El administrador principal debe conservar acceso total.")
    if usuario_objetivo.rol == "admin" and getattr(actor, "rol", None) != "admin":
        abort(403)
    return verificar_rol_otorgable(
        actor,
        rol,
        rol_actual=usuario_objetivo.rol,
    )


def verificar_permisos_otorgables(
    actor,
    usuario_objetivo,
    actuales: Mapping[str, Mapping[str, bool]],
    solicitados: Mapping[str, Mapping[str, bool]],
) -> None:
    """Bloquea autoedición y concesiones que superen al usuario que edita."""

    if actor.id == usuario_objetivo.id:
        if solicitados != actuales:
            abort(403, description="No puedes modificar tu propio rol o permisos.")
        return

    for modulo in MODULOS_PERMISOS:
        for accion in ACCIONES_PERMISO:
            se_otorga = solicitados[modulo][accion] and not actuales[modulo][accion]
            if se_otorga and not actor.tiene_permiso(modulo, accion):
                abort(403)
