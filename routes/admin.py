"""Rutas administrativas para centros de costo y usuarios."""

from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from forms import ActionForm, CentroCostoForm, UsuarioEditForm, UsuarioForm
from models import (
    ACCIONES_PERMISO,
    ACCIONES_POR_MODULO,
    MODULOS_PERMISOS,
    BitacoraAuditoria,
    CentroCosto,
    Permiso,
    Usuario,
    db,
    permisos_predeterminados_rol,
)
from utils.decorators import permission_required
from utils.access import verificar_acceso_obra
from services.actualizacion_operativa import (
    asignar_obra_a_compradores,
    asignar_todas_las_obras_comprador,
)
from utils.user_permissions import (
    matriz_permisos_efectivos,
    matriz_permisos_formulario,
    verificar_cambio_rol,
    verificar_permisos_otorgables,
    verificar_rol_otorgable,
)


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
ROLES_CON_OBRA_ASIGNADA = {
    "capturista",
    "supervisor",
    "almacenista",
}


def usuario_centro_principal(usuario: Usuario) -> int:
    """Obtiene el centro mostrado en el formulario sin perder compatibilidad."""

    if usuario.centro_costo_id:
        return usuario.centro_costo_id
    return min((centro.id for centro in usuario.projects), default=0)


def add_admin_audit_event(
    accion: str,
    tabla_afectada: str,
    registro_id: int | None,
    detalle: str,
) -> None:
    """Agrega una acción administrativa a la transacción actual."""

    db.session.add(
        BitacoraAuditoria(
            usuario_id=current_user.id,
            accion=accion,
            tabla_afectada=tabla_afectada,
            registro_id=registro_id,
            detalle=detalle,
        )
    )


def active_center_choices() -> list[tuple[int, str]]:
    """Construye las opciones válidas para asignar roles operativos."""

    centros = (
        CentroCosto.query.filter(
            CentroCosto.estado == "activa",
            CentroCosto.tipo.in_(("obra", "oficina")),
        )
        .order_by(CentroCosto.tipo.asc(), CentroCosto.nombre.asc())
        .all()
    )
    if not current_user.acceso_global_obras:
        allowed_ids = {centro.id for centro in current_user.projects}
        if current_user.centro_costo_id:
            allowed_ids.add(current_user.centro_costo_id)
        centros = [centro for centro in centros if centro.id in allowed_ids]
    return [(0, "Selecciona un centro de costo")] + [
        (
            centro.id,
            f"{centro.nombre} ({'Obra' if centro.tipo == 'obra' else 'Oficina'})",
        )
        for centro in centros
    ]


def selected_project_ids() -> list[int]:
    """Lee selección múltiple y conserva compatibilidad con el selector viejo."""

    selected = {
        int(value)
        for value in request.form.getlist("project_ids")
        if value.isdigit() and int(value) > 0
    }
    legacy = request.form.get("centro_costo_id", type=int)
    if not selected and legacy:
        selected.add(legacy)
    return sorted(selected)


def resolve_user_projects(role: str, selected_ids: list[int]) -> list[CentroCosto]:
    """Valida el conjunto completo antes de reemplazar una asignación."""

    if role == "comprador":
        return (
            CentroCosto.query.filter(CentroCosto.tipo == "obra")
            .order_by(CentroCosto.id)
            .all()
        )
    if role not in ROLES_CON_OBRA_ASIGNADA:
        return []
    if not selected_ids:
        raise ValueError("Selecciona al menos una obra o centro de costo.")
    for project_id in selected_ids:
        verificar_acceso_obra(
            current_user,
            project_id,
            respetar_obra_activa=False,
        )
    projects = (
        CentroCosto.query.filter(
            CentroCosto.id.in_(selected_ids),
            CentroCosto.estado == "activa",
        )
        .order_by(CentroCosto.nombre)
        .all()
    )
    if len(projects) != len(set(selected_ids)):
        raise ValueError("Una de las obras seleccionadas no existe o está cerrada.")
    if role in {"supervisor", "almacenista"} and any(
        project.tipo != "obra" for project in projects
    ):
        raise ValueError(
            "Supervisor y Almacenista solo pueden asignarse a obras."
        )
    return projects


