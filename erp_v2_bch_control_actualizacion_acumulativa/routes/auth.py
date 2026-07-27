"""Rutas de autenticación y dashboard inicial."""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from forms import InitialAdminRegistrationForm, LoginForm, LogoutForm
from models import BitacoraAuditoria, Usuario, db


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


@auth_bp.app_context_processor
def inject_logout_form():
    """Hace disponible el formulario de logout en la barra de navegación."""

    return {"logout_form": LogoutForm()}


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
        valid_credentials = (
            usuario is not None
            and usuario.activo
            and usuario.check_password(form.contrasena.data)
        )

        if not valid_credentials:
            # El mismo mensaje cubre correo inexistente, contraseña incorrecta
            # y cuenta desactivada para no revelar información sensible.
            flash("Correo, contraseña o estado de cuenta incorrectos.", "danger")
        else:
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
                flash(
                    "No fue posible iniciar la sesión de forma segura. Intenta nuevamente.",
                    "danger",
                )
                return render_template(
                    "login.html",
                    form=form,
                    allow_initial_registration=False,
                )

            target = request.args.get("next")
            return redirect(
                target if is_safe_local_url(target) else url_for("auth.dashboard")
            )

    allow_initial_registration = Usuario.query.first() is None
    return render_template(
        "login.html",
        form=form,
        allow_initial_registration=allow_initial_registration,
    )


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


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    """Muestra el panel inicial correspondiente a cualquiera de los roles activos."""

    return render_template("dashboard.html")
