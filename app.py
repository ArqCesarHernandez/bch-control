"""Punto de entrada del ERP V2.

La función ``create_app`` construye y configura una instancia de Flask. Este
patrón permite reutilizar la aplicación en desarrollo, pruebas y producción
sin enlazar las extensiones globales a un solo ambiente.
"""

from __future__ import annotations

import click
from flask import Flask, render_template, request
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from config import get_config
from models import Usuario, db

# La importación registra todos los modelos de Compras en el metadata que usa
# Flask-Migrate, incluso antes de que se visite una ruta del módulo.
import compras_models  # noqa: F401, E402
import fase5_models  # noqa: F401, E402


# Las extensiones se crean una sola vez, sin aplicación asociada. Más adelante
# create_app() las enlaza mediante init_app().
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
mail = Mail()


@login_manager.user_loader
def load_user(user_id: str) -> Usuario | None:
    """Recupera de la base de datos al usuario guardado en la sesión.

    Flask-Login almacena el identificador como texto. Si la cookie contiene un
    valor inválido, se devuelve None y Flask-Login trata la sesión como anónima.
    """

    try:
        numeric_user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    return db.session.get(Usuario, numeric_user_id)


def create_app() -> Flask:
    """Crea la aplicación y registra configuración, extensiones y rutas."""

    app = Flask(__name__)
    app.config.from_object(get_config())
    if app.config.get("IS_PRODUCTION"):
        # Render y otros PaaS terminan TLS en el proxy. Esta capa permite que
        # Flask reconozca correctamente el esquema HTTPS comunicado por él.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Base de datos y migraciones.
    db.init_app(app)
    migrate.init_app(app, db)

    # Protección CSRF global para todos los formularios Flask-WTF.
    csrf.init_app(app)
    mail.init_app(app)

    # Administración de sesiones de usuario.
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Inicia sesión para acceder a esta página."
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"

    # Las importaciones se realizan aquí para evitar ciclos durante el arranque.
    from routes import (
        admin_bp,
        almacen_bp,
        auth_bp,
        campo_bp,
        ceo_bp,
        comprador_fase5_bp,
        compras_bp,
        nominas_bp,
        notificaciones_bp,
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    # Todos los Blueprints, incluido Nóminas, utilizan el mismo token firmado
    # de Flask-WTF. Mantener una sola implementación evita que una plantilla
    # envíe ``_csrf_token`` mientras otra ruta espera ``csrf_token``.
    app.register_blueprint(nominas_bp)
    app.register_blueprint(compras_bp)
    app.register_blueprint(campo_bp)
    app.register_blueprint(comprador_fase5_bp)
    app.register_blueprint(almacen_bp)
    app.register_blueprint(ceo_bp)
    app.register_blueprint(notificaciones_bp)

    @app.before_request
    def run_purchase_alerts_once_daily():
        """Actualiza alertas al primer acceso diario a cualquier módulo."""

        from routes.compras import run_daily_purchase_alerts
        from services.fase5 import run_daily_phase5_alerts

        run_daily_purchase_alerts()
        run_daily_phase5_alerts()

    @app.context_processor
    def inject_global_notifications():
        """Expone el centro de avisos en el shell común del ERP."""

        from flask_login import current_user
        from sqlalchemy.exc import OperationalError

        from compras_models import PurchaseNotification

        if not current_user.is_authenticated:
            return {"system_notifications": [], "system_unread": 0}
        try:
            notifications = (
                PurchaseNotification.query.filter_by(
                    user_id=current_user.id, leida=False
                )
                .order_by(PurchaseNotification.created_at.desc())
                .limit(8)
                .all()
            )
            unread = PurchaseNotification.query.filter_by(
                user_id=current_user.id, leida=False
            ).count()
        except OperationalError:
            db.session.rollback()
            notifications, unread = [], 0
        return {
            "system_notifications": notifications,
            "system_unread": unread,
        }

    @app.after_request
    def add_security_headers(response):
        """Añade defensas del navegador a todas las respuestas del ERP."""

        if app.config.get("IS_PRODUCTION"):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.cli.command("compras-alertas")
    @click.option("--force", is_flag=True, help="Repite la revisión del día actual.")
    def purchase_alerts_command(force: bool):
        """Revisa vencimientos de requisiciones, entregas y pagos."""

        from routes.compras import run_daily_purchase_alerts

        counts = run_daily_purchase_alerts(force=force)
        click.echo(
            "Alertas revisadas: "
            f"{counts['requisitions']} requisiciones, "
            f"{counts['deliveries']} entregas y "
            f"{counts['payments']} pagos, "
            f"{counts['cards']} tarjetas."
        )

    @app.cli.command("fase5-alertas")
    @click.option("--force", is_flag=True, help="Repite la revisión del día actual.")
    def phase5_alerts_command(force: bool):
        """Revisa NCR, certificaciones y licitaciones pendientes."""

        from services.fase5 import run_daily_phase5_alerts

        counts = run_daily_phase5_alerts(force=force)
        click.echo(
            "Alertas Fase 5 revisadas: "
            f"{counts['ncr']} NCR por vencer, "
            f"{counts['certificaciones']} certificaciones pendientes y "
            f"{counts['licitaciones']} licitaciones sin adjudicar."
        )

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        """Registra la causa real sin exponer el token ni datos del formulario."""

        app.logger.warning(
            "Solicitud CSRF rechazada: %s %s (%s)",
            request.method,
            request.path,
            error.description,
        )
        return render_template("400.html"), 400

    @app.errorhandler(403)
    def forbidden(error):
        """Presenta una respuesta amigable cuando falta autorización."""

        custom_message = (
            error.description
            if error.description.startswith(("No puedes", "El administrador"))
            else None
        )
        return render_template("403.html", error_message=custom_message), 403

    return app


if __name__ == "__main__":
    # Esta alternativa permite ejecutar ``python app.py`` durante desarrollo.
    # Para el flujo normal recomendado se utiliza ``flask run``.
    create_app().run()
