"""Marcador de compatibilidad de la Fase 3 cancelada.

Revision ID: 3c7e9a1b2d4f
Revises: f0ddff750d47

La captura semanal simplificada se canceló porque no corresponde al sistema de
nóminas validado en PythonAnywhere. Se conserva el identificador de revisión
para que tanto las bases que ya lo aplicaron como las que no puedan continuar
hacia la integración real sin reescribir su historial de Alembic.
"""

revision = "3c7e9a1b2d4f"
down_revision = "f0ddff750d47"
branch_labels = None
depends_on = None


def upgrade():
    """No crea nuevas tablas; la revisión se conserva por compatibilidad."""

    pass


def downgrade():
    """No borra datos que pudieran existir de una instalación previa."""

    pass

