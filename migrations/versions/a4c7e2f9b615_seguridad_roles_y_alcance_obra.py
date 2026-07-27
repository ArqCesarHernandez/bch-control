"""Seguridad de roles y alcance por obra.

Revision ID: a4c7e2f9b615
Revises: e9a3f7c2d614
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa


revision = "a4c7e2f9b615"
down_revision = "e9a3f7c2d614"
branch_labels = None
depends_on = None


def upgrade():
    """Conserva el acceso vigente de compradores al volverlo explícito."""

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO user_projects (user_id, project_id)
            SELECT usuarios.id, centros_costo.id
            FROM usuarios
            CROSS JOIN centros_costo
            WHERE usuarios.rol = 'comprador'
              AND usuarios.activo = :activo
              AND centros_costo.tipo = 'obra'
              AND centros_costo.estado = 'activa'
              AND NOT EXISTS (
                  SELECT 1
                  FROM user_projects asignacion
                  WHERE asignacion.user_id = usuarios.id
                    AND asignacion.project_id = centros_costo.id
              )
            """
        ),
        {"activo": True},
    )


def downgrade():
    # Las asignaciones son datos de autorización ya utilizables por versiones
    # anteriores. No se eliminan al bajar para no borrar asignaciones legítimas
    # que un administrador haya ajustado después de instalar el parche.
    pass