@admin_bp.route("/centros")
@permission_required("centros_costo", "ver")
def centros_lista():
    """Lista todos los centros, incluidos los que ya están cerrados."""

    centros = CentroCosto.query.order_by(CentroCosto.nombre.asc()).all()
    return render_template(
        "admin/centros_lista.html",
        centros=centros,
        action_form=ActionForm(),
    )


@admin_bp.route("/centros/nuevo", methods=["GET", "POST"])
@permission_required("centros_costo", "crear")
def centro_nuevo():
    """Registra un centro activo sin eliminar ni modificar otros registros."""

    form = CentroCostoForm()
    if form.validate_on_submit():
        centro = CentroCosto(
            nombre=form.nombre.data,
            codigo=form.codigo.data,
            tipo=form.tipo.data,
            estado="activa",
            fecha_apertura=form.fecha_apertura.data or date.today(),
            fecha_cierre=None,
            presupuesto_total=form.presupuesto_total.data,
            presupuesto_mano_obra=form.presupuesto_mano_obra.data,
            descripcion=form.descripcion.data,
            direccion_entrega=form.direccion_entrega.data,
        )

        try:
            db.session.add(centro)
            db.session.flush()
            asignar_obra_a_compradores(centro)
            add_admin_audit_event(
                accion="CREAR_CENTRO_COSTO",
                tabla_afectada="centros_costo",
                registro_id=centro.id,
                detalle=f"Alta del centro de costo {centro.nombre}.",
            )
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash(
                "No fue posible guardar el centro de costo. Revisa los datos e intenta nuevamente.",
                "danger",
            )
        else:
            flash(
                "Centro de costo creado correctamente. Agrega ahora las partidas "
                "que se usarán en la captura de nómina.",
                "success",
            )
            return redirect(
                url_for("nominas.project_detail", project_id=centro.id)
            )

    return render_template(
        "admin/centro_form.html",
        form=form,
        centro=None,
    )


@admin_bp.route("/centros/<int:centro_id>/editar", methods=["GET", "POST"])
@permission_required("centros_costo", "editar")
def centro_editar(centro_id: int):
    """Modifica los datos descriptivos de un centro existente."""

    centro = CentroCosto.query.get_or_404(centro_id)
    verificar_acceso_obra(current_user, centro.id)
    form = CentroCostoForm(obj=centro, centro_actual=centro)

    if form.validate_on_submit():
        nombre_anterior = centro.nombre
        centro.nombre = form.nombre.data
        centro.codigo = form.codigo.data
        centro.tipo = form.tipo.data
        centro.fecha_apertura = form.fecha_apertura.data
        centro.presupuesto_total = form.presupuesto_total.data
        centro.presupuesto_mano_obra = form.presupuesto_mano_obra.data
        centro.descripcion = form.descripcion.data
        centro.direccion_entrega = form.direccion_entrega.data

        try:
            add_admin_audit_event(
                accion="EDITAR_CENTRO_COSTO",
                tabla_afectada="centros_costo",
                registro_id=centro.id,
                detalle=(
                    f"Edición del centro {nombre_anterior}; nombre actual: {centro.nombre}."
                ),
            )
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash(
                "No fue posible actualizar el centro de costo.",
                "danger",
            )
        else:
            flash("Centro de costo actualizado correctamente.", "success")
            return redirect(url_for("admin.centros_lista"))

    return render_template(
        "admin/centro_form.html",
        form=form,
        centro=centro,
    )


