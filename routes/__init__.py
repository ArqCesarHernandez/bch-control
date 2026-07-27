"""Blueprints de la aplicación."""

from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.nominas import nominas_bp
from routes.compras import compras_bp
from routes.supervisor import campo_bp
from routes.comprador_fase5 import comprador_fase5_bp
from routes.almacenista import almacen_bp
from routes.ceo import ceo_bp
from routes.notificaciones import notificaciones_bp

__all__ = [
    "auth_bp",
    "admin_bp",
    "nominas_bp",
    "compras_bp",
    "campo_bp",
    "comprador_fase5_bp",
    "almacen_bp",
    "ceo_bp",
    "notificaciones_bp",
]
