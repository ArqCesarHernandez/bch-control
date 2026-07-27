"""Actualización operativa de Supervisor, OC, permisos y garantías.

Revision ID: e3a7b9c1d245
Revises: c6d9a4c5880d
Create Date: 2026-07-23

La revisión parte de la Fase 5 vigente. Conserva los documentos históricos,
materializa la primera revisión de cada explosión existente y no sustituye
filas de permisos que ya hayan sido personalizadas.
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "e3a7b9c1d245"
down_revision = "c6d9a4c5880d"
branch_labels = None
depends_on = None


MODULES = (
    "dashboard_general",
    "dashboard_supervisor",
    "dashboard_ejecutivo",
    "nomina_dashboard",
    "nominas_semanales",
    "trabajadores",
    "prestamos",
    "pagos_adicionales",
    "empresas_pago",
    "gastos_oficina",
    "subcontratos",
    "contratistas",
    "reportes_nomina",
    "compras_dashboard",
    "explosion_insumos",
    "insumos",
    "requisiciones",
    "cotizaciones_rfq",
    "licitaciones",
    "oc_compras",
    "oc_operaciones",
    "programacion_pagos",
    "pagos_proveedores",
    "recepcion_materiales",
    "discrepancias_recepcion",
    "almacen",
    "proveedores",
    "proveedores_sensibles",
    "reportes_compras",
    "smnc",
    "garantias",
    "contratos",
    "conciliacion_facturas",
    "tarjetas_credito",
    "metodos_pago",
    "obras_partidas",
    "centros_costo",
    "parte_diario",
    "avance_obra",
    "certificaciones",
    "no_conformidades",
    "rfis",
    "seguridad_obra",
    "usuarios",
    "seguridad",
    "ver_nss_completo",
)

ACTIONS = (
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

LEGACY_PARENTS = {
    "nomina_dashboard": "nomina",
    "nominas_semanales": "nomina",
    "trabajadores": "nomina",
    "prestamos": "nomina",
    "pagos_adicionales": "nomina",
    "empresas_pago": "nomina",
    "gastos_oficina": "nomina",
    "subcontratos": "nomina",
    "contratistas": "nomina",
    "reportes_nomina": "reportes",
    "compras_dashboard": "compras",
    "explosion_insumos": "compras",
    "insumos": "compras",
    "cotizaciones_rfq": "compras",
    "oc_compras": "compras",
    "oc_operaciones": "compras",
    "programacion_pagos": "compras",
    "pagos_proveedores": "compras",
    "metodos_pago": "compras",
    "smnc": "compras",
    "reportes_compras": "reportes",
    "proveedores_sensibles": "proveedores",
    "discrepancias_recepcion": "recepcion_materiales",
    "almacen": "recepcion_materiales",
}


def _set_sqlite_foreign_keys(enabled: bool) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    with op.get_context().autocommit_block():
        bind.exec_driver_sql(
            f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}"
        )


def _role_defaults(role: str) -> dict[str, dict[str, bool]]:
    matrix = {
        module: {action: False for action in ACTIONS}
        for module in MODULES
    }

    def grant(module: str, *actions: str) -> None:
        for action in actions:
            matrix[module][action] = True

    if role == "admin":
        for module in MODULES:
            if module == "ver_nss_completo":
                grant(module, "ver")
            else:
                grant(module, *ACTIONS)
    elif role == "admin_financiero":
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
        grant("tarjetas_credito", *ACTIONS)
        grant("conciliacion_facturas", *ACTIONS)
        grant("contratos", "ver")
        grant("dashboard_ejecutivo", "ver")
        grant("ver_nss_completo", "ver")
    elif role == "capturista":
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
    elif role == "supervisor":
        grant("dashboard_supervisor", "ver")
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
        grant("parte_diario", *ACTIONS)
        grant("avance_obra", *ACTIONS)
        grant("certificaciones", "ver", "crear", "editar", "aprobar")
        grant("no_conformidades", *ACTIONS)
        grant("rfis", *ACTIONS)
        grant("seguridad_obra", *ACTIONS)
    elif role == "comprador":
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
            grant(module, *ACTIONS)
        grant("oc_compras", "emitir", "cancelar")
        grant("obras_partidas", "ver")
        grant("contratos", "ver", "crear", "editar", "eliminar")
        grant("conciliacion_facturas", "ver", "crear", "editar", "conciliar")
        grant("recepcion_materiales", "ver", "crear")
        grant("pagos_proveedores", "ver", "crear", "editar", "pagar")
        grant("programacion_pagos", "ver", "editar")
    elif role == "almacenista":
        grant("almacen", "ver")
        grant("recepcion_materiales", "ver", "crear")
        grant("discrepancias_recepcion", "ver", "crear")
    elif role == "ceo":
        grant("dashboard_ejecutivo", "ver")
    elif role == "costos":
        grant("dashboard_general", "ver")
        grant("reportes_nomina", *ACTIONS)
        grant("reportes_compras", *ACTIONS)
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


def _permission_gate(
    default: bool,
    parent: dict[str, object] | None,
    action: str,
) -> bool:
    """Impide que una fila agrupada revocada vuelva a conceder privilegios."""

    if not default or not parent:
        return default
    source_action = {
        "emitir": "editar",
        "cancelar": "editar",
        "pagar": "crear",
        "conciliar": "editar",
    }.get(action, action)
    return bool(parent.get(f"puede_{source_action}", False))


def _backfill_permissions() -> None:
    bind = op.get_bind()
    users = bind.execute(
        sa.text("SELECT id, rol FROM usuarios ORDER BY id")
    ).mappings().all()
    existing_rows = bind.execute(
        sa.text(
            """
            SELECT usuario_id, modulo, puede_ver, puede_crear, puede_editar,
                   puede_eliminar, puede_aprobar
            FROM permisos
            """
        )
    ).mappings().all()
    by_user: dict[int, dict[str, dict[str, object]]] = {}
    for row in existing_rows:
        by_user.setdefault(row["usuario_id"], {})[row["modulo"]] = dict(row)

    insert_sql = sa.text(
        """
        INSERT INTO permisos
            (usuario_id, modulo, puede_ver, puede_crear, puede_editar,
             puede_eliminar, puede_aprobar, puede_emitir, puede_cancelar,
             puede_pagar, puede_conciliar)
        VALUES
            (:usuario_id, :modulo, :puede_ver, :puede_crear, :puede_editar,
             :puede_eliminar, :puede_aprobar, :puede_emitir, :puede_cancelar,
             :puede_pagar, :puede_conciliar)
        """
    )
    update_new_actions = sa.text(
        """
        UPDATE permisos
        SET puede_emitir = :puede_emitir,
            puede_cancelar = :puede_cancelar,
            puede_pagar = :puede_pagar,
            puede_conciliar = :puede_conciliar
        WHERE usuario_id = :usuario_id AND modulo = :modulo
        """
    )

    for user in users:
        user_id = int(user["id"])
        defaults = _role_defaults(user["rol"])
        rows = by_user.setdefault(user_id, {})
        founder = user_id == 1 and user["rol"] == "admin"
        for module in MODULES:
            parent = rows.get(LEGACY_PARENTS.get(module, ""))
            values = {
                action: (
                    True
                    if founder and module != "ver_nss_completo"
                    else defaults[module][action]
                )
                for action in ACTIONS
            }
            if founder and module == "ver_nss_completo":
                values = {action: action == "ver" for action in ACTIONS}
            if parent and not founder:
                values = {
                    action: _permission_gate(value, parent, action)
                    for action, value in values.items()
                }

            current = rows.get(module)
            if current is None:
                payload = {
                    "usuario_id": user_id,
                    "modulo": module,
                    **{f"puede_{action}": values[action] for action in ACTIONS},
                }
                bind.execute(insert_sql, payload)
                rows[module] = {
                    "usuario_id": user_id,
                    "modulo": module,
                    **payload,
                }
                continue

            # Las acciones CRUD/aprobar ya podían estar personalizadas y no se
            # tocan. Las cuatro acciones nuevas se derivan del rol y de las
            # capacidades que esa misma fila ya conservaba.
            effective = dict(values)
            if not founder:
                effective["emitir"] = bool(
                    values["emitir"]
                    and (
                        current.get("puede_crear")
                        or current.get("puede_editar")
                    )
                )
                effective["cancelar"] = bool(
                    values["cancelar"] and current.get("puede_editar")
                )
                effective["pagar"] = bool(
                    values["pagar"]
                    and (
                        current.get("puede_crear")
                        or current.get("puede_aprobar")
                    )
                )
                effective["conciliar"] = bool(
                    values["conciliar"]
                    and (
                        current.get("puede_editar")
                        or current.get("puede_aprobar")
                    )
                )
            bind.execute(
                update_new_actions,
                {
                    "usuario_id": user_id,
                    "modulo": module,
                    **{
                        f"puede_{action}": effective[action]
                        for action in (
                            "emitir",
                            "cancelar",
                            "pagar",
                            "conciliar",
                        )
                    },
                },
            )


def _backfill_explosion_revisions() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT project_id, MIN(created_by_id) AS loaded_by_id,
                   MIN(created_at) AS loaded_at
            FROM budget_explosion_items
            GROUP BY project_id
            ORDER BY project_id
            """
        )
    ).mappings().all()
    revision_table = sa.table(
        "explosion_revisions",
        sa.column("id", sa.Integer),
        sa.column("project_id", sa.Integer),
        sa.column("numero_revision", sa.Integer),
        sa.column("estado", sa.String),
        sa.column("es_vigente", sa.Boolean),
        sa.column("archivo_origen", sa.String),
        sa.column("observaciones", sa.String),
        sa.column("obra_origen_id", sa.Integer),
        sa.column("loaded_by_id", sa.Integer),
        sa.column("loaded_at", sa.DateTime(timezone=True)),
        sa.column("vigente_desde", sa.DateTime(timezone=True)),
        sa.column("vigente_hasta", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    for row in rows:
        loaded_at = row["loaded_at"] or now
        # Las consultas de texto de SQLite no aplican procesadores de tipo y
        # devuelven MIN(datetime) como cadena. PostgreSQL sí entrega datetime.
        # Normalizamos ambos casos para que la migración sea portable.
        if isinstance(loaded_at, str):
            try:
                loaded_at = datetime.fromisoformat(
                    loaded_at.replace("Z", "+00:00")
                )
            except ValueError:
                loaded_at = now
        if loaded_at.tzinfo is None:
            loaded_at = loaded_at.replace(tzinfo=timezone.utc)
        bind.execute(
            revision_table.insert().values(
                project_id=row["project_id"],
                numero_revision=1,
                estado="VIGENTE",
                es_vigente=True,
                archivo_origen="MIGRACION_FASE5",
                observaciones=(
                    "Explosión histórica vigente al aplicar la actualización "
                    "operativa."
                ),
                obra_origen_id=None,
                loaded_by_id=row["loaded_by_id"],
                loaded_at=loaded_at,
                vigente_desde=loaded_at,
                vigente_hasta=None,
            )
        )
        # No todos los dialectos exponen inserted_primary_key cuando Alembic
        # opera con una tabla liviana; la clave natural es inequívoca.
        revision_id = bind.execute(
            sa.text(
                """
                SELECT id FROM explosion_revisions
                WHERE project_id = :project_id AND numero_revision = 1
                """
            ),
            {"project_id": row["project_id"]},
        ).scalar_one()
        bind.execute(
            sa.text(
                """
                UPDATE budget_explosion_items
                SET revision_id = :revision_id
                WHERE project_id = :project_id
                """
            ),
            {
                "revision_id": revision_id,
                "project_id": row["project_id"],
            },
        )

    bind.execute(
        sa.text(
            """
            UPDATE budget_explosion_items
            SET clasificacion = 'OPERATIVO',
                observacion_clasificacion =
                    'Clasificación heredada del catálogo operativo histórico.'
            WHERE supply_item_id IN (
                SELECT id FROM supply_items WHERE es_operacion = :active
            )
            """
        ),
        {"active": True},
    )


def _backfill_traceability() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE purchase_requisition_lines
            SET requiere_autorizacion_previa = COALESCE(
                (
                    SELECT item.requiere_autorizacion_previa
                    FROM budget_explosion_items AS item
                    WHERE item.id = purchase_requisition_lines.explosion_item_id
                ),
                :disabled
            )
            """
        ),
        {"disabled": False},
    )
    bind.execute(
        sa.text(
            """
            UPDATE purchase_requisition_lines
            SET liberada_at = CURRENT_TIMESTAMP
            WHERE estado_linea = 'APROBADA'
              AND requiere_autorizacion_previa = :disabled
            """
        ),
        {"disabled": False},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO licitacion_lineas
                (licitacion_id, requisicion_linea_id, fecha_liberacion)
            SELECT licitacion.id, line.id, CURRENT_TIMESTAMP
            FROM licitaciones AS licitacion
            JOIN purchase_requisition_lines AS line
              ON line.requisition_id = licitacion.requisicion_id
            WHERE line.estado_linea = 'APROBADA'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE purchase_order_lines
            SET clasificacion_explosion = (
                SELECT item.clasificacion
                FROM budget_explosion_items AS item
                WHERE item.id = purchase_order_lines.explosion_item_id
            )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE purchase_order_lines
            SET smnc_id = (
                SELECT detail.request_id
                FROM material_change_request_lines AS detail
                WHERE detail.generated_explosion_item_id =
                      purchase_order_lines.explosion_item_id
                ORDER BY detail.id
                LIMIT 1
            )
            WHERE EXISTS (
                SELECT 1
                FROM material_change_request_lines AS detail
                WHERE detail.generated_explosion_item_id =
                      purchase_order_lines.explosion_item_id
            )
            """
        )
    )