@admin_bp.post("/centros/<int:centro_id>/estado")
@permission_required("centros_costo", "editar")
def centro_cambiar_estado(centro_id: int):
    """Cierra o reactiva un centro sin borrarlo físicamente."""

    form = ActionForm()
    if not form.validate_on_submit():
        flash("No fue posible validar la solicitud.", "danger")
        return redirect(url_for("admin.centros_lista"))

    centro = CentroCosto.query.get_or_404(centro_id)
    verificar_acceso_obra(current_user, centro.id)
    estaba_activo = centro.estado == "activa"

    if estaba_activo:
        centro.estado = "cerrada"
        centro.fecha_cierre = date.today()
        accion = "CERRAR_CENTRO_COSTO"
        mensaje = "Centro de costo cerrado correctamente."
    else:
        centro.estado = "activa"
        centro.fecha_cierre = None
        accion = "REACTIVAR_CENTRO_COSTO"
        mensaje = "Centro de costo reactivado correctamente."

    try:
        add_admin_audit_event(
            accion=accion,
            tabla_afectada="centros_costo",
            registro_id=centro.id,
            detalle=f"Cambio de estado de {centro.nombre} a {centro.estado}.",
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash("No fue posible cambiar el estado del centro.", "danger")
    else:
        flash(mensaje, "success")

    return redirect(url_for("admin.centros_lista"))


@admin_bp.route("/usuarios")
@permission_required("usuarios", "ver")
def usuarios_lista():
    """Lista usuarios activos e inactivos sin ocultar el historial."""

    usuarios = (
        Usuario.query.options(
            joinedload(Usuario.centro_costo),
            selectinload(Usuario.projects),
        )
        .order_by(Usuario.activo.desc(), Usuario.nombre_completo.asc())
        .all()
    )
    return render_template(
        "admin/usuarios_lista.html",
        usuarios=usuarios,
        action_form=ActionForm(),
    )


@admin_bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@permission_required("usuarios", "crear")
def usuario_nuevo():
    """Crea usuarios y limita el rol otorgado a la autoridad del actor."""

    form = UsuarioForm()
    form.centro_costo_id.choices = active_center_choices()
    form.project_ids.choices = active_center_choices()[1:]
    selected_ids = selected_project_ids() if request.method == "POST" else []
    if selected_ids:
        form.project_ids.data = selected_ids
        form.centro_costo_id.data = selected_ids[0]

    if form.validate_on_submit():
        next_role = verificar_rol_otorgable(current_user, form.rol.data)
        try:
            selected_projects = resolve_user_projects(next_role, selected_ids)
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template(
                "admin/usuario_form.html",
                form=form,
                usuario=None,
                has_active_centers=bool(form.project_ids.choices),
                modules=MODULOS_PERMISOS,
                actions=ACCIONES_PERMISO,
                actions_by_module=ACCIONES_POR_MODULO,
                permission_matrix=permisos_predeterminados_rol(
                    form.rol.data or "capturista"
                ),
            )
        centro_id = (
            selected_projects[0].id
            if next_role in {"capturista", "supervisor"} and selected_projects
            else None
        )
        usuario = Usuario(
            nombre_completo=form.nombre_completo.data,
            correo=form.correo.data,
            rol=next_role,
            centro_costo_id=(
                centro_id if next_role in {"capturista", "supervisor"} else None
            ),
            activo=True,
        )
        usuario.set_password(form.contrasena.data)
        usuario.asignar_permisos_predeterminados()

        usuario.projects = selected_projects
        if next_role == "comprador":
            asignar_todas_las_obras_comprador(usuario)

        try:
            db.session.add(usuario)
            db.session.flush()
            add_admin_audit_event(
                accion="CREAR_USUARIO",
                tabla_afectada="usuarios",
                registro_id=usuario.id,
                detalle=f"Alta de {usuario.correo} con rol {usuario.rol}.",
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("El correo ya está registrado por otro usuario.", "danger")
        except SQLAlchemyError:
            db.session.rollback()
            flash("No fue posible crear el usuario.", "danger")
        else:
            flash("Usuario creado correctamente.", "success")
            return redirect(url_for("admin.usuarios_lista"))

    return render_template(
        "admin/usuario_form.html",
        form=form,
        usuario=None,
        has_active_centers=len(form.centro_costo_id.choices) > 1,
        modules=MODULOS_PERMISOS,
        actions=ACCIONES_PERMISO,
        actions_by_module=ACCIONES_POR_MODULO,
        permission_matrix=permisos_predeterminados_rol(form.rol.data or "capturista"),
    )


@admin_bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@permission_required("usuarios", "editar")
def usuario_editar(usuario_id: int):
    """Edita datos y las acciones configurables de cada módulo por usuario."""

    usuario = Usuario.query.options(
        joinedload(Usuario.centro_costo),
        selectinload(Usuario.projects),
    ).get_or_404(usuario_id)
    form = UsuarioEditForm(obj=usuario, usuario_actual=usuario)
    form.centro_costo_id.choices = active_center_choices()
    form.project_ids.choices = active_center_choices()[1:]
    if request.method == "GET":
        form.rol.data = usuario.rol
        form.centro_costo_id.data = usuario_centro_principal(usuario)
        form.project_ids.data = [project.id for project in usuario.projects]
    selected_ids = (
        selected_project_ids()
        if request.method == "POST"
        else [project.id for project in usuario.projects]
    )
    if request.method == "POST" and selected_ids:
        form.project_ids.data = selected_ids
        form.centro_costo_id.data = selected_ids[0]

    if form.validate_on_submit():
        previous_role = usuario.rol
        next_role = verificar_cambio_rol(current_user, usuario, form.rol.data)
        current_permissions = matriz_permisos_efectivos(usuario)
        requested_permissions = matriz_permisos_formulario(request.form)
        verificar_permisos_otorgables(
            current_user,
            usuario,
            current_permissions,
            requested_permissions,
        )
        editing_self = usuario.id == current_user.id
        if editing_self and set(selected_ids) != {
            project.id for project in usuario.projects
        }:
            # La asignación de obra también es autoridad: una cuenta nunca
            # puede ampliar por sí misma el conjunto de documentos que opera.
            abort(403, description="No puedes modificar tu propio rol o permisos.")

        if usuario.id == 1 and (
            next_role != "admin" or requested_permissions != current_permissions
        ):
            abort(403, description="El administrador principal debe conservar acceso total.")

        if (
            usuario.rol == "admin"
            and next_role != "admin"
            and Usuario.query.filter_by(rol="admin", activo=True).count() <= 1
        ):
            flash("Debe permanecer por lo menos un administrador activo.", "danger")
        else:
            usuario.nombre_completo = form.nombre_completo.data
            usuario.correo = form.correo.data
            if not editing_self:
                usuario.rol = next_role
                try:
                    selected_projects = resolve_user_projects(
                        next_role,
                        selected_ids,
                    )
                except ValueError as exc:
                    db.session.rollback()
                    flash(str(exc), "danger")
                    permission_matrix = matriz_permisos_efectivos(usuario)
                    return render_template(
                        "admin/usuario_form.html",
                        form=form,
                        usuario=usuario,
                        has_active_centers=bool(form.project_ids.choices),
                        modules=MODULOS_PERMISOS,
                        actions=ACCIONES_PERMISO,
                        actions_by_module=ACCIONES_POR_MODULO,
                        permission_matrix=permission_matrix,
                        editing_self=False,
                        default_matrices={
                            role: permisos_predeterminados_rol(role)
                            for role in (
                                "admin",
                                "admin_financiero",
                                "capturista",
                                "supervisor",
                                "comprador",
                                "almacenista",
                                "ceo",
                                "costos",
                            )
                        },
                    )
                centro_id = (
                    selected_projects[0].id
                    if next_role in {"capturista", "supervisor"}
                    and selected_projects
                    else None
                )
                usuario.centro_costo_id = (
                    centro_id
                    if next_role in {"capturista", "supervisor"}
                    else None
                )
                usuario.projects = selected_projects
                if next_role == "comprador":
                    asignar_todas_las_obras_comprador(usuario)
            if form.contrasena.data:
                usuario.set_password(form.contrasena.data)

            if not editing_self:
                by_module = {
                    permission.modulo: permission
                    for permission in usuario.permisos
                }
                for module in MODULOS_PERMISOS:
                    permission = by_module.get(module)
                    if permission is None:
                        permission = Permiso(usuario=usuario, modulo=module)
                        db.session.add(permission)
                    for action in ACCIONES_PERMISO:
                        setattr(
                            permission,
                            f"puede_{action}",
                            requested_permissions[module][action],
                        )

            try:
                add_admin_audit_event(
                    accion="EDITAR_USUARIO_PERMISOS",
                    tabla_afectada="usuarios",
                    registro_id=usuario.id,
                    detalle=(
                        f"Edición de {usuario.correo}; rol {previous_role} → {next_role}."
                    ),
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("El correo ya está registrado por otro usuario.", "danger")
            except SQLAlchemyError:
                db.session.rollback()
                flash("No fue posible actualizar el usuario.", "danger")
            else:
                flash("Usuario y permisos actualizados correctamente.", "success")
                return redirect(url_for("admin.usuarios_lista"))

    permission_matrix = matriz_permisos_efectivos(usuario)
    return render_template(
        "admin/usuario_form.html",
        form=form,
        usuario=usuario,
        has_active_centers=len(form.centro_costo_id.choices) > 1,
        modules=MODULOS_PERMISOS,
        actions=ACCIONES_PERMISO,
        actions_by_module=ACCIONES_POR_MODULO,
        permission_matrix=permission_matrix,
        editing_self=usuario.id == current_user.id,
        default_matrices={
            role: permisos_predeterminados_rol(role)
            for role in (
                "admin",
                "admin_financiero",
                "capturista",
                "supervisor",
                "comprador",
                "almacenista",
                "ceo",
                "costos",
            )
        },
    )


@admin_bp.post("/usuarios/<int:usuario_id>/desactivar")
@permission_required("usuarios", "eliminar")
def usuario_desactivar(usuario_id: int):
    """Desactiva una cuenta sin eliminarla ni perder su historial."""

    form = ActionForm()
    if not form.validate_on_submit():
        flash("No fue posible validar la solicitud.", "danger")
        return redirect(url_for("admin.usuarios_lista"))

    usuario = Usuario.query.get_or_404(usuario_id)

    if usuario.id == 1:
        flash("El administrador principal (id=1) debe permanecer activo.", "danger")
        return redirect(url_for("admin.usuarios_lista"))

    if not usuario.activo:
        flash("El usuario ya se encuentra desactivado.", "info")
        return redirect(url_for("admin.usuarios_lista"))

    if usuario.id == current_user.id:
        flash("No puedes desactivar la cuenta con la que iniciaste sesión.", "danger")
        return redirect(url_for("admin.usuarios_lista"))

    if usuario.rol == "admin":
        administradores_activos = Usuario.query.filter_by(
            rol="admin", activo=True
        ).count()
        if administradores_activos <= 1:
            flash(
                "Debe permanecer por lo menos un administrador activo.",
                "danger",
            )
            return redirect(url_for("admin.usuarios_lista"))

    usuario.activo = False
    try:
        add_admin_audit_event(
            accion="DESACTIVAR_USUARIO",
            tabla_afectada="usuarios",
            registro_id=usuario.id,
            detalle=f"Desactivación de la cuenta {usuario.correo}.",
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash("No fue posible desactivar el usuario.", "danger")
    else:
        flash("Usuario desactivado correctamente.", "success")

    return redirect(url_for("admin.usuarios_lista"))
