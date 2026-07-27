"""Configuración central de la aplicación ERP V2.

Este módulo no contiene secretos. Todos los valores sensibles se leen desde
variables de entorno o desde un archivo local ``.env`` que nunca deberá
subirse al repositorio.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


# Carga el archivo .env ubicado junto al proyecto cuando se trabaja localmente.
# En producción, Render/Supabase proporcionarán las variables directamente.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


CRITICAL_SECRET_ERROR = (
    "ERROR CRÍTICO: SECRET_KEY no configurada o insegura. Define una clave "
    "aleatoria de al menos 32 caracteres en las variables de entorno."
)
INSECURE_SECRET_MARKERS = (
    "reemplazar",
    "cambia-esto",
    "clave-secreta-para-desarrollo",
    "genera_una_clave",
    "genera-una-clave",
    "tu_clave",
    "tu-clave",
    "secret-key",
    "changeme",
    "example",
    "ejemplo",
)


def validate_secret_key(value: str | None) -> str:
    """Rechaza claves públicas, de ejemplo o demasiado cortas."""

    secret = (value or "").strip()
    lowered = secret.lower()
    if len(secret) < 32 or any(marker in lowered for marker in INSECURE_SECRET_MARKERS):
        raise RuntimeError(CRITICAL_SECRET_ERROR)
    return secret


def required_environment_variable(name: str) -> str:
    """Obtiene una variable obligatoria o detiene el arranque claramente.

    Es preferible fallar al iniciar que levantar el ERP con una clave insegura
    o conectado por accidente a una base distinta.
    """

    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Falta la variable de entorno obligatoria {name}. "
            "Crea tu archivo .env tomando .env.example como referencia."
        )
    return value


def normalize_database_url(database_url: str) -> str:
    """Adapta URLs PostgreSQL al controlador Psycopg 2 instalado.

    Supabase normalmente entrega ``postgresql://``. Al indicar explícitamente
    ``postgresql+psycopg2://`` hacemos que SQLAlchemy use exactamente la
    dependencia ``psycopg2-binary`` declarada en requirements.txt. Las URLs
    SQLite se conservan sin cambios.
    """

    if database_url.startswith("postgres://"):
        return database_url.replace(
            "postgres://", "postgresql+psycopg2://", 1
        )
    if database_url.startswith("postgresql://"):
        return database_url.replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )
    return database_url


ENVIRONMENT = required_environment_variable("FLASK_ENV").lower()
if ENVIRONMENT not in {"development", "production", "testing"}:
    raise RuntimeError(
        "FLASK_ENV debe ser development, production o testing."
    )

DATABASE_URL = normalize_database_url(
    required_environment_variable("DATABASE_URL")
)
if ENVIRONMENT == "production":
    normalized_url = DATABASE_URL.lower()
    if "sqlite" in normalized_url or not normalized_url.startswith(
        "postgresql+psycopg2://"
    ):
        raise RuntimeError(
            "ERROR CRÍTICO: producción requiere PostgreSQL; configura una "
            "DATABASE_URL válida y no uses SQLite."
        )

SECRET_KEY_VALUE = (
    validate_secret_key(os.getenv("SECRET_KEY"))
    if ENVIRONMENT == "production"
    else required_environment_variable("SECRET_KEY")
)


def environment_flag(name: str, default: bool = False) -> bool:
    """Interpreta banderas de entorno sin aceptar valores ambiguos."""

    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


class Config:
    """Valores compartidos por todos los ambientes."""

    SECRET_KEY = SECRET_KEY_VALUE
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Comprueba que una conexión del pool siga viva antes de reutilizarla.
    # Esto será importante al trabajar con PostgreSQL administrado.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Flask renueva el vencimiento de una sesión permanente en cada petición.
    # En la ruta de login se deberá establecer: session.permanent = True.
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_REFRESH_EACH_REQUEST = True

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False

    # Aunque en esta fase no usaremos "recordarme", dejamos protegida cualquier
    # cookie futura creada por Flask-Login.
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = False

    WTF_CSRF_ENABLED = True
    IS_PRODUCTION = False
    MFA_REQUIRED_FOR_ADMINS = True
    MFA_PENDING_LIFETIME = timedelta(minutes=5)
    LOGIN_MAX_FAILED_ATTEMPTS = 5
    LOGIN_ATTEMPT_WINDOW = timedelta(minutes=15)
    LOGIN_LOCKOUT_TIME = timedelta(minutes=15)
    REQUIRE_THREE_WAY_MATCH = True
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024
    FASE5_UPLOAD_FOLDER = os.getenv("FASE5_UPLOAD_FOLDER", "").strip() or None

    # Correo transaccional de Compras mediante Flask-Mail. Las credenciales
    # permanecen únicamente en .env o en las variables del servidor.
    MAIL_SERVER = os.getenv("MAIL_SERVER", "").strip()
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = environment_flag("MAIL_USE_TLS", True)
    MAIL_USE_SSL = environment_flag("MAIL_USE_SSL", False)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "").strip() or None
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "").strip() or None
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "").strip() or None
    MAIL_SUPPRESS_SEND = environment_flag("MAIL_SUPPRESS_SEND", False)


class DevelopmentConfig(Config):
    """Configuración para la computadora del desarrollador."""

    DEBUG = True


class TestingConfig(Config):
    """Configuración destinada a las pruebas automatizadas."""

    TESTING = True
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    MFA_REQUIRED_FOR_ADMINS = False
    # Las regresiones históricas de Compras ejercitan el flujo anterior. Las
    # pruebas específicas de Fase 5 activan esta bandera de forma explícita.
    REQUIRE_THREE_WAY_MATCH = False
    # Flask-Mail exige remitente incluso cuando el transporte está suprimido;
    # este valor existe solo en la base efímera de pruebas.
    MAIL_DEFAULT_SENDER = "compras-pruebas@example.com"


class ProductionConfig(Config):
    """Configuración endurecida para el servidor productivo con HTTPS."""

    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    IS_PRODUCTION = True
    SECRET_KEY = SECRET_KEY_VALUE

    # Reciclar conexiones ayuda frente a cierres de red o del pooler externo.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }


CONFIG_BY_ENVIRONMENT = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config():
    """Devuelve la clase que ``create_app()`` cargará posteriormente."""

    return CONFIG_BY_ENVIRONMENT[ENVIRONMENT]
