"""Importa una base del sistema original hacia el ERP V2 integrado.

El modo predeterminado es una simulación que termina con ROLLBACK. Para aplicar
la importación se requiere ``--apply``; antes de escribir se crea una copia de
seguridad de la base destino. La herramienta solo admite SQLite y se niega a
mezclar dos módulos de nómina que ya contengan movimientos.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path


BUSINESS_TABLES = (
    "budget_items",
    "employees",
    "payrolls",
    "payroll_lines",
    "loans",
    "loan_payments",
    "additional_payments",
    "contractors",
    "subcontracts",
    "subcontract_payments",
    "office_expenses",
    "weekly_resource_availability",
)


def normalized(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        is not None
    )


def columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def require_schema(
    source: sqlite3.Connection, destination: sqlite3.Connection
) -> None:
    source_required = {"users", "projects", "companies", "payrolls"}
    destination_required = {
        "usuarios",
        "centros_costo",
        "companies",
        "payrolls",
        "user_projects",
    }
    missing_source = sorted(
        table for table in source_required if not table_exists(source, table)
    )
    missing_destination = sorted(
        table
        for table in destination_required
        if not table_exists(destination, table)
    )
    if missing_source:
        raise RuntimeError(
            "La base de origen no parece ser la de PythonAnywhere. Faltan: "
            + ", ".join(missing_source)
        )
    if missing_destination:
        raise RuntimeError(
            "Primero ejecuta flask db upgrade en el ERP. Faltan: "
            + ", ".join(missing_destination)
        )


def ensure_empty_payroll(destination: sqlite3.Connection) -> None:
    occupied = []
    for table in BUSINESS_TABLES:
        if table_exists(destination, table):
            count = destination.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]
            if count:
                occupied.append(f"{table} ({count})")
    if occupied:
        raise RuntimeError(
            "El módulo destino ya contiene movimientos. Para evitar duplicados, "
            "la importación fue cancelada: "
            + ", ".join(occupied)
        )


def insert_row(
    destination: sqlite3.Connection, table: str, data: dict
) -> None:
    available = columns(destination, table)
    filtered = {key: value for key, value in data.items() if key in available}
    names = list(filtered)
    placeholders = ", ".join("?" for _ in names)
    quoted = ", ".join(f'"{name}"' for name in names)
    destination.execute(
        f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})',
        [filtered[name] for name in names],
    )


def copy_table(
    source: sqlite3.Connection,
    destination: sqlite3.Connection,
    source_table: str,
    destination_table: str | None = None,
    transform: Callable[[dict], dict] | None = None,
) -> int:
    destination_table = destination_table or source_table
    if not table_exists(source, source_table):
        return 0
    source_columns = columns(source, source_table)
    destination_columns = columns(destination, destination_table)
    shared = source_columns & destination_columns
    copied = 0
    for raw in source.execute(f'SELECT * FROM "{source_table}"'):
        data = {name: raw[name] for name in shared}
        if transform:
            data = transform(data)
        insert_row(destination, destination_table, data)
        copied += 1
    return copied


def import_companies(
    source: sqlite3.Connection, destination: sqlite3.Connection
) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for row in source.execute("SELECT * FROM companies ORDER BY id"):
        existing = destination.execute(
            "SELECT id FROM companies WHERE upper(codigo)=upper(?)", (row["codigo"],)
        ).fetchone()
        if existing:
            destination_id = existing[0]
            destination.execute(
                "UPDATE companies SET nombre=?, activa=? WHERE id=?",
                (row["nombre"], row["activa"], destination_id),
            )
        else:
            cursor = destination.execute(
                "INSERT INTO companies (nombre,codigo,activa) VALUES (?,?,?)",
                (row["nombre"], row["codigo"], row["activa"]),
            )
            destination_id = cursor.lastrowid
        mapping[row["id"]] = destination_id
    return mapping


def import_projects(
    source: sqlite3.Connection, destination: sqlite3.Connection
) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for row in source.execute("SELECT * FROM projects ORDER BY id"):
        existing = destination.execute(
            "SELECT id,codigo FROM centros_costo "
            "WHERE lower(codigo)=lower(?) OR lower(nombre)=lower(?) "
            "ORDER BY CASE WHEN lower(codigo)=lower(?) THEN 0 ELSE 1 END LIMIT 1",
            (row["codigo"], row["nombre"], row["codigo"]),
        ).fetchone()
        project_type = normalized(row["tipo"])
        project_type = "oficina" if project_type == "oficina" else "obra"
        state = "activa" if row["activa"] else "cerrada"
        if existing:
            destination_id = existing["id"]
            code_owner = destination.execute(
                "SELECT id FROM centros_costo WHERE lower(codigo)=lower(?)",
                (row["codigo"],),
            ).fetchone()
            code = row["codigo"] if not code_owner or code_owner[0] == destination_id else existing["codigo"]
            destination.execute(
                "UPDATE centros_costo SET nombre=?, codigo=?, tipo=?, estado=?, "
                "presupuesto_total=?, presupuesto_mano_obra=?, descripcion=? "
                "WHERE id=?",
                (
                    row["nombre"],
                    code,
                    project_type,
                    state,
                    row["presupuesto_total"],
                    row["presupuesto_mano_obra"],
                    row["descripcion"],
                    destination_id,
                ),
            )
        else:
            cursor = destination.execute(
                "INSERT INTO centros_costo "
                "(nombre,codigo,tipo,estado,fecha_apertura,presupuesto_total,"
                "presupuesto_mano_obra,descripcion,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    row["nombre"],
                    row["codigo"],
                    project_type,
                    state,
                    str(row["created_at"] or "")[:10] or None,
                    row["presupuesto_total"],
                    row["presupuesto_mano_obra"],
                    row["descripcion"],
                    row["created_at"],
                ),
            )
            destination_id = cursor.lastrowid
        mapping[row["id"]] = destination_id
    return mapping


def import_users(
    source: sqlite3.Connection,
    destination: sqlite3.Connection,
    project_map: dict[int, int],
) -> dict[int, int]:
    source_assignments: dict[int, list[int]] = {}
    if table_exists(source, "user_projects"):
        for row in source.execute(
            "SELECT user_id,project_id FROM user_projects ORDER BY user_id,project_id"
        ):
            source_assignments.setdefault(row["user_id"], []).append(row["project_id"])

    mapping: dict[int, int] = {}
    for row in source.execute("SELECT * FROM users ORDER BY id"):
        email = normalized(row["email"])
        if not email or "@" not in email:
            email = f"{normalized(row['username']).replace(' ', '.')}@importacion.local"
        existing = destination.execute(
            "SELECT id FROM usuarios WHERE lower(correo)=lower(?)", (email,)
        ).fetchone()
        role = "admin" if row["role"] == "administrador" else "capturista"
        mapped_projects = [
            project_map[value]
            for value in source_assignments.get(row["id"], [])
            if value in project_map
        ]
        primary = mapped_projects[0] if role == "capturista" and mapped_projects else None
        if existing:
            destination_id = existing[0]
            destination.execute(
                "UPDATE usuarios SET nombre_completo=?, rol=?, activo=?, "
                "centro_costo_id=? WHERE id=?",
                (
                    row["nombre_completo"],
                    role,
                    row["activo"],
                    primary,
                    destination_id,
                ),
            )
        else:
            cursor = destination.execute(
                "INSERT INTO usuarios "
                "(nombre_completo,correo,contrasena_hash,rol,centro_costo_id,activo,fecha_alta) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    row["nombre_completo"],
                    email,
                    row["password_hash"],
                    role,
                    primary,
                    row["activo"],
                    row["created_at"],
                ),
            )
            destination_id = cursor.lastrowid
        mapping[row["id"]] = destination_id
        destination.execute(
            "DELETE FROM user_projects WHERE user_id=?", (destination_id,)
        )
        if role == "capturista":
            for project_id in mapped_projects:
                destination.execute(
                    "INSERT OR IGNORE INTO user_projects (user_id,project_id) VALUES (?,?)",
                    (destination_id, project_id),
                )
    return mapping


def import_business_tables(
    source: sqlite3.Connection,
    destination: sqlite3.Connection,
    project_map: dict[int, int],
    user_map: dict[int, int],
    company_map: dict[int, int],
) -> dict[str, int]:
    def mapped(mapping: dict[int, int], value):
        return mapping.get(value) if value is not None else None

    transforms: dict[str, Callable[[dict], dict]] = {
        "budget_items": lambda row: {**row, "project_id": mapped(project_map, row.get("project_id"))},
        "employees": lambda row: {
            **row,
            "project_id": mapped(project_map, row.get("project_id")),
            "empresa_imss_id": mapped(company_map, row.get("empresa_imss_id")),
            "empresa_transferencia_id": mapped(company_map, row.get("empresa_transferencia_id")),
            "empresa_efectivo_id": mapped(company_map, row.get("empresa_efectivo_id")),
        },
        "payrolls": lambda row: {
            **row,
            "project_id": mapped(project_map, row.get("project_id")),
            "created_by_id": mapped(user_map, row.get("created_by_id")),
            "closed_by_id": mapped(user_map, row.get("closed_by_id")),
        },
        "payroll_lines": lambda row: {
            **row,
            "empresa_transferencia_id": mapped(company_map, row.get("empresa_transferencia_id")),
            "empresa_efectivo_id": mapped(company_map, row.get("empresa_efectivo_id")),
        },
        "loans": lambda row: {
            **row,
            "company_id": mapped(company_map, row.get("company_id")),
            "created_by_id": mapped(user_map, row.get("created_by_id")),
        },
        "additional_payments": lambda row: {
            **row,
            "project_id": mapped(project_map, row.get("project_id")),
            "company_id": mapped(company_map, row.get("company_id")),
            "created_by_id": mapped(user_map, row.get("created_by_id")),
        },
        "office_expenses": lambda row: {
            **row,
            "project_id": mapped(project_map, row.get("project_id")),
            "company_id": mapped(company_map, row.get("company_id")),
            "created_by_id": mapped(user_map, row.get("created_by_id")),
        },
        "subcontracts": lambda row: {**row, "project_id": mapped(project_map, row.get("project_id"))},
        "subcontract_payments": lambda row: {
            **row,
            "company_id": mapped(company_map, row.get("company_id")),
            "created_by_id": mapped(user_map, row.get("created_by_id")),
        },
        "weekly_resource_availability": lambda row: {
            **row,
            "updated_by_id": mapped(user_map, row.get("updated_by_id")),
        },
    }
    order = (
        "budget_items",
        "contractors",
        "employees",
        "payrolls",
        "payroll_lines",
        "loans",
        "loan_payments",
        "additional_payments",
        "office_expenses",
        "subcontracts",
        "subcontract_payments",
        "weekly_resource_availability",
    )
    return {
        table: copy_table(
            source,
            destination,
            table,
            transform=transforms.get(table),
        )
        for table in order
    }


def import_audit(
    source: sqlite3.Connection,
    destination: sqlite3.Connection,
    user_map: dict[int, int],
) -> int:
    if not table_exists(source, "audit_logs"):
        return 0
    copied = 0
    for row in source.execute("SELECT * FROM audit_logs ORDER BY id"):
        destination.execute(
            "INSERT INTO bitacora_auditoria "
            "(usuario_id,accion,tabla_afectada,registro_id,fecha_hora,detalle) "
            "VALUES (?,?,?,?,?,?)",
            (
                user_map.get(row["user_id"]),
                row["accion"],
                row["entidad"],
                row["entidad_id"],
                row["created_at"],
                row["detalle"],
            ),
        )
        copied += 1
    return copied


def run(source_path: Path, destination_path: Path, apply: bool) -> Path | None:
    if source_path.resolve() == destination_path.resolve():
        raise RuntimeError("La base de origen y la de destino no pueden ser la misma.")
    if not source_path.is_file() or not destination_path.is_file():
        raise RuntimeError("Verifica que ambas rutas apunten a archivos SQLite existentes.")

    backup = None
    if apply:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = destination_path.with_name(
            f"{destination_path.stem}_respaldo_antes_importacion_{timestamp}{destination_path.suffix}"
        )
        shutil.copy2(destination_path, backup)

    source = sqlite3.connect(
        f"file:{source_path.resolve()}?mode=ro", uri=True
    )
    destination = sqlite3.connect(destination_path)
    source.row_factory = sqlite3.Row
    destination.row_factory = sqlite3.Row
    try:
        require_schema(source, destination)
        ensure_empty_payroll(destination)
        destination.execute("PRAGMA foreign_keys=ON")
        destination.execute("BEGIN IMMEDIATE")
        destination.execute("PRAGMA defer_foreign_keys=ON")

        company_map = import_companies(source, destination)
        project_map = import_projects(source, destination)
        user_map = import_users(source, destination, project_map)
        counts = import_business_tables(
            source, destination, project_map, user_map, company_map
        )
        counts["audit_logs"] = import_audit(source, destination, user_map)

        foreign_key_errors = destination.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise RuntimeError(
                "La validación de llaves foráneas detectó inconsistencias: "
                + str([tuple(row) for row in foreign_key_errors[:10]])
            )

        if apply:
            destination.commit()
            mode = "IMPORTACIÓN APLICADA"
        else:
            destination.rollback()
            mode = "SIMULACIÓN; NO SE GUARDÓ NADA"

        print(mode)
        print(f"Centros vinculados: {len(project_map)}")
        print(f"Usuarios vinculados: {len(user_map)}")
        print(f"Empresas vinculadas: {len(company_map)}")
        for table, count in counts.items():
            print(f"{table}: {count}")
        return backup
    except Exception:
        destination.rollback()
        raise
    finally:
        source.close()
        destination.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa la base SQLite original de PythonAnywhere al ERP V2."
    )
    parser.add_argument("--source", required=True, type=Path, help="nominas.sqlite3 descargada")
    parser.add_argument("--erp-db", required=True, type=Path, help="base SQLite actual del ERP")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica cambios. Sin esta opción solo se simula y se revierte.",
    )
    arguments = parser.parse_args()
    try:
        backup = run(arguments.source, arguments.erp_db, arguments.apply)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if backup:
        print(f"Respaldo creado: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

