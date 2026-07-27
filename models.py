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


# Catálogo único usado por Administración → Usuarios. Cada clave corresponde
# a una opción real del menú o a una capacidad sensible que debe poder
# revocarse sin depender del rol. Las claves históricas agrupadas se conservan
# en ``LEGACY_PERMISSION_ALIASES`` para que rutas y permisos existentes sigan
# funcionando durante la actualización, pero ya no aparecen en la matriz.
MODULOS_PERMISOS = {
    "dashboard_general": "Dashboard general",
    "dashboard_supervisor": "Dashboard del Supervisor",
    "dashboard_ejecutivo": "Dashboard ejecutivo",
    "nomina_dashboard": "Nóminas · Dashboard",
    "nominas_semanales": "Nóminas · Nóminas semanales",
    "trabajadores": "Nóminas · Trabajadores",
    "prestamos": "Nóminas · Préstamos",
    "pagos_adicionales": "Nóminas · Pagos adicionales",
    "empresas_pago": "Nóminas · Empresas de pago",
    "gastos_oficina": "Nóminas · Gastos de oficina",
    "subcontratos": "Obras · Subcontratos",
    "contratistas": "Obras · Contratistas",
    "reportes_nomina": "Reportes · Nómina",
    "compras_dashboard": "Compras · Dashboard",
    "explosion_insumos": "Compras · Explosión de insumos",
    "insumos": "Compras · Catálogo de insumos",
    "requisiciones": "Compras · Requisiciones",
    "cotizaciones_rfq": "Compras · Cotizaciones y RFQ",
    "licitaciones": "Compras · Licitaciones",
    "oc_compras": "Compras · OC de Compras",
    "oc_operaciones": "Compras · OC de Operaciones",
    "programacion_pagos": "Compras · Anticipos y programación de pagos",
    "pagos_proveedores": "Compras · Pagos a proveedores",
    "recepcion_materiales": "Almacén · Recepciones",
    "discrepancias_recepcion": "Almacén · Discrepancias",
    "almacen": "Almacén · Bandeja",
    "proveedores": "Compras · Proveedores",
    "proveedores_sensibles": "Compras · Datos sensibles de proveedores",
    "reportes_compras": "Reportes · Compras",
    "smnc": "Compras · SMNC",
    "garantias": "Campo · Garantías",
    "contratos": "Compras · Contratos",
    "conciliacion_facturas": "Compras · Conciliación de facturas",
    "tarjetas_credito": "Finanzas · Tarjetas de crédito",
    "metodos_pago": "Finanzas · Métodos de pago",
    "direcciones_entrega": "Compras · Direcciones de entrega",
    "obras_partidas": "Obras y partidas",
    "centros_costo": "Administración · Centros de costo",
    "parte_diario": "Campo · Partes diarios",
    "avance_obra": "Campo · Avance y cantidades ejecutadas",
    "certificaciones": "Campo · Certificaciones de subcontratos",
    "no_conformidades": "Campo · No conformidades y Punch List",
    "rfis": "Campo · Solicitudes de información (RFI)",
    "seguridad_obra": "Campo · Seguridad y salud en obra",
    "usuarios": "Administración · Usuarios y permisos",
    "seguridad": "Administración · Seguridad y acciones sensibles",
    "ver_nss_completo": "Administración · NSS completo",
}

ACCIONES_PERMISO = (
    "ver",
    "crear",
    "editar",
    "eliminar",
    "aprobar",
    "emitir",
    "cancelar",
    "pagar",
    "conciliar",
)

# Ayuda visual para no presentar acciones sin significado en la matriz. Esta
# lista no sustituye la comprobación del servidor.
ACCIONES_POR_MODULO = {
    "dashboard_general": ("ver",),
    "dashboard_supervisor": ("ver",),
    "dashboard_ejecutivo": ("ver",),
    "nomina_dashboard": ("ver",),
    "reportes_nomina": ("ver", "crear"),
    "compras_dashboard": ("ver",),
    "explosion_insumos": ("ver", "crear", "editar"),
    "cotizaciones_rfq": ("ver", "crear", "editar", "eliminar", "aprobar"),
    "licitaciones": ("ver", "crear", "editar", "eliminar", "aprobar"),
    "oc_compras": (
        "ver",
        "crear",
        "editar",
        "eliminar",
        "aprobar",
        "emitir",
        "cancelar",
    ),
    "oc_operaciones": (
        "ver",
        "crear",
        "editar",
        "eliminar",
        "aprobar",
        "emitir",
        "cancelar",
    ),
    "programacion_pagos": ("ver", "crear", "editar", "aprobar", "pagar"),
    "pagos_proveedores": ("ver", "crear", "editar", "eliminar", "pagar"),
    "recepcion_materiales": ("ver", "crear"),
    "discrepancias_recepcion": ("ver", "crear", "editar", "aprobar"),
    "almacen": ("ver",),
    "proveedores_sensibles": ("ver", "crear", "editar"),
    "direcciones_entrega": ("ver", "editar"),
    "reportes_compras": ("ver", "crear"),
    "garantias": ("ver", "crear", "editar", "aprobar"),
    "conciliacion_facturas": (
        "ver",
        "crear",
        "editar",
        "aprobar",
        "conciliar",
    ),
    "ver_nss_completo": ("ver",),
}

