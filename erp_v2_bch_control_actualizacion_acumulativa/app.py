"""Punto de entrada del ERP V2.

La función ``create_app`` construye y configura una instancia de Flask. Este
patrón permite reutilizar la aplicación en desarrollo, pruebas y producción
sin enlazar las extensiones globales a un solo ambiente.
"""

from __future__ import annotations

import click
from flask import Flask, render_template
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

from config import get_config
from models import Usuario, db

# La importación registra todos los modelos de Compras en el metadata que usa
# Flask-Migrate, incluso antes de que se visite una ruta del módulo.
import compras_models  # noqa: F401, E402


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
    from routes import admin_bp, auth_bp, compras_bp, nominas_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    # El módulo original conserva su token CSRF propio, validado en todas sus
    # acciones POST. Se exenta únicamente este Blueprint para evitar validar el
    # mismo formulario con dos formatos de token distintos.
    csrf.exempt(nominas_bp)
    app.register_blueprint(nominas_bp)
    app.register_blueprint(compras_bp)

    @app.before_request
    def run_purchase_alerts_once_daily():
        """Actualiza alertas al primer acceso diario a cualquier módulo."""

        from routes.compras import run_daily_purchase_alerts

        run_daily_purchase_alerts()

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

    @app.errorhandler(403)
    def forbidden(_error):
        """Presenta una respuesta amigable cuando falta autorización."""

        return render_template("403.html"), 403

    return app


if __name__ == "__main__":
    # Esta alternativa permite ejecutar ``python app.py`` durante desarrollo.
    # Para el flujo normal recomendado se utiliza ``flask run``.
    create_app().run()