def upgrade() -> None:
    _set_sqlite_foreign_keys(False)

    with op.batch_alter_table("centros_costo", schema=None) as batch_op:
        batch_op.drop_constraint("ck_centros_costo_tipo", type_="check")
        batch_op.add_column(
            sa.Column("obra_principal_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_centros_costo_obra_principal_id",
            "centros_costo",
            ["obra_principal_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            "ck_centros_costo_tipo",
            "tipo IN ('obra', 'oficina', 'garantia')",
        )
        batch_op.create_check_constraint(
            "ck_centros_costo_garantia_principal",
            "(tipo = 'garantia' AND obra_principal_id IS NOT NULL) OR "
            "(tipo <> 'garantia' AND obra_principal_id IS NULL)",
        )
    op.create_index(
        "ix_centros_costo_obra_principal_id",
        "centros_costo",
        ["obra_principal_id"],
        unique=False,
    )

    op.create_table(
        "explosion_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("numero_revision", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=12),
            server_default="VIGENTE",
            nullable=False,
        ),
        sa.Column(
            "es_vigente",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("archivo_origen", sa.String(length=255), nullable=True),
        sa.Column("observaciones", sa.String(length=500), nullable=True),
        sa.Column("obra_origen_id", sa.Integer(), nullable=True),
        sa.Column("loaded_by_id", sa.Integer(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vigente_desde", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vigente_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "estado IN ('VIGENTE','HISTORICA','CANCELADA')",
            name="ck_explosion_revision_status",
        ),
        sa.ForeignKeyConstraint(
            ["loaded_by_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["obra_origen_id"], ["centros_costo.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["centros_costo.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "numero_revision",
            name="uq_explosion_revision_project_number",
        ),
    )
    op.create_index(
        "ix_explosion_revisions_project_id",
        "explosion_revisions",
        ["project_id"],
    )
    op.create_index(
        "ix_explosion_revisions_estado",
        "explosion_revisions",
        ["estado"],
    )
    op.create_index(
        "ix_explosion_revisions_es_vigente",
        "explosion_revisions",
        ["es_vigente"],
    )
    op.create_index(
        "ix_explosion_revisions_obra_origen_id",
        "explosion_revisions",
        ["obra_origen_id"],
    )

    with op.batch_alter_table("budget_explosion_items", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_explosion_project_budget_supply", type_="unique"
        )
        batch_op.drop_constraint("ck_explosion_source", type_="check")
        batch_op.add_column(sa.Column("revision_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "clasificacion",
                sa.String(length=40),
                server_default="NORMAL",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "requiere_autorizacion_previa",
                sa.Boolean(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "observacion_clasificacion",
                sa.String(length=500),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "source_explosion_item_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_budget_explosion_items_revision_id",
            "explosion_revisions",
            ["revision_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_budget_explosion_items_source_id",
            "budget_explosion_items",
            ["source_explosion_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_explosion_revision_budget_supply",
            ["revision_id", "budget_item_id", "supply_item_id"],
        )
        batch_op.create_check_constraint(
            "ck_explosion_source",
            "origen IN ('EXPLOSION','SMNC','GARANTIA_HISTORICA')",
        )
    op.create_index(
        "ix_budget_explosion_items_revision_id",
        "budget_explosion_items",
        ["revision_id"],
    )
    op.create_index(
        "ix_budget_explosion_items_requiere_autorizacion_previa",
        "budget_explosion_items",
        ["requiere_autorizacion_previa"],
    )
    op.create_index(
        "ix_budget_explosion_items_source_explosion_item_id",
        "budget_explosion_items",
        ["source_explosion_item_id"],
    )
    _backfill_explosion_revisions()

    with op.batch_alter_table(
        "purchase_requisition_lines", schema=None
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "requiere_autorizacion_previa",
                sa.Boolean(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("liberada_at", sa.DateTime(timezone=True), nullable=True)
        )
    op.create_index(
        "ix_purchase_requisition_lines_requiere_autorizacion_previa",
        "purchase_requisition_lines",
        ["requiere_autorizacion_previa"],
    )

    op.create_table(
        "licitacion_lineas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("licitacion_id", sa.Integer(), nullable=False),
        sa.Column("requisicion_linea_id", sa.Integer(), nullable=False),
        sa.Column(
            "fecha_liberacion",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["licitacion_id"], ["licitaciones.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requisicion_linea_id"],
            ["purchase_requisition_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "licitacion_id",
            "requisicion_linea_id",
            name="uq_licitacion_requisicion_linea",
        ),
    )
    op.create_index(
        "ix_licitacion_lineas_licitacion_id",
        "licitacion_lineas",
        ["licitacion_id"],
    )
    op.create_index(
        "ix_licitacion_lineas_requisicion_linea_id",
        "licitacion_lineas",
        ["requisicion_linea_id"],
    )

    with op.batch_alter_table("purchase_orders", schema=None) as batch_op:
        batch_op.drop_constraint("ck_purchase_order_status", type_="check")
        batch_op.drop_constraint(
            "ck_purchase_order_payment_mode", type_="check"
        )
        batch_op.add_column(
            sa.Column(
                "beneficiario_libre",
                sa.String(length=180),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "beneficiario_validado",
                sa.Boolean(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "beneficiario_validado_por_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "beneficiario_validado_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "condicion_saldo",
                sa.String(length=30),
                server_default="CONTRA_RECEPCION",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "anticipo_porcentaje",
                sa.Numeric(precision=7, scale=4),
                server_default="0",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "version_actual",
                sa.Integer(),
                server_default="1",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            )
        )
        batch_op.alter_column(
            "supplier_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.alter_column(
            "company_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.alter_column(
            "payment_method_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.alter_column(
            "modalidad_pago",
            existing_type=sa.String(length=12),
            type_=sa.String(length=24),
            existing_nullable=False,
            existing_server_default=sa.text("'CREDITO'"),
        )
        batch_op.create_foreign_key(
            "fk_purchase_orders_beneficiario_validado_por_id",
            "usuarios",
            ["beneficiario_validado_por_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_purchase_order_status",
            "estado IN ('BORRADOR','PENDIENTE_AUTORIZACION','EMITIDA',"
            "'PENDIENTE_ANTICIPO','ANTICIPO_AUTORIZADO','ANTICIPO_PARCIAL',"
            "'ANTICIPO_PAGADO','RECEPCION_PARCIAL','RECEPCION_TOTAL',"
            "'CERRADA','CANCELADA')",
        )
        batch_op.create_check_constraint(
            "ck_purchase_order_payment_mode",
            "modalidad_pago IN "
            "('CREDITO','ANTICIPO','PAGO_CONTRA_ENTREGA')",
        )
        batch_op.create_check_constraint(
            "ck_purchase_order_balance_condition",
            "condicion_saldo IN "
            "('CONTRA_RECEPCION','CONTRA_ENTREGA_TOTAL')",
        )
        batch_op.create_check_constraint(
            "ck_purchase_order_advance_percentage",
            "anticipo_porcentaje >= 0 AND anticipo_porcentaje <= 100",
        )
    # Los documentos previos ya tenían beneficiario, empresa y método
    # validados en su flujo original. No se bloquean pagos retroactivamente.
    op.execute(
        sa.text(
            """
            UPDATE purchase_orders
            SET beneficiario_validado = :validated
            """
        ).bindparams(validated=True)
    )

    op.create_table(
        "purchase_order_payment_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("secuencia", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=10), nullable=False),
        sa.Column("condicion", sa.String(length=24), nullable=False),
        sa.Column(
            "monto_programado",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column(
            "porcentaje",
            sa.Numeric(precision=7, scale=4),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "estado",
            sa.String(length=24),
            server_default="SOLICITADO",
            nullable=False,
        ),
        sa.Column(
            "monto_pagado",
            sa.Numeric(precision=14, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("solicitado_por_id", sa.Integer(), nullable=False),
        sa.Column("autorizado_por_id", sa.Integer(), nullable=True),
        sa.Column(
            "fecha_solicitud",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "fecha_autorizacion",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("fecha_pago", sa.DateTime(timezone=True), nullable=True),
        sa.Column("justificacion", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('ANTICIPO','SALDO')",
            name="ck_order_payment_schedule_type",
        ),
        sa.CheckConstraint(
            "condicion IN "
            "('SOLICITADO','CONTRA_RECEPCION','CONTRA_ENTREGA_TOTAL')",
            name="ck_order_payment_schedule_condition",
        ),
        sa.CheckConstraint(
            "estado IN ('SOLICITADO','PENDIENTE_RECEPCION','AUTORIZADO',"
            "'PARCIAL','PAGADO','CANCELADO')",
            name="ck_order_payment_schedule_status",
        ),
        sa.CheckConstraint(
            "monto_programado >= 0 AND monto_pagado >= 0 "
            "AND monto_pagado <= monto_programado",
            name="ck_order_payment_schedule_amounts",
        ),
        sa.CheckConstraint(
            "porcentaje >= 0 AND porcentaje <= 100",
            name="ck_order_payment_schedule_percentage",
        ),
        sa.ForeignKeyConstraint(
            ["autorizado_por_id"], ["usuarios.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["purchase_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["solicitado_por_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_id",
            "secuencia",
            name="uq_order_payment_schedule_sequence",
        ),
    )
    op.create_index(
        "ix_purchase_order_payment_schedules_order_id",
        "purchase_order_payment_schedules",
        ["order_id"],
    )
    op.create_index(
        "ix_purchase_order_payment_schedules_estado",
        "purchase_order_payment_schedules",
        ["estado"],
    )

    op.create_table(
        "purchase_order_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("motivo", sa.String(length=500), nullable=False),
        sa.Column("valores_anteriores", sa.JSON(), nullable=False),
        sa.Column("valores_nuevos", sa.JSON(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.CheckConstraint(
            "version > 1", name="ck_purchase_order_revision_version"
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["purchase_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_id",
            "version",
            name="uq_purchase_order_revision_version",
        ),
    )
    op.create_index(
        "ix_purchase_order_revisions_order_id",
        "purchase_order_revisions",
        ["order_id"],
    )

    with op.batch_alter_table("additional_payments", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("payment_schedule_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_additional_payments_payment_schedule_id",
            "purchase_order_payment_schedules",
            ["payment_schedule_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_additional_payments_payment_schedule_id",
        "additional_payments",
        ["payment_schedule_id"],
    )

    op.create_table(
        "garantias_obras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("obra_principal_id", sa.Integer(), nullable=False),
        sa.Column("centro_garantia_id", sa.Integer(), nullable=False),
        sa.Column("supervisor_id", sa.Integer(), nullable=False),
        sa.Column("reportada_por_id", sa.Integer(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("ubicacion", sa.String(length=240), nullable=False),
        sa.Column("motivo", sa.String(length=500), nullable=False),
        sa.Column("evidencia_inicial", sa.String(length=500), nullable=True),
        sa.Column("diagnostico", sa.Text(), nullable=True),
        sa.Column("trabajos_requeridos", sa.Text(), nullable=True),
        sa.Column("accion_correctiva", sa.Text(), nullable=True),
        sa.Column("evidencia_final", sa.String(length=500), nullable=True),
        sa.Column(
            "estado",
            sa.String(length=20),
            server_default="reportada",
            nullable=False,
        ),
        sa.Column("autorizada_por_id", sa.Integer(), nullable=True),
        sa.Column("cerrada_por_id", sa.Integer(), nullable=True),
        sa.Column("rechazada_por_id", sa.Integer(), nullable=True),
        sa.Column("motivo_rechazo", sa.String(length=500), nullable=True),
        sa.Column(
            "fecha_diagnostico",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "fecha_autorizacion",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("fecha_inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fecha_solicitud_cierre",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("fecha_cierre", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fecha_creacion",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "obra_principal_id <> centro_garantia_id",
            name="ck_garantia_centros_distintos",
        ),
        sa.CheckConstraint(
            "estado IN ('reportada','diagnostico','autorizada',"
            "'en_ejecucion','pendiente_cierre','cerrada','rechazada')",
            name="ck_garantia_estado",
        ),
        sa.ForeignKeyConstraint(
            ["autorizada_por_id"], ["usuarios.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["centro_garantia_id"],
            ["centros_costo.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cerrada_por_id"], ["usuarios.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["obra_principal_id"],
            ["centros_costo.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rechazada_por_id"], ["usuarios.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reportada_por_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["supervisor_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("centro_garantia_id"),
    )
    op.create_index(
        "ix_garantias_obras_obra_principal_id",
        "garantias_obras",
        ["obra_principal_id"],
    )
    op.create_index(
        "ix_garantias_obras_supervisor_id",
        "garantias_obras",
        ["supervisor_id"],
    )
    op.create_index(
        "ix_garantias_obras_estado",
        "garantias_obras",
        ["estado"],
    )

    with op.batch_alter_table(
        "material_change_requests", schema=None
    ) as batch_op:
        batch_op.add_column(
            sa.Column("garantia_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_material_change_requests_garantia_id",
            "garantias_obras",
            ["garantia_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_material_change_requests_garantia_id",
        "material_change_requests",
        ["garantia_id"],
    )

    with op.batch_alter_table(
        "material_change_request_lines", schema=None
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "clasificacion",
                sa.String(length=40),
                server_default="NORMAL",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_smnc_classification",
            "clasificacion IN "
            "('NORMAL','OPERATIVO','EQUIPO_ESPECIAL','ELECTRODOMESTICO')",
        )

    with op.batch_alter_table("purchase_order_lines", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "clasificacion_explosion",
                sa.String(length=40),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "observacion_operativa",
                sa.String(length=500),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("smnc_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_purchase_order_lines_smnc_id",
            "material_change_requests",
            ["smnc_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_purchase_order_lines_smnc_id",
        "purchase_order_lines",
        ["smnc_id"],
    )

    with op.batch_alter_table(
        "discrepancias_recepcion", schema=None
    ) as batch_op:
        batch_op.add_column(
            sa.Column("evidencia", sa.String(length=500), nullable=True)
        )

    with op.batch_alter_table("permisos", schema=None) as batch_op:
        for action in ("emitir", "cancelar", "pagar", "conciliar"):
            batch_op.add_column(
                sa.Column(
                    f"puede_{action}",
                    sa.Boolean(),
                    server_default=sa.text("0"),
                    nullable=False,
                )
            )
    _backfill_permissions()
    _backfill_traceability()
    _set_sqlite_foreign_keys(True)


def _assert_downgrade_safe() -> None:
    bind = op.get_bind()
    checks = (
        (
            "SELECT COUNT(*) FROM garantias_obras",
            "Existen garantías; respáldalas y ciérralas antes de regresar a Fase 5.",
        ),
        (
            "SELECT COUNT(*) FROM purchase_order_payment_schedules",
            "Existen programaciones de pago que Fase 5 no puede representar.",
        ),
        (
            "SELECT COUNT(*) FROM purchase_order_revisions",
            "Existen revisiones de OC que Fase 5 no puede representar.",
        ),
        (
            """
            SELECT COUNT(*) FROM purchase_orders
            WHERE supplier_id IS NULL OR company_id IS NULL
               OR payment_method_id IS NULL
               OR modalidad_pago = 'PAGO_CONTRA_ENTREGA'
               OR estado = 'PENDIENTE_AUTORIZACION'
            """,
            "Existen OC del flujo operativo nuevo que Fase 5 no puede representar.",
        ),
        (
            """
            SELECT COUNT(*) FROM (
                SELECT project_id, budget_item_id, supply_item_id
                FROM budget_explosion_items
                GROUP BY project_id, budget_item_id, supply_item_id
                HAVING COUNT(*) > 1
            ) AS duplicados
            """,
            "Existen revisiones múltiples de explosión; no se pueden aplanar sin pérdida.",
        ),
    )
    for sql, message in checks:
        if int(bind.execute(sa.text(sql)).scalar() or 0):
            raise RuntimeError(message)


def downgrade() -> None:
    _assert_downgrade_safe()
    _set_sqlite_foreign_keys(False)

    with op.batch_alter_table("permisos", schema=None) as batch_op:
        for action in ("conciliar", "pagar", "cancelar", "emitir"):
            batch_op.drop_column(f"puede_{action}")

    with op.batch_alter_table(
        "discrepancias_recepcion", schema=None
    ) as batch_op:
        batch_op.drop_column("evidencia")

    op.drop_index(
        "ix_purchase_order_lines_smnc_id",
        table_name="purchase_order_lines",
    )
    with op.batch_alter_table("purchase_order_lines", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_purchase_order_lines_smnc_id", type_="foreignkey"
        )
        batch_op.drop_column("smnc_id")
        batch_op.drop_column("observacion_operativa")
        batch_op.drop_column("clasificacion_explosion")

    with op.batch_alter_table(
        "material_change_request_lines", schema=None
    ) as batch_op:
        batch_op.drop_constraint("ck_smnc_classification", type_="check")
        batch_op.drop_column("clasificacion")

    op.drop_index(
        "ix_material_change_requests_garantia_id",
        table_name="material_change_requests",
    )
    with op.batch_alter_table(
        "material_change_requests", schema=None
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_material_change_requests_garantia_id",
            type_="foreignkey",
        )
        batch_op.drop_column("garantia_id")
    op.drop_index("ix_garantias_obras_estado", table_name="garantias_obras")
    op.drop_index(
        "ix_garantias_obras_supervisor_id", table_name="garantias_obras"
    )
    op.drop_index(
        "ix_garantias_obras_obra_principal_id",
        table_name="garantias_obras",
    )
    op.drop_table("garantias_obras")

    op.drop_index(
        "ix_additional_payments_payment_schedule_id",
        table_name="additional_payments",
    )
    with op.batch_alter_table("additional_payments", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_additional_payments_payment_schedule_id",
            type_="foreignkey",
        )
        batch_op.drop_column("payment_schedule_id")

    op.drop_index(
        "ix_purchase_order_revisions_order_id",
        table_name="purchase_order_revisions",
    )
    op.drop_table("purchase_order_revisions")
    op.drop_index(
        "ix_purchase_order_payment_schedules_estado",
        table_name="purchase_order_payment_schedules",
    )
    op.drop_index(
        "ix_purchase_order_payment_schedules_order_id",
        table_name="purchase_order_payment_schedules",
    )
    op.drop_table("purchase_order_payment_schedules")

    with op.batch_alter_table("purchase_orders", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_purchase_order_advance_percentage", type_="check"
        )
        batch_op.drop_constraint(
            "ck_purchase_order_balance_condition", type_="check"
        )
        batch_op.drop_constraint(
            "ck_purchase_order_payment_mode", type_="check"
        )
        batch_op.drop_constraint("ck_purchase_order_status", type_="check")
        batch_op.drop_constraint(
            "fk_purchase_orders_beneficiario_validado_por_id",
            type_="foreignkey",
        )
        batch_op.alter_column(
            "modalidad_pago",
            existing_type=sa.String(length=24),
            type_=sa.String(length=12),
            existing_nullable=False,
            existing_server_default=sa.text("'CREDITO'"),
        )
        batch_op.alter_column(
            "payment_method_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "company_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "supplier_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.drop_column("updated_at")
        batch_op.drop_column("version_actual")
        batch_op.drop_column("anticipo_porcentaje")
        batch_op.drop_column("condicion_saldo")
        batch_op.drop_column("beneficiario_validado_at")
        batch_op.drop_column("beneficiario_validado_por_id")
        batch_op.drop_column("beneficiario_validado")
        batch_op.drop_column("beneficiario_libre")
        batch_op.create_check_constraint(
            "ck_purchase_order_status",
            "estado IN ('BORRADOR','EMITIDA','PENDIENTE_ANTICIPO',"
            "'ANTICIPO_AUTORIZADO','ANTICIPO_PARCIAL','ANTICIPO_PAGADO',"
            "'RECEPCION_PARCIAL','RECEPCION_TOTAL','CERRADA','CANCELADA')",
        )
        batch_op.create_check_constraint(
            "ck_purchase_order_payment_mode",
            "modalidad_pago IN ('CREDITO','ANTICIPO')",
        )

    op.drop_index(
        "ix_licitacion_lineas_requisicion_linea_id",
        table_name="licitacion_lineas",
    )
    op.drop_index(
        "ix_licitacion_lineas_licitacion_id",
        table_name="licitacion_lineas",
    )
    op.drop_table("licitacion_lineas")

    op.drop_index(
        "ix_purchase_requisition_lines_requiere_autorizacion_previa",
        table_name="purchase_requisition_lines",
    )
    with op.batch_alter_table(
        "purchase_requisition_lines", schema=None
    ) as batch_op:
        batch_op.drop_column("liberada_at")
        batch_op.drop_column("requiere_autorizacion_previa")

    op.drop_index(
        "ix_budget_explosion_items_source_explosion_item_id",
        table_name="budget_explosion_items",
    )
    op.drop_index(
        "ix_budget_explosion_items_requiere_autorizacion_previa",
        table_name="budget_explosion_items",
    )
    op.drop_index(
        "ix_budget_explosion_items_revision_id",
        table_name="budget_explosion_items",
    )
    with op.batch_alter_table("budget_explosion_items", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_explosion_revision_budget_supply", type_="unique"
        )
        batch_op.drop_constraint("ck_explosion_source", type_="check")
        batch_op.drop_constraint(
            "fk_budget_explosion_items_source_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_budget_explosion_items_revision_id", type_="foreignkey"
        )
        batch_op.drop_column("source_explosion_item_id")
        batch_op.drop_column("observacion_clasificacion")
        batch_op.drop_column("requiere_autorizacion_previa")
        batch_op.drop_column("clasificacion")
        batch_op.drop_column("revision_id")
        batch_op.create_unique_constraint(
            "uq_explosion_project_budget_supply",
            ["project_id", "budget_item_id", "supply_item_id"],
        )
        batch_op.create_check_constraint(
            "ck_explosion_source", "origen IN ('EXPLOSION','SMNC')"
        )

    op.drop_index(
        "ix_explosion_revisions_obra_origen_id",
        table_name="explosion_revisions",
    )
    op.drop_index(
        "ix_explosion_revisions_es_vigente",
        table_name="explosion_revisions",
    )
    op.drop_index(
        "ix_explosion_revisions_estado", table_name="explosion_revisions"
    )
    op.drop_index(
        "ix_explosion_revisions_project_id",
        table_name="explosion_revisions",
    )
    op.drop_table("explosion_revisions")

    op.drop_index(
        "ix_centros_costo_obra_principal_id", table_name="centros_costo"
    )
    with op.batch_alter_table("centros_costo", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_centros_costo_garantia_principal", type_="check"
        )
        batch_op.drop_constraint("ck_centros_costo_tipo", type_="check")
        batch_op.drop_constraint(
            "fk_centros_costo_obra_principal_id", type_="foreignkey"
        )
        batch_op.drop_column("obra_principal_id")
        batch_op.create_check_constraint(
            "ck_centros_costo_tipo", "tipo IN ('obra', 'oficina')"
        )

    _set_sqlite_foreign_keys(True)
