"""Decoradores de autorización por rol.

La interfaz puede ocultar botones, pero la seguridad real siempre se comprueba
en el servidor antes de ejecutar una vista protegida.
"""

from __future__ import annotations

from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def roles_required(*allowed_roles: str):
    """Construye un decorador para uno o varios roles autorizados."""

    allowed = frozenset(allowed_roles)

    def decorator(view_function):
        @wraps(view_function)
        @login_required
        def wrapped_view(*args, **kwargs):
            if not current_user.is_active or current_user.rol not in allowed:
                abort(403)
            return view_function(*args, **kwargs)

        return wrapped_view

    return decorator


def permission_required(modulo: str, accion: str = "ver"):
    """Exige un permiso CRUD individual, además de una sesión activa."""

    def decorator(view_function):
        @wraps(view_function)
        @login_required
        def wrapped_view(*args, **kwargs):
            if (
                not current_user.is_active
                or not current_user.tiene_permiso(modulo, accion)
            ):
                abort(403)
            return view_function(*args, **kwargs)

        return wrapped_view

    return decorator


def any_permission_required(*requirements: tuple[str, str]):
    """Autoriza cuando al menos uno de los permisos indicados está activo."""

    def decorator(view_function):
        @wraps(view_function)
        @login_required
        def wrapped_view(*args, **kwargs):
            if not current_user.is_active or not any(
                current_user.tiene_permiso(module, action)
                for module, action in requirements
            ):
                abort(403)
            return view_function(*args, **kwargs)

        return wrapped_view

    return decorator


def admin_required(view_function):
    """Permite acceso exclusivamente a usuarios con rol administrador."""

    return roles_required("admin")(view_function)


def capturista_required(view_function):
    """Permite operaciones de nómina a capturistas y administradores.

    El administrador hereda este permiso porque el objetivo operativo definido
    para el ERP es que pueda realizar todas las funciones del sistema.
    """

    return roles_required("admin", "capturista")(view_function)


def supervisor_required(view_function):
    """Permite requisiciones y recepciones a supervisores y administradores."""

    return roles_required("admin", "supervisor")(view_function)
