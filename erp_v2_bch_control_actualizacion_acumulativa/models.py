"""Modelos del ERP V2.

La instancia ``db`` se crea sin enlazarla a una aplicación; ``create_app()``
ejecutará posteriormente ``db.init_app(app)``. Este patrón evita importaciones
circulares y es compatible con Blueprints y Flask-Migrate.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, Index, case, event, func, true
from sqlalchemy.engine import Engine
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Activa llaves foráneas solo cuando el motor real es SQLite."""

    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def utc_now() -> datetime:
    """Devuelve la hora UTC consciente de zona horaria."""

    return datetime.now(UTC)


# Catálogo único usado por Administración → Usuarios. Los nombres guardados
# en la base son estables para que una migración futura pueda renombrar la
# etiqueta visible sin invalidar los permisos ya asignados.
MODULOS_PERMISOS = {
    "nomina": "Nómina",
    "compras": "Órdenes de compra",
    "requisiciones": "Requisiciones",
    "oc_operaciones": "OC de Operaciones",
    "proveedores": "Proveedores",
    "reportes": "Reportes",
    "usuarios": "Usuarios",
    "centros_costo": "Centros de costo",
    "tarjetas_credito": "Tarjetas de crédito",
}

ACCIONES_PERMISO = ("ver", "crear", "editar", "eliminar")


def permisos_predeterminados_rol(rol: str) -> dict[str, dict[str, bool]]:
    """Devuelve una matriz nueva con los accesos iniciales de cada rol.

    La matriz es únicamente el punto de partida. Después del alta, un
    administrador puede modificar cada casilla sin cambiar el rol ni perder la
    delimitación de datos (obra asignada y tipo de requisición/OC).
    """

    matrix = {
        module: {action: False for action in ACCIONES_PERMISO}
        for module in MODULOS_PERMISOS
    }

    def grant(module: str, *actions: str) -> None:
        for action in actions:
            matrix[module][action] = True

    if rol == "admin":
        for module in matrix:
            grant(module, *ACCIONES_PERMISO)
    elif rol == "capturista":
        # Guardar una captura en proceso técnicamente es una edición; se
        # mantiene activa para no impedir la operación normal de Nómina.
        grant("nomina", "ver", "crear", "editar")
    elif rol == "supervisor":
        grant("nomina", "ver", "crear", "editar")
        grant("requisiciones", "ver", "crear", "editar")
        grant("oc_operaciones", "ver", "crear", "editar")
    elif rol == "comprador":
        for module in ("compras", "requisiciones", "proveedores", "reportes"):
            grant(module, *ACCIONES_PERMISO)
    elif rol == "costos":
        grant("reportes", *ACCIONES_PERMISO)
        grant("centros_costo", "ver", "crear", "editar")
        grant("compras", "ver")
        grant("requisiciones", "ver")
    return matrix


