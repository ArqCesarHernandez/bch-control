"""Rutas de autenticación y dashboard inicial."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

import pyotp
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from forms import (
    ActiveProjectForm,
    InitialAdminRegistrationForm,
    LoginForm,
    LogoutForm,
    MFAForm,
)
from models import BitacoraAuditoria, Usuario, db, utc_now
from utils.project_scope import (
    obra_activa_supervisor,
    obras_asignadas_supervisor,
    seleccionar_obra_activa,
)


auth_bp = Blueprint("auth", __name__)


def is_safe_local_url(target: str | None) -> bool:
    """Impide redirecciones hacia dominios externos después del login."""

    if not target or not target.startswith("/") or target.startswith("//"):
        return False
    parsed = urlsplit(target)
    return not parsed.scheme and not parsed.netloc


def add_audit_event(
    usuario_id: int | None,
    accion: str,
    tabla_afectada: str,
    registro_id: int | None = None,
    detalle: str | None = None,
) -> None:
    """Agrega un evento a la transacción actual; quien llama hace commit."""

    db.session.add(
        BitacoraAuditoria(
            usuario_id=usuario_id,
            accion=accion,
            tabla_afectada=tabla_afectada,
            registro_id=registro_id,
            detalle=detalle,
        )
    )


def aware_utc(value: datetime | None) -> datetime | None:
    """Normaliza fechas que SQLite puede devolver sin información de zona."""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def account_is_locked(usuario: Usuario, now: datetime | None = None) -> bool:
    locked_until = aware_utc(usuario.bloqueado_hasta)
    return bool(locked_until and locked_until > (now or utc_now()))


def register_failed_login(usuario: Usuario | None, detail: str) -> bool:
    """Registra el fallo y bloquea la cuenta al quinto intento en 15 minutos."""

    now = utc_now()
    locked = False
    if usuario is not None:
        if account_is_locked(usuario, now):
            locked = True
        else:
            window_start = aware_utc(usuario.ventana_intentos_inicio)
            window = current_app.config["LOGIN_ATTEMPT_WINDOW"]
            if window_start is None or now - window_start >= window:
                usuario.ventana_intentos_inicio = now
                usuario.intentos_fallidos = 1
            else:
                usuario.intentos_fallidos = int(usuario.intentos_fallidos or 0) + 1
            if usuario.intentos_fallidos >= current_app.config["LOGIN_MAX_FAILED_ATTEMPTS"]:
                usuario.bloqueado_hasta = now + current_app.config["LOGIN_LOCKOUT_TIME"]
                locked = True

    add_audit_event(
        usuario_id=usuario.id if usuario else None,
        accion="LOGIN_FALLIDO",
        tabla_afectada="usuarios",
        registro_id=usuario.id if usuario else None,
        detalle=detail[:500],
    )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
    return locked


def clear_failed_logins(usuario: Usuario) -> None:
    usuario.intentos_fallidos = 0
    usuario.ventana_intentos_inicio = None
    usuario.bloqueado_hasta = None


def begin_mfa(usuario: Usuario, target: str | None) -> None:
    session["mfa_pending_user_id"] = usuario.id
    session["mfa_pending_at"] = utc_now().timestamp()
    session["mfa_next"] = target if is_safe_local_url(target) else ""
    session.permanent = False


def pending_mfa_user() -> Usuario | None:
    user_id = session.get("mfa_pending_user_id")
    started = session.get("mfa_pending_at")
    try:
        age = utc_now().timestamp() - float(started)
        user_id = int(user_id)
    except (TypeError, ValueError):
        age = float("inf")
    if age < 0 or age > current_app.config["MFA_PENDING_LIFETIME"].total_seconds():
        session.pop("mfa_pending_user_id", None)
        session.pop("mfa_pending_at", None)
        session.pop("mfa_next", None)
        return None
    usuario = db.session.get(Usuario, user_id)
    if not usuario or not usuario.activo or usuario.rol != "admin":
        return None
    return usuario


def complete_login(usuario: Usuario):
    """Finaliza la sesión únicamente después de contraseña y, en admin, TOTP."""

    target = session.pop("mfa_next", "")
    session.pop("mfa_pending_user_id", None)
    session.pop("mfa_pending_at", None)
    clear_failed_logins(usuario)
    login_user(usuario, remember=False, fresh=True)
    session.permanent = True
    session.modified = True
    try:
        add_audit_event(
            usuario_id=usuario.id,
            accion="INICIAR_SESION",
            tabla_afectada="usuarios",
            registro_id=usuario.id,
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logout_user()
        session.clear()
        flash("No fue posible iniciar la sesión de forma segura. Intenta nuevamente.", "danger")
        return redirect(url_for("auth.login"))
    return redirect(target if is_safe_local_url(target) else url_for("auth.dashboard"))


@auth_bp.app_context_processor
def inject_logout_form():
    """Hace disponible el formulario de logout en la barra de navegación."""

    supervisor_projects = (
        obras_asignadas_supervisor(current_user, incluir_inactivas=False)
        if current_user.is_authenticated and current_user.es_supervisor
        else []
    )
    return {
        "logout_form": LogoutForm(),
        "active_project_form": ActiveProjectForm(),
        "supervisor_projects": supervisor_projects,
        "active_supervisor_project": (
            obra_activa_supervisor(current_user, incluir_inactivas=False)
            if supervisor_projects
            else None
        ),
    }


@auth_bp.before_app_request
def reject_deactivated_session():
    """Expulsa una cuenta que fue desactivada mientras tenía sesión abierta."""

    if current_user.is_authenticated and not current_user.is_active:
        logout_user()
        session.clear()
        flash("Tu cuenta fue desactivada. Comunícate con Administración.", "warning")
        return redirect(url_for("auth.login"))
    return None


@auth_bp.route("/")
def index():
    """Envía a cada visitante a la pantalla que corresponde."""

    if current_user.is_authenticated:
        return redirect(url_for("auth.dashboard"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Permite crear exclusivamente al primer administrador del sistema."""

    if Usuario.query.first() is not None:
        flash(
            "El administrador inicial ya fue creado. Inicia sesión para continuar.",
            "info",
        )
        return redirect(url_for("auth.login"))

    form = InitialAdminRegistrationForm()
    if form.validate_on_submit():
        try:
            # Segunda comprobación justo antes de guardar. La restricción única
            # del correo aporta una protección adicional ante envíos repetidos.
            if Usuario.query.first() is not None:
                flash("El administrador inicial ya fue creado.", "warning")
                return redirect(url_for("auth.login"))

            usuario = Usuario(
                nombre_completo=form.nombre_completo.data,
                correo=form.correo.data,
                rol="admin",
                centro_costo_id=None,
                activo=True,
            )
            usuario.set_password(form.contrasena.data)
            usuario.asignar_permisos_predeterminados()
            db.session.add(usuario)
            db.session.flush()

            add_audit_event(
                usuario_id=usuario.id,
                accion="CREAR_ADMIN_INICIAL",
                tabla_afectada="usuarios",
                registro_id=usuario.id,
                detalle="Creación segura del primer administrador.",
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                "No fue posible crear la cuenta porque el correo ya está registrado.",
                "danger",
            )
        except SQLAlchemyError:
            db.session.rollback()
            flash(
                "No fue posible guardar el administrador. Intenta nuevamente.",
                "danger",
            )
        else:
            flash(
                "Administrador inicial creado correctamente. Ya puedes iniciar sesión.",
                "success",
            )
            return redirect(url_for("auth.login"))

    return render_template("register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Autentica mediante correo y contraseña hasheada."""

    if current_user.is_authenticated:
        return redirect(url_for("auth.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(correo=form.correo.data).first()
        if usuario is not None and account_is_locked(usuario):
            register_failed_login(usuario, "Intento durante bloqueo temporal.")
            flash("Demasiados intentos. Intenta de nuevo en 15 minutos.", "danger")
            return render_template(
                "login.html", form=form, allow_initial_registration=False
            )
        valid_credentials = (
            usuario is not None
            and usuario.activo
            and usuario.check_password(form.contrasena.data)
        )

        if not valid_credentials:
            # El mismo mensaje cubre correo inexistente, contraseña incorrecta
            # y cuenta desactivada para no revelar información sensible.
            locked = register_failed_login(
                usuario,
                "Credenciales inválidas, cuenta inexistente o cuenta inactiva.",
            )
            if locked:
                flash("Demasiados intentos. Intenta de nuevo en 15 minutos.", "danger")
            else:
                flash("Correo, contraseña o estado de cuenta incorrectos.", "danger")
        else:
            target = request.args.get("next")
            clear_failed_logins(usuario)
            if usuario.rol == "admin" and current_app.config["MFA_REQUIRED_FOR_ADMINS"]:
                begin_mfa(usuario, target)
                if not usuario.mfa_secret:
                    usuario.mfa_secret = pyotp.random_base32()
                    add_audit_event(
                        usuario_id=usuario.id,
                        accion="INICIAR_CONFIGURACION_MFA",
                        tabla_afectada="usuarios",
                        registro_id=usuario.id,
                    )
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    session.clear()
                    flash("No fue posible iniciar la verificación MFA.", "danger")
                    return redirect(url_for("auth.login"))
                endpoint = (
                    "auth.mfa_setup"
                    if usuario.mfa_confirmado_en is None
                    else "auth.mfa_verify"
                )
                return redirect(url_for(endpoint))
            return complete_login(usuario)

    allow_initial_registration = Usuario.query.first() is None
    return render_template(
        "login.html",
        form=form,
        allow_initial_registration=allow_initial_registration,
    )


@auth_bp.route("/mfa/configurar", methods=["GET", "POST"])
def mfa_setup():
    """Activa el segundo factor durante el primer acceso administrativo."""

    usuario = pending_mfa_user()
    if usuario is None:
        flash("La verificación MFA venció. Inicia sesión nuevamente.", "warning")
        return redirect(url_for("auth.login"))
    if account_is_locked(usuario):
        session.clear()
        flash("Demasiados intentos. Intenta de nuevo en 15 minutos.", "danger")
        return redirect(url_for("auth.login"))
    if usuario.mfa_confirmado_en is not None:
        return redirect(url_for("auth.mfa_verify"))

    form = MFAForm()
    if form.validate_on_submit():
        valid = form.codigo.data.isdigit() and pyotp.TOTP(usuario.mfa_secret).verify(
            form.codigo.data, valid_window=1
        )
        if not valid:
            locked = register_failed_login(usuario, "Código MFA de configuración inválido.")
            flash(
                "Demasiados intentos. Intenta de nuevo en 15 minutos."
                if locked
                else "El código no es válido o ya venció.",
                "danger",
            )
        else:
            usuario.mfa_confirmado_en = utc_now()
            clear_failed_logins(usuario)
            add_audit_event(
                usuario_id=usuario.id,
                accion="ACTIVAR_MFA",
                tabla_afectada="usuarios",
                registro_id=usuario.id,
            )
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                flash("No fue posible activar MFA. Intenta nuevamente.", "danger")
            else:
                return complete_login(usuario)

    provisioning_uri = pyotp.TOTP(usuario.mfa_secret).provisioning_uri(
        name=usuario.correo,
        issuer_name="BCH Control",
    )
    return render_template(
        "mfa_setup.html",
        form=form,
        secret=usuario.mfa_secret,
        provisioning_uri=provisioning_uri,
    )


@auth_bp.route("/mfa/verificar", methods=["GET", "POST"])
def mfa_verify():
    """Valida el TOTP después de una contraseña administrativa correcta."""

    usuario = pending_mfa_user()
    if usuario is None:
        flash("La verificación MFA venció. Inicia sesión nuevamente.", "warning")
        return redirect(url_for("auth.login"))
    if usuario.mfa_confirmado_en is None:
        return redirect(url_for("auth.mfa_setup"))
    if account_is_locked(usuario):
        session.clear()
        flash("Demasiados intentos. Intenta de nuevo en 15 minutos.", "danger")
        return redirect(url_for("auth.login"))

    form = MFAForm()
    if form.validate_on_submit():
        valid = form.codigo.data.isdigit() and pyotp.TOTP(usuario.mfa_secret).verify(
            form.codigo.data, valid_window=1
        )
        if valid:
            clear_failed_logins(usuario)
            return complete_login(usuario)
        locked = register_failed_login(usuario, "Código MFA de acceso inválido.")
        if locked:
            session.clear()
        flash(
            "Demasiados intentos. Intenta de nuevo en 15 minutos."
            if locked
            else "El código no es válido o ya venció.",
            "danger",
        )

    return render_template("mfa_verify.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Cierra la sesión mediante POST protegido por CSRF."""

    form = LogoutForm()
    if not form.validate_on_submit():
        abort(400)

    usuario_id = current_user.id
    try:
        add_audit_event(
            usuario_id=usuario_id,
            accion="CERRAR_SESION",
            tabla_afectada="usuarios",
            registro_id=usuario_id,
        )
        db.session.commit()
    except SQLAlchemyError:
        # Una falla de bitácora nunca debe impedir que el usuario proteja su
        # cuenta cerrando la sesión.
        db.session.rollback()

    logout_user()
    session.clear()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.post("/obra-activa")
@login_required
def active_project():
    """Cambia la obra operativa del Supervisor sin alterar sus asignaciones."""

    if not current_user.es_supervisor:
        abort(403)
    form = ActiveProjectForm()
    if not form.validate_on_submit():
        abort(400)
    obra = seleccionar_obra_activa(current_user, form.project_id.data)
    if obra is None:
        abort(404)
    try:
        add_audit_event(
            usuario_id=current_user.id,
            accion="CAMBIAR_OBRA_ACTIVA",
            tabla_afectada="centros_costo",
            registro_id=obra.id,
            detalle=f"{obra.codigo} · {obra.nombre}",
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
    target = form.return_to.data
    flash(f"Obra activa: {obra.codigo} · {obra.nombre}.", "success")
    return redirect(
        target
        if is_safe_local_url(target)
        else url_for("auth.dashboard")
    )


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    """Muestra el panel inicial correspondiente a cualquiera de los roles activos."""

    if current_user.es_supervisor:
        if not current_user.tiene_permiso("dashboard_supervisor", "ver"):
            abort(403)
        return redirect(url_for("campo.supervisor_dashboard"))
    if current_user.es_almacenista:
        if not current_user.tiene_permiso("almacen", "ver"):
            abort(403)
        return redirect(url_for("almacen.pendientes"))
    if current_user.es_ceo:
        if not current_user.tiene_permiso("dashboard_ejecutivo", "ver"):
            abort(403)
        return redirect(url_for("ceo.dashboard"))
    if not current_user.tiene_permiso("dashboard_general", "ver"):
        abort(403)
    return render_template("dashboard.html")
