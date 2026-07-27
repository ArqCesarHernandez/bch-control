"""Presentación segura de identificadores personales sensibles."""

from __future__ import annotations


def enmascarar_nss(nss: str | None) -> str:
    """Muestra únicamente los últimos cuatro caracteres de un NSS."""

    value = "".join(str(nss or "").split())
    if not value:
        return "Sin NSS"
    return f"****{value[-4:]}"


def puede_ver_nss_completo(usuario) -> bool:
    """Comprueba el permiso explícito y conserva el acceso total del id 1."""

    if not getattr(usuario, "is_authenticated", False):
        return False
    if getattr(usuario, "id", None) == 1 and getattr(usuario, "rol", None) == "admin":
        return True
    return bool(usuario.tiene_permiso("ver_nss_completo", "ver"))


def nss_para_usuario(usuario, nss: str | None) -> str:
    """Devuelve el NSS completo o enmascarado según la matriz de permisos."""

    if puede_ver_nss_completo(usuario):
        return nss or "Sin NSS"
    return enmascarar_nss(nss)