# Los decoradores anteriores a esta versión todavía solicitan estos módulos
# agrupados. Las nuevas rutas vuelven a exigir el permiso específico.
LEGACY_PERMISSION_ALIASES = {
    "nomina": (
        "nomina_dashboard",
        "nominas_semanales",
        "trabajadores",
        "prestamos",
        "pagos_adicionales",
        "empresas_pago",
        "gastos_oficina",
        "subcontratos",
        "contratistas",
    ),
    "compras": (
        "compras_dashboard",
        "explosion_insumos",
        "insumos",
        "oc_compras",
        "programacion_pagos",
        "pagos_proveedores",
        "smnc",
        "metodos_pago",
    ),
    "reportes": ("reportes_nomina", "reportes_compras"),
}


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
            if module == "ver_nss_completo":
                grant(module, "ver")
                continue
            grant(module, *ACCIONES_PERMISO)
    elif rol == "admin_financiero":
        grant("dashboard_general", "ver")
        for module in (
            "nomina_dashboard",
            "nominas_semanales",
            "pagos_adicionales",
            "empresas_pago",
            "reportes_nomina",
            "compras_dashboard",
            "oc_compras",
            "oc_operaciones",
            "programacion_pagos",
            "pagos_proveedores",
            "proveedores",
            "proveedores_sensibles",
            "reportes_compras",
        ):
            grant(module, "ver", "crear", "editar", "aprobar")
        grant("nominas_semanales", "pagar", "conciliar")
        grant("programacion_pagos", "pagar")
        grant("pagos_proveedores", "pagar")
        grant("oc_compras", "emitir")
        grant("oc_operaciones", "emitir")
        grant("centros_costo", "ver")
        grant("tarjetas_credito", *ACCIONES_PERMISO)
        grant("conciliacion_facturas", *ACCIONES_PERMISO)
        grant("contratos", "ver")
        grant("dashboard_ejecutivo", "ver")
        grant("ver_nss_completo", "ver")
    elif rol == "capturista":
        # Guardar una captura en proceso técnicamente es una edición; se
        # mantiene activa para no impedir la operación normal de Nómina.
        grant("dashboard_general", "ver")
        grant("nomina_dashboard", "ver")
        for module in (
            "nominas_semanales",
            "trabajadores",
            "prestamos",
            "pagos_adicionales",
        ):
            grant(module, "ver", "crear", "editar")
        grant("obras_partidas", "ver")
    elif rol == "supervisor":
        grant("dashboard_supervisor", "ver")
        # C1–C3 ya permitían que el Supervisor preparara la nómina de sus
        # obras, administrara sus trabajadores y solicitara préstamos/pagos
        # adicionales. La matriz granular conserva esas capacidades sin
        # abrirle empresas de pago, reportes ni acciones financieras.
        grant("nomina_dashboard", "ver")
        for module in (
            "nominas_semanales",
            "trabajadores",
            "prestamos",
            "pagos_adicionales",
        ):
            grant(module, "ver", "crear", "editar")
        grant("compras_dashboard", "ver")
        grant("explosion_insumos", "ver")
        grant("requisiciones", "ver", "crear", "editar")
        grant("oc_operaciones", "ver", "crear", "editar")
        grant("proveedores", "ver", "crear")
        grant("obras_partidas", "ver")
        grant("smnc", "ver", "crear", "editar")
        grant("garantias", "ver", "crear", "editar")
        grant("parte_diario", *ACCIONES_PERMISO)
        grant("avance_obra", *ACCIONES_PERMISO)
        grant("certificaciones", "ver", "crear", "editar", "aprobar")
        grant("no_conformidades", *ACCIONES_PERMISO)
        grant("rfis", *ACCIONES_PERMISO)
        grant("seguridad_obra", *ACCIONES_PERMISO)
    elif rol == "comprador":
        grant("dashboard_general", "ver")
        for module in (
            "compras_dashboard",
            "explosion_insumos",
            "insumos",
            "requisiciones",
            "cotizaciones_rfq",
            "licitaciones",
            "oc_compras",
            "proveedores",
            "proveedores_sensibles",
            "reportes_compras",
            "smnc",
        ):
            grant(module, *ACCIONES_PERMISO)
        grant("oc_compras", "emitir", "cancelar")
        grant("obras_partidas", "ver")
        grant("direcciones_entrega", "ver", "editar")
        grant("contratos", "ver", "crear", "editar", "eliminar")
        grant("conciliacion_facturas", "ver", "crear", "editar", "conciliar")
        # Conserva la recepción histórica del Comprador. El Supervisor no
        # recibe este permiso; el Almacenista usa su bandeja móvil con el mismo
        # permiso y con alcance obligatorio por obra.
        grant("recepcion_materiales", "ver", "crear")
        # Se preserva la operación financiera que el rol Comprador ya tenía en
        # Fase 5. La separación de funciones de las OC de Operaciones se exige
        # además con validación del beneficiario y programación autorizada.
        grant("pagos_proveedores", "ver", "crear", "editar", "pagar")
        grant("programacion_pagos", "ver", "editar")
    elif rol == "almacenista":
        grant("almacen", "ver")
        grant("recepcion_materiales", "ver", "crear")
        grant("discrepancias_recepcion", "ver", "crear")
    elif rol == "ceo":
        grant("dashboard_ejecutivo", "ver")
    elif rol == "costos":
        grant("dashboard_general", "ver")
        grant("reportes_nomina", *ACCIONES_PERMISO)
        grant("reportes_compras", *ACCIONES_PERMISO)
        grant("centros_costo", "ver", "crear", "editar")
        grant("obras_partidas", "ver", "crear", "editar")
        grant("compras_dashboard", "ver")
        grant("explosion_insumos", "ver", "crear", "editar")
        grant("requisiciones", "ver")
        grant("avance_obra", "ver")
        grant("licitaciones", "ver")
        grant("contratos", "ver")
        grant("smnc", "ver", "aprobar")
        grant("garantias", "ver", "aprobar")
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
    obra_principal_id = db.Column(
        db.Integer,
        db.ForeignKey("centros_costo.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

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
    direccion_entrega = db.Column(db.String(500))
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
    obra_principal = db.relationship(
        "CentroCosto",
        remote_side=[id],
        back_populates="centros_garantia",
        foreign_keys=[obra_principal_id],
    )
    centros_garantia = db.relationship(
        "CentroCosto",
        back_populates="obra_principal",
        foreign_keys=[obra_principal_id],
        lazy="select",
    )

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('obra', 'oficina', 'garantia')",
            name="ck_centros_costo_tipo",
        ),
        CheckConstraint(
            "(tipo = 'garantia' AND obra_principal_id IS NOT NULL) OR "
            "(tipo <> 'garantia' AND obra_principal_id IS NULL)",
            name="ck_centros_costo_garantia_principal",
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
    intentos_fallidos = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    ventana_intentos_inicio = db.Column(db.DateTime(timezone=True))
    bloqueado_hasta = db.Column(db.DateTime(timezone=True), index=True)
    mfa_secret = db.Column(db.String(64))
    mfa_confirmado_en = db.Column(db.DateTime(timezone=True))

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
            "rol IN ('admin', 'admin_financiero', 'capturista', 'supervisor', "
            "'comprador', 'almacenista', 'ceo', 'costos')",
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
    def es_admin_financiero(self) -> bool:
        return self.rol == "admin_financiero"

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
    def es_almacenista(self) -> bool:
        return self.rol == "almacenista"

    @property
    def es_ceo(self) -> bool:
        return self.rol == "ceo"

    @property
    def es_costos(self) -> bool:
        return self.rol == "costos"

    @property
    def puede_autorizar_compras(self) -> bool:
        return self.rol in {"admin", "costos"}

    @property
    def acceso_global_obras(self) -> bool:
        # El Comprador ve todas las obras por regla de negocio; además se
        # materializan sus vínculos en ``user_projects`` para que integraciones
        # y reportes históricos que lean esa tabla conserven el mismo alcance.
        return self.rol in {
            "admin",
            "admin_financiero",
            "costos",
            "comprador",
        }

    def tiene_permiso(self, modulo: str, accion: str = "ver") -> bool:
        """Comprueba un permiso individual con respaldo por rol.

        El respaldo permite iniciar con seguridad durante una instalación o
        una prueba que todavía no haya materializado las filas de ``permisos``.
        En cuanto existe una fila para el módulo, sus cuatro valores son la
        autoridad efectiva y pueden desactivar incluso un acceso del rol.
        """

        if accion not in ACCIONES_PERMISO:
            return False
        # La cuenta fundadora nunca puede perder autoridad por una fila de
        # permisos incompleta o manipulada. El rol sigue validándose para que
        # un id reutilizado que no sea administrador no herede este acceso.
        if self.id == 1 and self.rol == "admin":
            return True
        permission = next(
            (item for item in self.permisos if item.modulo == modulo), None
        )
        if modulo in MODULOS_PERMISOS:
            if permission is not None:
                return bool(getattr(permission, f"puede_{accion}"))
            return permisos_predeterminados_rol(self.rol)[modulo][accion]
        aliases = LEGACY_PERMISSION_ALIASES.get(modulo)
        if aliases:
            legacy_value = bool(
                permission and getattr(permission, f"puede_{accion}", False)
            )
            return legacy_value or any(
                self.tiene_permiso(child, accion) for child in aliases
            )
        return False

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
            "admin": "Administrador General",
            "admin_financiero": "Administrador financiero",
            "capturista": "Capturista de nómina",
            "supervisor": "Residente / Supervisor de obra",
            "comprador": "Comprador",
            "almacenista": "Almacenista",
            "ceo": "CEO / Dirección",
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
        if self.rol not in {
            "capturista",
            "supervisor",
            "comprador",
            "almacenista",
        }:
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
    puede_aprobar = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )
    puede_emitir = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )
    puede_cancelar = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )
    puede_pagar = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )
    puede_conciliar = db.Column(
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
