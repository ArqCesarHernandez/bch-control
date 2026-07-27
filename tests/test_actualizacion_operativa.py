"""Regresiones de la actualización operativa posterior a Fase 5."""

import os
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

os.environ["FLASK_ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-actualizacion-operativa-secret"

from app import create_app  # noqa: E402
from compras_models import (  # noqa: E402
    BudgetExplosionItem,
    ExplosionRevision,
    GoodsReceipt,
    MaterialChangeRequest,
    MaterialChangeRequestLine,
    PaymentMethod,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderPaymentSchedule,
    PurchaseOrderRevision,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    Supplier,
    SupplyItem,
)
from fase5_models import (  # noqa: E402
    DiscrepanciaRecepcion,
    GarantiaObra,
    Licitacion,
    LicitacionLinea,
)
from models import (  # noqa: E402
    ACCIONES_PERMISO,
    MODULOS_PERMISOS,
    CentroCosto,
    Permiso,
    Usuario,
    db,
)
from nominas_models import (  # noqa: E402
    AdditionalPayment,
    BudgetItem,
    Company,
    Employee,
    Payroll,
    PayrollLine,
)
from services.fase5 import obras_accesibles  # noqa: E402


app = create_app()


class OperationalUpdateTest(unittest.TestCase):
    TODAY = date(2026, 7, 23)

    def setUp(self):
        self.uploads = tempfile.TemporaryDirectory()
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            MFA_REQUIRED_FOR_ADMINS=False,
            MAIL_SUPPRESS_SEND=True,
            REQUIRE_THREE_WAY_MATCH=True,
            FASE5_UPLOAD_FOLDER=self.uploads.name,
            COMPRAS_TODAY=self.TODAY,
        )
        self.client = app.test_client()
        with app.app_context():
            with db.engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                db.metadata.drop_all(bind=connection)
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            db.create_all()

            obra = CentroCosto(
                nombre="Residencia Operativa",
                codigo="OB-OPS",
                tipo="obra",
                estado="activa",
                fecha_apertura=self.TODAY - timedelta(days=90),
                presupuesto_total=500_000,
                presupuesto_mano_obra=90_000,
            )
            sin_explosion = CentroCosto(
                nombre="Residencia sin Explosión",
                codigo="OB-SIN-EXP",
                tipo="obra",
                estado="activa",
                fecha_apertura=self.TODAY - timedelta(days=20),
                presupuesto_total=250_000,
                presupuesto_mano_obra=40_000,
            )
            ajena = CentroCosto(
                nombre="Residencia Ajena",
                codigo="OB-AJENA",
                tipo="obra",
                estado="activa",
                fecha_apertura=self.TODAY - timedelta(days=60),
                presupuesto_total=300_000,
                presupuesto_mano_obra=50_000,
            )
            finalizada = CentroCosto(
                nombre="Residencia Entregada",
                codigo="OB-FIN",
                tipo="obra",
                estado="inactiva",
                fecha_apertura=self.TODAY - timedelta(days=500),
                fecha_cierre=self.TODAY - timedelta(days=40),
                presupuesto_total=800_000,
                presupuesto_mano_obra=160_000,
            )
            db.session.add_all([obra, sin_explosion, ajena, finalizada])
            db.session.flush()

            users = {}
            user_specs = (
                ("admin", "admin-ops@example.com", "Administración Operativa"),
                (
                    "supervisor",
                    "supervisor-ops@example.com",
                    "Supervisión Operativa",
                ),
                ("comprador", "comprador-ops@example.com", "Compras Operativas"),
                ("almacenista", "almacen-ops@example.com", "Almacén Operativo"),
                (
                    "admin_financiero",
                    "finanzas-ops@example.com",
                    "Finanzas Operativas",
                ),
                ("costos", "costos-ops@example.com", "Costos Operativos"),
                ("ceo", "direccion-ops@example.com", "Dirección Operativa"),
            )
            for role, email, name in user_specs:
                user = Usuario(
                    nombre_completo=name,
                    correo=email,
                    rol=role,
                    centro_costo_id=obra.id if role == "supervisor" else None,
                    activo=True,
                )
                user.set_password("ClaveSegura123!")
                user.asignar_permisos_predeterminados()
                if role == "supervisor":
                    user.projects = [obra, sin_explosion, finalizada]
                elif role in {"comprador", "almacenista"}:
                    user.projects = [obra]
                db.session.add(user)
                users[role] = user
            db.session.flush()

            company = Company(codigo="BCH", nombre="Baja Custom Homes")
            method = PaymentMethod(nombre="TRANSFERENCIA", activo=True)
            supplier = Supplier(
                codigo="PROV-OPS",
                nombre="Proveedor de Compras",
                email="proveedor-ops@example.com",
                activo=True,
            )
            db.session.add_all([company, method, supplier])

            budget_ops = BudgetItem(
                project_id=obra.id,
                codigo="OPS-01",
                nombre="Operaciones de campo",
                categoria="ADICIONAL",
                presupuesto=80_000,
                cantidad_objetivo=100,
                unidad_medida="SERV",
            )
            budget_labor = BudgetItem(
                project_id=obra.id,
                codigo="MO-01",
                nombre="Mano de obra presupuestada",
                categoria="MANO_OBRA",
                presupuesto=20_000,
                cantidad_objetivo=100,
                unidad_medida="JOR",
            )
            budget_foreign = BudgetItem(
                project_id=ajena.id,
                codigo="AJ-01",
                nombre="Partida ajena",
                categoria="ADICIONAL",
                presupuesto=30_000,
            )
            budget_finished = BudgetItem(
                project_id=finalizada.id,
                codigo="GAR-01",
                nombre="Acabados históricos",
                categoria="ADICIONAL",
                presupuesto=40_000,
                cantidad_objetivo=100,
                unidad_medida="M2",
                porcentaje_avance_real=37,
            )
            db.session.add_all(
                [budget_ops, budget_labor, budget_foreign, budget_finished]
            )

            operation = SupplyItem(
                clave="OPS-AGUA",
                descripcion="Suministro de agua en pipa",
                tipo="MATERIAL",
                unidad="M3",
                es_operacion=True,
                categoria_operacion="AGUA",
            )
            normal = SupplyItem(
                clave="MAT-NORMAL",
                descripcion="Block normal",
                tipo="MATERIAL",
                unidad="PZA",
            )
            special = SupplyItem(
                clave="EQ-ESPECIAL",
                descripcion="Equipo especial",
                tipo="EQUIPO",
                unidad="PZA",
            )
            labor = SupplyItem(
                clave="MO-CAMPO",
                descripcion="Cuadrilla de campo",
                tipo="MANO_OBRA",
                unidad="JOR",
            )
            foreign_operation = SupplyItem(
                clave="OPS-AJENA",
                descripcion="Operación ajena",
                tipo="MATERIAL",
                unidad="SERV",
                es_operacion=True,
                categoria_operacion="FLETE",
            )
            historical = SupplyItem(
                clave="MAT-HIST",
                descripcion="Material histórico de garantía",
                tipo="MATERIAL",
                unidad="PZA",
            )
            db.session.add_all(
                [
                    operation,
                    normal,
                    special,
                    labor,
                    foreign_operation,
                    historical,
                ]
            )
            db.session.flush()

            old_revision = ExplosionRevision(
                project_id=obra.id,
                numero_revision=1,
                estado="HISTORICA",
                es_vigente=False,
                archivo_origen="explosion-r1.xlsx",
                loaded_by_id=users["admin"].id,
                vigente_hasta=self.TODAY - timedelta(days=1),
            )
            current_revision = ExplosionRevision(
                project_id=obra.id,
                numero_revision=2,
                estado="VIGENTE",
                es_vigente=True,
                archivo_origen="explosion-r2.xlsx",
                loaded_by_id=users["admin"].id,
            )
            foreign_revision = ExplosionRevision(
                project_id=ajena.id,
                numero_revision=1,
                estado="VIGENTE",
                es_vigente=True,
                archivo_origen="explosion-ajena.xlsx",
                loaded_by_id=users["admin"].id,
            )
            historical_revision = ExplosionRevision(
                project_id=finalizada.id,
                numero_revision=3,
                estado="HISTORICA",
                es_vigente=False,
                archivo_origen="explosion-entregada.xlsx",
                loaded_by_id=users["admin"].id,
                vigente_hasta=self.TODAY - timedelta(days=40),
            )
            db.session.add_all(
                [
                    old_revision,
                    current_revision,
                    foreign_revision,
                    historical_revision,
                ]
            )
            db.session.flush()

            old_labor = BudgetExplosionItem(
                revision_id=old_revision.id,
                project_id=obra.id,
                budget_item_id=budget_labor.id,
                supply_item_id=labor.id,
                cantidad_presupuestada=1,
                precio_unitario_sin_iva=1111,
                importe_presupuestado=1111,
                clasificacion="NORMAL",
                activo=False,
                created_by_id=users["admin"].id,
            )
            current_labor = BudgetExplosionItem(
                revision_id=current_revision.id,
                project_id=obra.id,
                budget_item_id=budget_labor.id,
                supply_item_id=labor.id,
                cantidad_presupuestada=1,
                precio_unitario_sin_iva=2555,
                importe_presupuestado=2555,
                clasificacion="NORMAL",
                created_by_id=users["admin"].id,
            )
            operation_entry = BudgetExplosionItem(
                revision_id=current_revision.id,
                project_id=obra.id,
                budget_item_id=budget_ops.id,
                supply_item_id=operation.id,
                cantidad_presupuestada=100,
                precio_unitario_sin_iva=100,
                importe_presupuestado=10_000,
                clasificacion="OPERATIVO",
                observacion_clasificacion="Agua clasificada en explosión vigente.",
                created_by_id=users["admin"].id,
            )
            normal_entry = BudgetExplosionItem(
                revision_id=current_revision.id,
                project_id=obra.id,
                budget_item_id=budget_ops.id,
                supply_item_id=normal.id,
                cantidad_presupuestada=100,
                precio_unitario_sin_iva=20,
                importe_presupuestado=2_000,
                clasificacion="NORMAL",
                created_by_id=users["admin"].id,
            )
            special_entry = BudgetExplosionItem(
                revision_id=current_revision.id,
                project_id=obra.id,
                budget_item_id=budget_ops.id,
                supply_item_id=special.id,
                cantidad_presupuestada=2,
                precio_unitario_sin_iva=2_000,
                importe_presupuestado=4_000,
                clasificacion="EQUIPO_ESPECIAL",
                requiere_autorizacion_previa=True,
                observacion_clasificacion=(
                    "Equipo especial sujeto a autorización previa."
                ),
                created_by_id=users["admin"].id,
            )
            foreign_entry = BudgetExplosionItem(
                revision_id=foreign_revision.id,
                project_id=ajena.id,
                budget_item_id=budget_foreign.id,
                supply_item_id=foreign_operation.id,
                cantidad_presupuestada=10,
                precio_unitario_sin_iva=500,
                importe_presupuestado=5_000,
                clasificacion="OPERATIVO",
                created_by_id=users["admin"].id,
            )
            historical_entry = BudgetExplosionItem(
                revision_id=historical_revision.id,
                project_id=finalizada.id,
                budget_item_id=budget_finished.id,
                supply_item_id=historical.id,
                cantidad_presupuestada=50,
                precio_unitario_sin_iva=100,
                importe_presupuestado=5_000,
                clasificacion="NORMAL",
                activo=False,
                created_by_id=users["admin"].id,
            )
            db.session.add_all(
                [
                    old_labor,
                    current_labor,
                    operation_entry,
                    normal_entry,
                    special_entry,
                    foreign_entry,
                    historical_entry,
                ]
            )
            db.session.commit()

            self.ids = {
                "obra": obra.id,
                "sin_explosion": sin_explosion.id,
                "ajena": ajena.id,
                "finalizada": finalizada.id,
                "admin": users["admin"].id,
                "supervisor": users["supervisor"].id,
                "comprador": users["comprador"].id,
                "almacenista": users["almacenista"].id,
                "finanzas": users["admin_financiero"].id,
                "costos": users["costos"].id,
                "company": company.id,
                "method": method.id,
                "supplier": supplier.id,
                "budget_ops": budget_ops.id,
                "budget_labor": budget_labor.id,
                "budget_foreign": budget_foreign.id,
                "budget_finished": budget_finished.id,
                "revision": current_revision.id,
                "operation": operation_entry.id,
                "normal": normal_entry.id,
                "special": special_entry.id,
                "foreign_entry": foreign_entry.id,
                "historical_entry": historical_entry.id,
            }

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            with db.engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                db.metadata.drop_all(bind=connection)
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        self.uploads.cleanup()

    def login(self, role):
        addresses = {
            "admin": "admin-ops@example.com",
            "supervisor": "supervisor-ops@example.com",
            "comprador": "comprador-ops@example.com",
            "almacenista": "almacen-ops@example.com",
            "finanzas": "finanzas-ops@example.com",
            "costos": "costos-ops@example.com",
            "ceo": "direccion-ops@example.com",
        }
        self.client.post("/logout")
        response = self.client.post(
            "/login",
            data={
                "correo": addresses[role],
                "contrasena": "ClaveSegura123!",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        return response

    def grant_supervisor_emit(self):
        with app.app_context():
            permission = Permiso.query.filter_by(
                usuario_id=self.ids["supervisor"],
                modulo="oc_operaciones",
            ).one()
            permission.puede_emitir = True
            db.session.commit()

    def create_operational_order(
        self,
        *,
        entry_id=None,
        project_id=None,
        observation="Servicio operativo requerido en frente norte.",
        quantity="10",
        price="100",
        advance=None,
        grant_emit=False,
        role="supervisor",
    ):
        if grant_emit:
            self.grant_supervisor_emit()
        self.login(role)
        data = {
            "project_id": str(project_id or self.ids["obra"]),
            "supplier_id": "0",
            "beneficiario_libre": "Operador Independiente del Cabo",
            "fecha_entrega_estimada": "2026-07-24",
            "anticipo_tipo": "MONTO",
            "condicion_saldo": "CONTRA_RECEPCION",
            "lineas-0-explosion_item_id": str(
                entry_id or self.ids["operation"]
            ),
            "lineas-0-cantidad": quantity,
            "lineas-0-precio_unitario_sin_iva": price,
            "lineas-0-observacion": observation,
            "submit": "Guardar y emitir",
        }
        if advance is not None:
            data.update(
                {
                    "requiere_anticipo": "y",
                    "anticipo_monto": str(advance),
                    "justificacion_anticipo": (
                        "El operador requiere movilización previa de maquinaria."
                    ),
                }
            )
        response = self.client.post(
            "/compras/ordenes-operaciones/nueva",
            data=data,
            follow_redirects=True,
        )
        with app.app_context():
            order = PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).first()
            order_id = order.id if order else None
            line_id = order.lines[0].id if order and order.lines else None
        return response, order_id, line_id

    def approve_and_validate_beneficiary(self, order_id):
        self.login("finanzas")
        response = self.client.post(
            f"/compras/ordenes/{order_id}/aprobar-emision",
            follow_redirects=True,
        )
        self.assertIn(
            "aprobada y emitida automáticamente",
            response.get_data(as_text=True),
        )
        response = self.client.post(
            f"/compras/ordenes/{order_id}/validar-beneficiario",
            data={
                "company_id": str(self.ids["company"]),
                "payment_method_id": str(self.ids["method"]),
                "beneficiario_confirmado": "Operador Independiente del Cabo",
                "comentario": "Identidad y cuenta verificadas.",
            },
            follow_redirects=True,
        )
        self.assertIn(
            "Beneficiario validado por Finanzas",
            response.get_data(as_text=True),
        )

    def receive_with_warehouse(
        self,
        order_id,
        line_id,
        *,
        received,
        rejected="0",
        missing="0",
        reason="",
        evidence=None,
    ):
        self.login("almacenista")
        data = {
            "fecha": "2026-07-23",
            "documento_proveedor": "REM-OPS-001",
            "lineas-0-order_line_id": str(line_id),
            "lineas-0-cantidad_recibida": str(received),
            "lineas-0-cantidad_rechazada": str(rejected),
            "lineas-0-cantidad_faltante": str(missing),
            "lineas-0-motivo_discrepancia": reason,
        }
        if evidence:
            data["lineas-0-evidencia_discrepancia"] = evidence
        return self.client.post(
            f"/almacen/ordenes/{order_id}/recibir",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )

    def create_warranty(self):
        self.login("supervisor")
        response = self.client.post(
            "/campo/garantias/nueva",
            data={
                "obra_principal_id": str(self.ids["finalizada"]),
                "supervisor_id": str(self.ids["supervisor"]),
                "descripcion": (
                    "Filtración reportada en la terraza de la obra entregada."
                ),
                "ubicacion": "Terraza principal",
                "motivo": "Posible defecto cubierto por garantía.",
                "evidencia_inicial": (
                    BytesIO(b"evidencia-inicial"),
                    "garantia-inicial.png",
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        with app.app_context():
            warranty = GarantiaObra.query.order_by(
                GarantiaObra.id.desc()
            ).first()
            warranty_id = warranty.id if warranty else None
        return response, warranty_id

    def test_supervisor_dashboard_is_scoped_to_assigned_works(self):
        with app.app_context():
            own = PurchaseRequisition(
                folio="REQ-OPS-VISIBLE",
                project_id=self.ids["obra"],
                fecha_solicitud=self.TODAY,
                fecha_requerida=self.TODAY + timedelta(days=2),
                estado="BORRADOR",
                motivo="Solicitud visible",
                requested_by_id=self.ids["supervisor"],
            )
            foreign = PurchaseRequisition(
                folio="REQ-OPS-OCULTA",
                project_id=self.ids["ajena"],
                fecha_solicitud=self.TODAY,
                fecha_requerida=self.TODAY + timedelta(days=2),
                estado="BORRADOR",
                motivo="Solicitud ajena",
                requested_by_id=self.ids["admin"],
            )
            db.session.add_all([own, foreign])
            own_employee = Employee(
                nombre_completo="Trabajador Visible",
                fecha_ingreso=self.TODAY - timedelta(days=30),
                puesto="OFICIAL",
                project_id=self.ids["obra"],
                salario_semanal=3000,
                empresa_efectivo_id=self.ids["company"],
            )
            foreign_employee = Employee(
                nombre_completo="Trabajador Oculto",
                fecha_ingreso=self.TODAY - timedelta(days=30),
                puesto="OFICIAL",
                project_id=self.ids["ajena"],
                salario_semanal=9000,
                empresa_efectivo_id=self.ids["company"],
            )
            db.session.add_all([own_employee, foreign_employee])
            db.session.flush()
            own_payroll = Payroll(
                project_id=self.ids["obra"],
                semana_inicio=date(2026, 7, 20),
                semana_fin=date(2026, 7, 24),
                estado="aprobada",
                created_by_id=self.ids["admin"],
            )
            foreign_payroll = Payroll(
                project_id=self.ids["ajena"],
                semana_inicio=date(2026, 7, 20),
                semana_fin=date(2026, 7, 24),
                estado="aprobada",
                created_by_id=self.ids["admin"],
            )
            db.session.add_all([own_payroll, foreign_payroll])
            db.session.flush()
            db.session.add_all(
                [
                    PayrollLine(
                        payroll_id=own_payroll.id,
                        employee_id=own_employee.id,
                        partida_id=self.ids["budget_labor"],
                        nombre_trabajador=own_employee.nombre_completo,
                        puesto="OFICIAL",
                        salario_semanal=3000,
                        monto_devengado=3000,
                        pago_extra=250,
                        descuento_imss=150,
                        pago_efectivo=3400,
                        neto_pagar=3250,
                        empresa_efectivo_id=self.ids["company"],
                    ),
                    PayrollLine(
                        payroll_id=foreign_payroll.id,
                        employee_id=foreign_employee.id,
                        partida_id=self.ids["budget_foreign"],
                        nombre_trabajador=foreign_employee.nombre_completo,
                        puesto="OFICIAL",
                        salario_semanal=9000,
                        monto_devengado=9000,
                        pago_extra=0,
                        descuento_imss=900,
                        pago_efectivo=9900,
                        neto_pagar=9000,
                        empresa_efectivo_id=self.ids["company"],
                    ),
                ]
            )
            db.session.commit()

        self.login("supervisor")
        response = self.client.get("/campo/dashboard-supervisor")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("REQ-OPS-VISIBLE", page)
        self.assertNotIn("REQ-OPS-OCULTA", page)
        self.assertNotIn("OB-AJENA", page)
        self.assertIn("Costo de mano de obra por partida", page)
        self.assertIn("MO-01", page)
        self.assertIn("$3,400.00", page)
        self.assertNotIn("AJ-01", page)
        self.assertNotIn("$9,900.00", page)

        switched = self.client.post(
            "/obra-activa",
            data={
                "project_id": str(self.ids["sin_explosion"]),
                "return_to": "/campo/dashboard-supervisor",
            },
            follow_redirects=True,
        ).get_data(as_text=True)
        self.assertIn("OB-SIN-EXP", switched)
        self.assertNotIn("$3,400.00", switched)

    def test_dashboard_uses_only_latest_explosion_budget(self):
        self.login("supervisor")
        page = self.client.get(
            "/campo/dashboard-supervisor"
        ).get_data(as_text=True)
        self.assertIn("Explosión R2", page)
        self.assertIn("2,555.00", page)
        self.assertNotIn("1,111.00", page)
        self.assertNotIn("Sin explosión vigente", page)

        switched = self.client.post(
            "/obra-activa",
            data={
                "project_id": str(self.ids["sin_explosion"]),
                "return_to": "/campo/dashboard-supervisor",
            },
            follow_redirects=True,
        )
        switched_page = switched.get_data(as_text=True)
        self.assertIn("OB-SIN-EXP", switched_page)
        self.assertIn("Sin explosión vigente", switched_page)
        self.assertIn("No se interpreta como presupuesto cero", switched_page)
        self.assertNotIn("Explosión R2", switched_page)

    def test_operational_order_does_not_require_catalog_supplier(self):
        response, order_id, _line_id = self.create_operational_order()
        self.assertIn(
            "guardada y enviada a autorización",
            response.get_data(as_text=True),
        )
        with app.app_context():
            order = db.session.get(PurchaseOrder, order_id)
            self.assertIsNone(order.supplier_id)
            self.assertIsNone(order.company_id)
            self.assertIsNone(order.payment_method_id)
            self.assertEqual(
                order.beneficiario_libre,
                "Operador Independiente del Cabo",
            )
            self.assertEqual(order.tipo_oc, "OPERACIONES")
            self.assertEqual(order.estado, "PENDIENTE_AUTORIZACION")
            self.assertEqual(PurchaseRequisition.query.count(), 0)
            self.assertEqual(order.lines[0].clasificacion_explosion, "OPERATIVO")
            self.assertTrue(order.lines[0].observacion_operativa)
            self.assertEqual(len(order.payment_schedules), 1)
            self.assertEqual(
                order.payment_schedules[0].estado,
                "PENDIENTE_RECEPCION",
            )
            self.assertEqual(AdditionalPayment.query.count(), 0)

    def test_operational_order_requires_classification_and_observation(self):
        response, order_id, _ = self.create_operational_order(observation="")
        self.assertIsNone(order_id)
        self.assertIn(
            "La observación es obligatoria",
            response.get_data(as_text=True),
        )

        response, order_id, _ = self.create_operational_order(
            entry_id=self.ids["normal"],
            observation="Intento con clasificación normal.",
        )
        self.assertIsNone(order_id)
        self.assertIn(
            "no está clasificado como operativo",
            response.get_data(as_text=True),
        )

    def test_non_budget_concept_is_rejected_without_approved_smnc(self):
        with app.app_context():
            supply = SupplyItem(
                clave="OPS-SMNC-SIN-APROBAR",
                descripcion="Flete no contemplado",
                tipo="MATERIAL",
                unidad="SERV",
                es_operacion=True,
                categoria_operacion="FLETE",
            )
            entry = BudgetExplosionItem(
                revision_id=self.ids["revision"],
                project_id=self.ids["obra"],
                budget_item_id=self.ids["budget_ops"],
                supply_item=supply,
                cantidad_presupuestada=5,
                precio_unitario_sin_iva=500,
                importe_presupuestado=2_500,
                clasificacion="OPERATIVO",
                observacion_clasificacion="Pendiente de SMNC.",
                origen="SMNC",
                created_by_id=self.ids["supervisor"],
            )
            db.session.add(entry)
            db.session.commit()
            entry_id = entry.id

        response, order_id, _ = self.create_operational_order(
            entry_id=entry_id,
            observation="Flete requerido por cambio de frente.",
            quantity="2",
        )
        self.assertIsNone(order_id)
        self.assertIn(
            "no tiene una SMNC aprobada",
            response.get_data(as_text=True),
        )

    def test_payment_against_delivery_is_proportional_to_receipt(self):
        _response, order_id, line_id = self.create_operational_order()
        self.approve_and_validate_beneficiary(order_id)

        self.login("finanzas")
        blocked = self.client.post(
            "/compras/pagos/nuevo",
            data={
                "purchase_order_id": str(order_id),
                "order_line_id": str(line_id),
                "fecha": "2026-07-23",
                "monto_capturado": "100",
                "tipo_monto": "SIN_IVA",
                "payment_method_id": str(self.ids["method"]),
                "company_id": str(self.ids["company"]),
                "concepto": "Pago anticipado indebido",
            },
            follow_redirects=True,
        )
        self.assertIn(
            "Selecciona una programación liberada",
            blocked.get_data(as_text=True),
        )
        with app.app_context():
            self.assertEqual(AdditionalPayment.query.count(), 0)

        received = self.receive_with_warehouse(
            order_id,
            line_id,
            received="4",
        )
        self.assertIn(
            "Recepción registrada",
            received.get_data(as_text=True),
        )
        with app.app_context():
            schedule = PurchaseOrderPaymentSchedule.query.filter_by(
                order_id=order_id
            ).one()
            self.assertEqual(schedule.monto_liberado, Decimal("400.00"))
            schedule_id = schedule.id

        self.login("finanzas")
        overpayment = self.client.post(
            "/compras/pagos/nuevo",
            data={
                "purchase_order_id": str(order_id),
                "order_line_id": str(line_id),
                "payment_schedule_id": str(schedule_id),
                "fecha": "2026-07-23",
                "monto_capturado": "401",
                "tipo_monto": "SIN_IVA",
                "payment_method_id": str(self.ids["method"]),
                "company_id": str(self.ids["company"]),
                "concepto": "Intento superior a lo recibido",
            },
            follow_redirects=True,
        )
        self.assertIn(
            "excede el monto liberado",
            overpayment.get_data(as_text=True),
        )
        paid = self.client.post(
            "/compras/pagos/nuevo",
            data={
                "purchase_order_id": str(order_id),
                "order_line_id": str(line_id),
                "payment_schedule_id": str(schedule_id),
                "fecha": "2026-07-23",
                "monto_capturado": "400",
                "tipo_monto": "SIN_IVA",
                "payment_method_id": str(self.ids["method"]),
                "company_id": str(self.ids["company"]),
                "concepto": "Pago proporcional a recepción validada",
            },
            follow_redirects=True,
        )
        self.assertIn("Pago registrado", paid.get_data(as_text=True))
        with app.app_context():
            payment = AdditionalPayment.query.one()
            self.assertEqual(payment.monto_sin_iva, Decimal("400.00"))
            self.assertEqual(payment.payment_schedule_id, schedule_id)

    def test_advance_schedule_and_financial_separation_of_duties(self):
        _response, order_id, line_id = self.create_operational_order(
            advance="200"
        )
        with app.app_context():
            order = db.session.get(PurchaseOrder, order_id)
            schedules = sorted(order.payment_schedules, key=lambda item: item.secuencia)
            self.assertEqual(
                [(item.tipo, item.monto_programado) for item in schedules],
                [
                    ("ANTICIPO", Decimal("200.00")),
                    ("SALDO", Decimal("800.00")),
                ],
            )
            self.assertEqual(schedules[0].estado, "SOLICITADO")
            self.assertEqual(schedules[1].estado, "PENDIENTE_RECEPCION")
            advance_id = schedules[0].id

        self.login("supervisor")
        self.assertEqual(
            self.client.post(
                f"/compras/programacion-pagos/{advance_id}/resolver",
                data={"accion": "AUTORIZAR", "comentario": "Intento indebido"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/compras/pagos/nuevo",
                data={"purchase_order_id": str(order_id)},
            ).status_code,
            403,
        )

        self.approve_and_validate_beneficiary(order_id)
        self.login("finanzas")
        authorized = self.client.post(
            f"/compras/programacion-pagos/{advance_id}/resolver",
            data={
                "accion": "AUTORIZAR",
                "comentario": "Anticipo revisado por Finanzas.",
            },
            follow_redirects=True,
        )
        self.assertIn(
            "todavía no está pagado",
            authorized.get_data(as_text=True),
        )
        with app.app_context():
            self.assertEqual(AdditionalPayment.query.count(), 0)
            self.assertEqual(
                db.session.get(PurchaseOrderPaymentSchedule, advance_id).estado,
                "AUTORIZADO",
            )

        paid = self.client.post(
            "/compras/pagos/nuevo",
            data={
                "purchase_order_id": str(order_id),
                "order_line_id": str(line_id),
                "payment_schedule_id": str(advance_id),
                "fecha": "2026-07-23",
                "monto_capturado": "200",
                "tipo_monto": "SIN_IVA",
                "payment_method_id": str(self.ids["method"]),
                "company_id": str(self.ids["company"]),
                "concepto": "Anticipo autorizado por Finanzas",
            },
            follow_redirects=True,
        )
        self.assertIn("Pago registrado", paid.get_data(as_text=True))
        with app.app_context():
            schedule = db.session.get(PurchaseOrderPaymentSchedule, advance_id)
            self.assertEqual(schedule.estado, "PAGADO")
            self.assertEqual(schedule.monto_pagado, Decimal("200.00"))

    def test_single_submit_emits_when_user_has_emit_permission(self):
        response, order_id, _ = self.create_operational_order(grant_emit=True)
        self.assertIn(
            "guardada y emitida",
            response.get_data(as_text=True),
        )
        with app.app_context():
            order = db.session.get(PurchaseOrder, order_id)
            self.assertEqual(order.estado, "EMITIDA")
            self.assertEqual(order.issued_by_id, self.ids["supervisor"])
            self.assertIsNotNone(order.issued_at)
            self.assertFalse(order.requiere_autorizacion)

    def test_emitted_order_revision_preserves_previous_values(self):
        _response, order_id, line_id = self.create_operational_order(
            grant_emit=True
        )
        with app.app_context():
            issued_at = db.session.get(PurchaseOrder, order_id).issued_at

        self.login("supervisor")
        response = self.client.post(
            f"/compras/ordenes/{order_id}/revision",
            data={
                "version_actual": "1",
                "motivo": "Ajuste confirmado por el operador en sitio.",
                "beneficiario_libre": "Operador Independiente del Cabo",
                "fecha_entrega_estimada": "2026-07-25",
                "notas": "Revisión documentada.",
                "lineas-0-explosion_item_id": str(self.ids["operation"]),
                "lineas-0-cantidad": "12",
                "lineas-0-precio_unitario_sin_iva": "110",
                "lineas-0-observacion": (
                    "Doce viajes confirmados por bitácora de campo."
                ),
            },
            follow_redirects=True,
        )
        self.assertIn(
            "Revisión 2 guardada",
            response.get_data(as_text=True),
        )
        with app.app_context():
            order = db.session.get(PurchaseOrder, order_id)
            revision = PurchaseOrderRevision.query.one()
            self.assertEqual(order.estado, "EMITIDA")
            self.assertEqual(order.version_actual, 2)
            self.assertEqual(order.issued_at, issued_at)
            self.assertEqual(revision.version, 2)
            self.assertEqual(revision.usuario_id, self.ids["supervisor"])
            self.assertEqual(
                Decimal(
                    revision.valores_anteriores["lineas"][0]["cantidad"]
                ),
                Decimal("10"),
            )
            self.assertEqual(
                Decimal(revision.valores_nuevos["lineas"][0]["cantidad"]),
                Decimal("12"),
            )
            self.assertEqual(
                db.session.get(PurchaseOrderLine, line_id).importe_sin_iva,
                Decimal("1320.00"),
            )

    def test_mixed_requisition_releases_only_normal_lines_to_rfq(self):
        self.login("supervisor")
        self.client.post(
            "/compras/requisiciones/nueva",
            data={
                "project_id": str(self.ids["obra"]),
                "tipo_requisicion": "COMPRAS",
                "fecha_requerida": "2026-07-25",
                "motivo": "Materiales mixtos para acabados",
            },
            follow_redirects=True,
        )
        with app.app_context():
            requisition = PurchaseRequisition.query.one()
            requisition_id = requisition.id
        for entry_id, quantity in (
            (self.ids["normal"], "10"),
            (self.ids["special"], "1"),
        ):
            self.client.post(
                f"/compras/requisiciones/{requisition_id}/lineas",
                data={
                    "explosion_item_id": str(entry_id),
                    "cantidad_solicitada": quantity,
                },
                follow_redirects=True,
            )
        self.client.post(
            f"/compras/requisiciones/{requisition_id}/enviar",
            follow_redirects=True,
        )
        with app.app_context():
            requisition = db.session.get(PurchaseRequisition, requisition_id)
            lines = {
                line.explosion_item_id: line for line in requisition.lines
            }
            self.assertEqual(requisition.estado, "PARCIAL")
            self.assertEqual(
                lines[self.ids["normal"]].estado_linea,
                "APROBADA",
            )
            self.assertIsNotNone(lines[self.ids["normal"]].liberada_at)
            self.assertEqual(
                lines[self.ids["special"]].estado_linea,
                "PENDIENTE",
            )
            self.assertTrue(
                lines[self.ids["special"]].requiere_autorizacion_previa
            )
            rfq = Licitacion.query.filter_by(
                requisicion_id=requisition_id
            ).one()
            self.assertEqual(
                [item.requisicion_linea_id for item in rfq.lineas],
                [lines[self.ids["normal"]].id],
            )
            special_line_id = lines[self.ids["special"]].id

        self.login("admin")
        self.client.post(
            f"/compras/requisiciones/{requisition_id}/aprobar",
            data={f"aprobada_{special_line_id}": "1"},
            follow_redirects=True,
        )
        with app.app_context():
            requisition = db.session.get(PurchaseRequisition, requisition_id)
            self.assertEqual(requisition.estado, "APROBADA")
            self.assertEqual(
                LicitacionLinea.query.join(Licitacion)
                .filter(Licitacion.requisicion_id == requisition_id)
                .count(),
                2,
            )

    def test_warehouse_records_partial_receipt_and_two_discrepancies(self):
        _response, order_id, line_id = self.create_operational_order(
            grant_emit=True
        )
        response = self.receive_with_warehouse(
            order_id,
            line_id,
            received="4",
            rejected="1",
            missing="2",
            reason="Un viaje rechazado y dos pendientes de entrega.",
            evidence=(BytesIO(b"evidencia-discrepancia"), "evidencia.png"),
        )
        self.assertIn(
            "Las discrepancias permanecen abiertas",
            response.get_data(as_text=True),
        )
        with app.app_context():
            receipt = GoodsReceipt.query.one()
            discrepancies = DiscrepanciaRecepcion.query.order_by(
                DiscrepanciaRecepcion.tipo
            ).all()
            self.assertEqual(receipt.tipo, "PARCIAL")
            self.assertEqual(
                receipt.lines[0].cantidad_recibida,
                Decimal("4.0000"),
            )
            self.assertEqual(len(discrepancies), 2)
            self.assertEqual(
                {item.tipo: item.cantidad for item in discrepancies},
                {
                    "faltante": Decimal("2.0000"),
                    "rechazado": Decimal("1.0000"),
                },
            )
            self.assertTrue(all(item.evidencia for item in discrepancies))

        page = self.client.get("/almacen/").get_data(as_text=True)
        self.assertNotIn("Precio unitario", page)
        self.assertNotIn("Importe", page)

    def test_warranty_uses_child_cost_center_without_reactivating_main_work(self):
        response, warranty_id = self.create_warranty()
        self.assertIn(
            "sin reactivar la obra principal",
            response.get_data(as_text=True),
        )
        with app.app_context():
            warranty = db.session.get(GarantiaObra, warranty_id)
            main = db.session.get(CentroCosto, self.ids["finalizada"])
            center = warranty.centro_garantia
            source_budget = db.session.get(
                BudgetItem, self.ids["budget_finished"]
            )
            self.assertEqual(main.estado, "inactiva")
            self.assertEqual(source_budget.porcentaje_avance_real, Decimal("37.00"))
            self.assertEqual(center.tipo, "garantia")
            self.assertEqual(center.obra_principal_id, main.id)
            self.assertEqual(center.estado, "activa")
            self.assertEqual(center.presupuesto_total, Decimal("0.00"))
            cloned = BudgetExplosionItem.query.filter_by(
                project_id=center.id
            ).one()
            self.assertEqual(cloned.origen, "GARANTIA_HISTORICA")
            self.assertEqual(cloned.source_explosion_item_id, self.ids["historical_entry"])
            supervisor = db.session.get(Usuario, self.ids["supervisor"])
            normal_work_ids = {
                item.id
                for item in obras_accesibles(
                    supervisor, incluir_inactivas=True
                )
            }
            self.assertNotIn(center.id, normal_work_ids)

    def test_smnc_inside_warranty_keeps_traceability(self):
        _response, warranty_id = self.create_warranty()
        with app.app_context():
            warranty = db.session.get(GarantiaObra, warranty_id)
            center_id = warranty.centro_garantia_id
            budget_id = BudgetItem.query.filter_by(
                project_id=center_id
            ).first().id

        self.login("supervisor")
        response = self.client.post(
            f"/compras/smnc/nueva?garantia_id={warranty_id}",
            data={
                "garantia_id": str(warranty_id),
                "project_id": str(center_id),
                "budget_item_id": str(budget_id),
                "action_type": "NUEVO",
                "clasificacion": "OPERATIVO",
                "supply_key": "OPS-GAR-NUEVO",
                "supply_type": "MATERIAL",
                "descripcion": "Flete operativo no contemplado",
                "unidad": "SERV",
                "cantidad": "2",
                "precio_estimado": "750",
                "justificacion_tipo": "MATERIAL_NO_CONTEMPLADO",
                "justificacion": (
                    "Servicio necesario para ejecutar la corrección de garantía."
                ),
            },
            follow_redirects=True,
        )
        self.assertIn(
            "SMNC enviada a autorización",
            response.get_data(as_text=True),
        )
        with app.app_context():
            smnc = MaterialChangeRequest.query.one()
            self.assertEqual(smnc.garantia_id, warranty_id)
            self.assertEqual(smnc.project_id, center_id)
            smnc_id = smnc.id

        self.login("costos")
        approved = self.client.post(
            f"/compras/smnc/{smnc_id}/aprobar",
            follow_redirects=True,
        )
        self.assertIn(
            "SMNC aprobada",
            approved.get_data(as_text=True),
        )
        with app.app_context():
            smnc = db.session.get(MaterialChangeRequest, smnc_id)
            detail = MaterialChangeRequestLine.query.filter_by(
                request_id=smnc_id
            ).one()
            generated = detail.generated_explosion_item
            self.assertEqual(smnc.estado, "APROBADA")
            self.assertEqual(generated.project_id, center_id)
            self.assertEqual(generated.origen, "SMNC")
            self.assertEqual(generated.clasificacion, "OPERATIVO")
            self.assertEqual(
                db.session.get(
                    CentroCosto, self.ids["finalizada"]
                ).estado,
                "inactiva",
            )

    def test_direct_url_enforces_permission_and_project_scope(self):
        with app.app_context():
            order = PurchaseOrder(
                folio="OCO-AJENA-001",
                project_id=self.ids["ajena"],
                supplier_id=None,
                beneficiario_libre="Beneficiario ajeno",
                company_id=None,
                buyer_id=self.ids["admin"],
                payment_method_id=None,
                fecha_orden=self.TODAY,
                fecha_entrega_estimada=self.TODAY + timedelta(days=1),
                fecha_limite=self.TODAY + timedelta(days=1),
                tipo_oc="OPERACIONES",
                categoria_pago="OPERACIONES",
                estado="EMITIDA",
                modalidad_pago="PAGO_CONTRA_ENTREGA",
                requiere_conciliacion=False,
                created_by_id=self.ids["admin"],
                issued_by_id=self.ids["admin"],
            )
            order.lines.append(
                PurchaseOrderLine(
                    explosion_item_id=self.ids["foreign_entry"],
                    cantidad=1,
                    precio_unitario_sin_iva=500,
                    importe_sin_iva=500,
                    clasificacion_explosion="OPERATIVO",
                    observacion_operativa="Concepto de otra obra.",
                )
            )
            db.session.add(order)
            db.session.commit()
            order_id = order.id

        self.login("supervisor")
        self.assertEqual(
            self.client.get(f"/compras/ordenes/{order_id}").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/compras/ordenes?project_id={self.ids['ajena']}"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/compras/programacion-pagos").status_code,
            403,
        )

        self.login("almacenista")
        self.assertEqual(self.client.get("/compras/").status_code, 403)
        self.assertEqual(
            self.client.get(
                f"/almacen/ordenes/{order_id}/recibir"
            ).status_code,
            404,
        )

    def test_permission_matrix_is_granular_and_individually_enforced(self):
        with app.app_context():
            permissions = Permiso.query.filter_by(
                usuario_id=self.ids["supervisor"]
            ).all()
            self.assertEqual(len(permissions), len(MODULOS_PERMISOS))
            self.assertEqual(
                set(ACCIONES_PERMISO),
                {
                    "ver",
                    "crear",
                    "editar",
                    "eliminar",
                    "aprobar",
                    "emitir",
                    "cancelar",
                    "pagar",
                    "conciliar",
                },
            )
            operation_permission = next(
                item
                for item in permissions
                if item.modulo == "oc_operaciones"
            )
            operation_permission.puede_crear = False
            db.session.commit()

        self.login("supervisor")
        self.assertEqual(
            self.client.get(
                "/compras/ordenes-operaciones/nueva"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/campo/dashboard-supervisor").status_code,
            200,
        )

    def test_supervisor_basic_supplier_cannot_set_sensitive_data(self):
        self.login("supervisor")
        response = self.client.post(
            "/compras/proveedores",
            data={
                "codigo": "PROV-BASICO",
                "nombre": "Proveedor Básico de Campo",
                "email": "basico@example.com",
                "telefono": "624-000-0000",
                "contacto": "Operador de campo",
                # Estos valores manipulados no deben persistirse.
                "rfc": "SEN010101AA1",
                "company_id": str(self.ids["company"]),
                "tiene_credito": "on",
                "limite_credito": "999999",
                "dias_credito": "90",
                "notas": "Dato financiero manipulado.",
            },
            follow_redirects=True,
        )
        self.assertIn(
            "Proveedor registrado",
            response.get_data(as_text=True),
        )
        with app.app_context():
            supplier = Supplier.query.filter_by(codigo="PROV-BASICO").one()
            self.assertIsNone(supplier.rfc)
            self.assertIsNone(supplier.company_id)
            self.assertFalse(supplier.tiene_credito)
            self.assertEqual(supplier.limite_credito, Decimal("0.00"))
            self.assertEqual(supplier.dias_credito, 0)
            self.assertIsNone(supplier.notas)

    def test_buyer_single_button_saves_and_emits(self):
        with app.app_context():
            requisition = PurchaseRequisition(
                folio="REQ-BUY-001",
                project_id=self.ids["obra"],
                fecha_solicitud=self.TODAY,
                fecha_requerida=self.TODAY + timedelta(days=2),
                estado="APROBADA",
                motivo="Compra liberada",
                requested_by_id=self.ids["supervisor"],
                submitted_at=self.TODAY,
                approved_by_id=self.ids["admin"],
                fecha_limite_oc=self.TODAY + timedelta(days=3),
            )
            line = PurchaseRequisitionLine(
                explosion_item_id=self.ids["normal"],
                cantidad_solicitada=5,
                cantidad_aprobada=5,
                estado_linea="APROBADA",
                requiere_autorizacion_previa=False,
            )
            requisition.lines.append(line)
            db.session.add(requisition)
            db.session.commit()
            line_id = line.id

        self.login("comprador")
        response = self.client.post(
            "/compras/ordenes/nueva",
            data={
                "project_id": str(self.ids["obra"]),
                "tipo_oc": "COMPRAS",
                "supplier_id": str(self.ids["supplier"]),
                "company_id": str(self.ids["company"]),
                "payment_method_id": str(self.ids["method"]),
                "modalidad_pago": "CREDITO",
                "fecha_entrega_estimada": "2026-07-25",
                f"cantidad_{line_id}": "5",
                f"precio_{line_id}": "22",
                "guardar_emitir": "1",
            },
            follow_redirects=True,
        )
        self.assertIn(
            "Orden guardada y emitida",
            response.get_data(as_text=True),
        )
        with app.app_context():
            order = PurchaseOrder.query.filter_by(tipo_oc="COMPRAS").one()
            self.assertEqual(order.estado, "EMITIDA")
            self.assertEqual(order.issued_by_id, self.ids["comprador"])
            self.assertIsNotNone(order.issued_at)
            self.assertEqual(order.version_actual, 1)


if __name__ == "__main__":
    unittest.main()