# Relación del módulo de nóminas. La columna ``centro_costo_id`` de Usuario se
# conserva como centro principal para compatibilidad con la Fase 2; esta tabla
# permite que un capturista opere más de una obra, como en el sistema original.
usuario_centros_nomina = db.Table(
    "user_projects",
    db.Column(
        "user_id",
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "project_id",
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class CentroCosto(db.Model):
    """Obra u oficina usada para asignar usuarios y capturas semanales."""

    __tablename__ = "centros_costo"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False)
    estado = db.Column(
        db.String(20), nullable=False, default="activa", server_default="activa"
    )
    fecha_apertura = db.Column(db.Date)
    fecha_cierre = db.Column(db.Date)

    # Datos operativos que el sistema original de nóminas requiere para
    # presupuesto, importaciones y reportes. Los centros existentes reciben un
    # código durante la migración, sin cambiar su nombre ni su asignación.
    codigo = db.Column(db.String(40), nullable=False, unique=True, index=True)
    presupuesto_total = db.Column(
        db.Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    presupuesto_mano_obra = db.Column(
        db.Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    descripcion = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    usuarios = db.relationship(
        "Usuario",
        back_populates="centro_costo",
        lazy="select",
    )
    users = db.relationship(
        "Usuario",
        secondary=usuario_centros_nomina,
        back_populates="projects",
        lazy="select",
    )
    budget_items = db.relationship(
        "BudgetItem",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('obra', 'oficina')",
            name="ck_centros_costo_tipo",
        ),
        CheckConstraint(
            "fecha_cierre IS NULL OR fecha_apertura IS NULL "
            "OR fecha_cierre >= fecha_apertura",
            name="ck_centros_costo_fechas",
        ),
    )

    def __repr__(self) -> str:
        return f"<CentroCosto {self.id}: {self.nombre}>"

    @hybrid_property
    def activa(self) -> bool:
        """Alias compatible con el sistema original de PythonAnywhere."""

        return self.estado == "activa"

    @activa.setter
    def activa(self, value: bool) -> None:
        self.estado = "activa" if value else "cerrada"
        if value:
            self.fecha_cierre = None

    @activa.expression
    def activa(cls):
        return cls.estado == "activa"


class Usuario(UserMixin, db.Model):
    """Usuario autenticable del sistema.

    ``UserMixin`` proporciona a Flask-Login las propiedades necesarias como
    ``is_authenticated`` y ``get_id``. La propiedad ``is_active`` se redefine
    para respetar el estado real guardado en la columna ``activo``.
    """

    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre_completo = db.Column(db.String(150), nullable=False)
    correo = db.Column(
        db.String(120), nullable=False, unique=True, index=True
    )

    # Se usa "contrasena" sin ñ como identificador de Python para evitar
    # problemas de codificación en scripts, consolas y herramientas externas.
    contrasena_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(20), nullable=False)

    centro_costo_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    activo = db.Column(
        db.Boolean, nullable=False, default=True, server_default=true()
    )
    fecha_alta = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    centro_costo = db.relationship(
        "CentroCosto",
        back_populates="usuarios",
    )
    eventos_auditoria = db.relationship(
        "BitacoraAuditoria",
        back_populates="usuario",
        lazy="select",
    )
    projects = db.relationship(
        "CentroCosto",
        secondary=usuario_centros_nomina,
        back_populates="users",
        lazy="select",
    )
    permisos = db.relationship(
        "Permiso",
        back_populates="usuario",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "rol IN ('admin', 'capturista', 'supervisor', 'comprador', 'costos')",
            name="ck_usuarios_rol",
        ),
        # Un administrador siempre tiene acceso global y por eso no debe quedar
        # ligado accidentalmente a un solo centro de costo.
        CheckConstraint(
            "rol IN ('capturista', 'supervisor') OR centro_costo_id IS NULL",
            name="ck_usuarios_centro_segun_rol",
        ),
    )

    @validates("correo")
    def normalize_email(self, _key: str, value: str) -> str:
        """Guarda correos sin espacios y en minúsculas.

        La validación de formato y duplicados con mensajes amigables quedará en
        los formularios Flask-WTF; esta validación protege también altas hechas
        desde scripts o futuras importaciones.
        """

        normalized = (value or "").strip().lower()
        if not normalized:
            raise ValueError("El correo del usuario es obligatorio.")
        return normalized

    def set_password(self, password: str) -> None:
        """Genera y almacena un hash; nunca guarda la contraseña original."""

        self.contrasena_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Compara una contraseña recibida contra el hash almacenado."""

        return check_password_hash(self.contrasena_hash, password)

    @property
    def is_active(self) -> bool:
        """Flask-Login impedirá operar a una cuenta desactivada."""

        return bool(self.activo)

    @property
    def es_admin(self) -> bool:
        return self.rol == "admin"

    @property
    def es_capturista(self) -> bool:
        return self.rol == "capturista"

    @property
    def es_supervisor(self) -> bool:
        return self.rol == "supervisor"

    @property
    def es_comprador(self) -> bool:
        return self.rol == "comprador"

    @property
    def es_costos(self) -> bool:
        return self.rol == "costos"

    @property
    def puede_autorizar_compras(self) -> bool:
        return self.rol in {"admin", "costos"}

    @property
    def acceso_global_obras(self) -> bool:
        return self.rol in {"admin", "comprador", "costos"}

    def tiene_permiso(self, modulo: str, accion: str = "ver") -> bool:
        """Comprueba un permiso individual con respaldo por rol.

        El respaldo permite iniciar con seguridad durante una instalación o
        una prueba que todavía no haya materializado las filas de ``permisos``.
        En cuanto existe una fila para el módulo, sus cuatro valores son la
        autoridad efectiva y pueden desactivar incluso un acceso del rol.
        """

        if modulo not in MODULOS_PERMISOS or accion not in ACCIONES_PERMISO:
            return False
        permission = next(
            (item for item in self.permisos if item.modulo == modulo), None
        )
        if permission is not None:
            return bool(getattr(permission, f"puede_{accion}"))
        return permisos_predeterminados_rol(self.rol)[modulo][accion]

    def asignar_permisos_predeterminados(self, *, reemplazar: bool = True) -> None:
        """Crea o restablece la matriz inicial correspondiente al rol."""

        defaults = permisos_predeterminados_rol(self.rol)
        by_module = {permission.modulo: permission for permission in self.permisos}
        for module, values in defaults.items():
            permission = by_module.get(module)
            if permission is None:
                permission = Permiso(modulo=module)
                self.permisos.append(permission)
            elif not reemplazar:
                continue
            for action, enabled in values.items():
                setattr(permission, f"puede_{action}", enabled)

    @property
    def rol_etiqueta(self) -> str:
        return {
            "admin": "Administrador",
            "capturista": "Capturista",
            "supervisor": "Supervisor de obra",
            "comprador": "Comprador",
            "costos": "Costos",
        }.get(self.rol, self.rol.title())

    @property
    def is_admin(self) -> bool:
        """Nombre usado por las reglas y plantillas del módulo original."""

        return self.es_admin

    @hybrid_property
    def role(self) -> str:
        return "administrador" if self.rol == "admin" else self.rol

    @role.setter
    def role(self, value: str) -> None:
        self.rol = "admin" if value == "administrador" else value
        if self.rol not in {"capturista", "supervisor"}:
            self.centro_costo_id = None
            self.projects = []

    @role.expression
    def role(cls):
        return case((cls.rol == "admin", "administrador"), else_=cls.rol)

    @hybrid_property
    def email(self) -> str:
        return self.correo

    @email.setter
    def email(self, value: str) -> None:
        self.correo = value

    @email.expression
    def email(cls):
        return cls.correo

    @hybrid_property
    def username(self) -> str:
        return self.correo

    @username.setter
    def username(self, value: str) -> None:
        self.correo = value

    @username.expression
    def username(cls):
        return cls.correo

    @property
    def password_hash(self) -> str:
        return self.contrasena_hash

    @password_hash.setter
    def password_hash(self, value: str) -> None:
        self.contrasena_hash = value

    def __repr__(self) -> str:
        return f"<Usuario {self.id}: {self.correo}>"


class Permiso(db.Model):
    """Permisos CRUD configurables para un módulo y usuario concretos."""

    __tablename__ = "permisos"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    modulo = db.Column(db.String(50), nullable=False)
    puede_ver = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )
    puede_crear = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )
    puede_editar = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )
    puede_eliminar = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )

    usuario = db.relationship("Usuario", back_populates="permisos")

    __table_args__ = (
        db.UniqueConstraint(
            "usuario_id", "modulo", name="uq_permisos_usuario_modulo"
        ),
    )


class BitacoraAuditoria(db.Model):
    """Registro básico de acciones relevantes dentro del sistema."""

    __tablename__ = "bitacora_auditoria"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    accion = db.Column(db.String(100), nullable=False)
    tabla_afectada = db.Column(db.String(50), nullable=False)
    registro_id = db.Column(db.Integer)
    fecha_hora = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        index=True,
    )
    detalle = db.Column(db.Text)

    usuario = db.relationship(
        "Usuario",
        back_populates="eventos_auditoria",
    )

    __table_args__ = (
        Index(
            "ix_bitacora_tabla_registro",
            "tabla_afectada",
            "registro_id",
        ),
    )

    def __repr__(self) -> str:
        return f"<BitacoraAuditoria {self.id}: {self.accion}>"

    # Alias de lectura para las pantallas de auditoría recuperadas del sistema
    # original. Las escrituras se realizan siempre con los nombres del ERP.
    @property
    def user(self):
        return self.usuario

    @property
    def entidad(self):
        return self.tabla_afectada

    @property
    def entidad_id(self):
        return self.registro_id

    @property
    def created_at(self):
        return self.fecha_hora
