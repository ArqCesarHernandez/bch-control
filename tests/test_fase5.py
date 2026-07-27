"""Pruebas integrales de Roles Ampliados y Funcionalidades de Campo."""

import os
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

os.environ["FLASK_ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-fase5-secret"

from app import create_app  # noqa: E402
from compras_models import (  # noqa: E402
    BudgetExplosionItem,
    GoodsReceipt,
    GoodsReceiptLine,
    PaymentMethod,
    PurchaseNotification,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    Supplier,
    SupplyItem,
)
from fase5_models import (  # noqa: E402
    AvancePartida,
    CertificacionSubcontrato,
    ConciliacionFactura,
    Contrato,
    DiscrepanciaRecepcion,
    Licitacion,
    NoConformidad,
    Oferta,
    ParteDiario,
    RFI,
    RFIEvento,
)
from models import CentroCosto, Usuario, db  # noqa: E402
from nominas_models import (  # noqa: E402
    BudgetItem,
    Company,
    Contractor,
    Subcontract,
    SubcontractPayment,
)
from services.fase5 import conciliacion_aprobada_para_pago  # noqa: E402


app = create_app()


class Phase5FlowTest(unittest.TestCase):
    def setUp(self):
        self.uploads = tempfile.TemporaryDirectory()
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            MFA_REQUIRED_FOR_ADMINS=False,
            MAIL_SUPPRESS_SEND=True,
            REQUIRE_THREE_WAY_MATCH=True,
            FASE5_UPLOAD_FOLDER=self.uploads.name,
            COMPRAS_TODAY=date.today(),
        )
        self.client = app.test_client()
        with app.app_context():
            db.drop_all()
            db.create_all()

            obra = CentroCosto(
                nombre="Residencia Fase 5",
                codigo="OB-F5",
                tipo="obra",
                estado="activa",
                fecha_apertura=date.today() - timedelta(days=60),
                presupuesto_total=500_000,
                presupuesto_mano_obra=120_000,
            )
            otra_obra = CentroCosto(
                nombre="Obra sin acceso",
                codigo="OB-AJENA",
                tipo="obra",
                estado="activa",
                fecha_apertura=date.today() - timedelta(days=30),
                presupuesto_total=200_000,
                presupuesto_mano_obra=50_000,
            )
            db.session.add_all([obra, otra_obra])
            db.session.flush()

            users = {}
            for role, email, name in (
                ("admin", "admin-f5@example.com", "Administración BCH"),
                ("supervisor", "supervisor-f5@example.com", "Residente Fase 5"),
                ("comprador", "comprador-f5@example.com", "Compras Fase 5"),
                ("almacenista", "almacen-f5@example.com", "Almacén Fase 5"),
                ("ceo", "direccion-f5@example.com", "Dirección BCH"),
            ):
                user = Usuario(
                    nombre_completo=name,
                    correo=email,
                    rol=role,
                    centro_costo_id=obra.id if role == "supervisor" else None,
                    activo=True,
                )
                user.set_password("ClaveSegura123!")
                user.asignar_permisos_predeterminados()
                if role in {"supervisor", "comprador", "almacenista"}:
                    user.projects = [obra]
                db.session.add(user)
                users[role] = user
            db.session.flush()

            company = Company(codigo="BCH", nombre="Baja Custom Homes")
            method = PaymentMethod(nombre="TRANSFERENCIA", activo=True)
            supplier = Supplier(
                codigo="PROV-F5",
                nombre="Materiales del Pacífico",
                email="proveedor@example.com",
                activo=True,
            )
            budget = BudgetItem(
                project_id=obra.id,
                codigo="EST-01",
                nombre="Estructura",
                categoria="SUBCONTRATO",
                presupuesto=100_000,
                cantidad_objetivo=100,
                unidad_medida="M2",
            )
            supply = SupplyItem(
                clave="ACERO-F5",
                descripcion="Acero de refuerzo",
                tipo="MATERIAL",
                unidad="KG",
            )
            contractor = Contractor(
                nombre="Estructuras del Mar", especialidad="Estructura"
            )
            db.session.add_all(
                [company, method, supplier, budget, supply, contractor]
            )
            db.session.flush()

            explosion = BudgetExplosionItem(
                project_id=obra.id,
                budget_item_id=budget.id,
                supply_item_id=supply.id,
                cantidad_presupuestada=10,
                precio_unitario_sin_iva=100,
                importe_presupuestado=1_000,
                created_by_id=users["admin"].id,
            )
            subcontract = Subcontract(
                project_id=obra.id,
                budget_item_id=budget.id,
                contractor_id=contractor.id,
                especialidad="Estructura",
                presupuesto_sin_iva=10_000,
                avance_fisico=Decimal("0.50"),
            )
            db.session.add_all([explosion, subcontract])
            db.session.flush()

            order = PurchaseOrder(
                folio="OC-F5-0001",
                project_id=obra.id,
                supplier_id=supplier.id,
                company_id=company.id,
                buyer_id=users["comprador"].id,
                payment_method_id=method.id,
                fecha_orden=date.today(),
                fecha_entrega_estimada=date.today() + timedelta(days=7),
                fecha_limite=date.today() + timedelta(days=14),
                tipo_oc="COMPRAS",
                categoria_pago="COMPRAS",
                estado="EMITIDA",
                modalidad_pago="CREDITO",
                requiere_conciliacion=True,
                created_by_id=users["comprador"].id,
                issued_by_id=users["comprador"].id,
            )
            db.session.add(order)
            db.session.flush()
            order_line = PurchaseOrderLine(
                order_id=order.id,
                explosion_item_id=explosion.id,
                cantidad=10,
                precio_unitario_sin_iva=100,
                importe_sin_iva=1_000,
            )
            db.session.add(order_line)
            db.session.commit()

            self.ids = {
                "obra": obra.id,
                "otra_obra": otra_obra.id,
                "admin": users["admin"].id,
                "supervisor": users["supervisor"].id,
                "comprador": users["comprador"].id,
                "almacenista": users["almacenista"].id,
                "ceo": users["ceo"].id,
                "company": company.id,
                "method": method.id,
                "supplier": supplier.id,
                "budget": budget.id,
                "explosion": explosion.id,
                "subcontract": subcontract.id,
                "order": order.id,
                "order_line": order_line.id,
            }

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()
        self.uploads.cleanup()

    def login(self, role):
        self.client.post("/logout")
        return self.client.post(
            "/login",
            data={
                "correo": f"{role}-f5@example.com"
                if role != "admin"
                else "admin-f5@example.com",
                "contrasena": "ClaveSegura123!",
            },
            follow_redirects=True,
        )

    def test_daily_log_is_mobile_ready_and_scoped_to_assigned_project(self):
        self.login("supervisor")
        response = self.client.post(
            "/campo/partes-diarios/nuevo",
            data={
                "centro_costo_id": self.ids["obra"],
                "fecha": date.today().isoformat(),
                "personal_total": "18",
                "horas_trabajadas": "144",
                "equipos_utilizados": "Grúa y vibrador",
                "condiciones_meteorologicas": "Soleado",
                "visitas": "Dirección de obra",
                "incidencias": "Sin incidentes",
                "observaciones": "Colado concluido",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Parte diario guardado correctamente", response.get_data(as_text=True))
        with app.app_context():
            part = ParteDiario.query.one()
            self.assertEqual(part.personal_total, 18)
            self.assertEqual(part.centro_costo_id, self.ids["obra"])

        denied = self.client.post(
            "/campo/partes-diarios/nuevo",
            data={
                "centro_costo_id": self.ids["otra_obra"],
                "fecha": (date.today() + timedelta(days=1)).isoformat(),
                "personal_total": "1",
                "horas_trabajadas": "8",
            },
        )
        self.assertEqual(denied.status_code, 404)

    def test_progress_measurement_recalculates_budget_and_subcontract(self):
        self.login("supervisor")
        response = self.client.post(
            "/campo/avances/nuevo",
            data={
                "partida_id": self.ids["budget"],
                "fecha": date.today().isoformat(),
                "cantidad_ejecutada": "25",
                "unidad": "M2",
                "observaciones": "Medición validada en sitio",
            },
            follow_redirects=True,
        )
        self.assertIn("La partida quedó en 25.00%", response.get_data(as_text=True))
        with app.app_context():
            self.assertEqual(AvancePartida.query.count(), 1)
            budget = db.session.get(BudgetItem, self.ids["budget"])
            subcontract = db.session.get(Subcontract, self.ids["subcontract"])
            self.assertEqual(budget.porcentaje_avance_real, Decimal("25.00"))
            self.assertEqual(subcontract.avance_fisico, Decimal("0.2500"))

    def test_ncr_requires_corrective_action_and_closing_evidence(self):
        self.login("supervisor")
        response = self.client.post(
            "/campo/no-conformidades/nueva",
            data={
                "centro_costo_id": str(self.ids["obra"]),
                "descripcion": "Anclaje fuera de tolerancia",
                "ubicacion": "Eje B-4",
                "severidad": "grave",
                "responsable": "Subcontratista estructura",
                "fecha_deteccion": date.today().isoformat(),
                "fecha_limite": (date.today() + timedelta(days=2)).isoformat(),
                "estado": "abierta",
                "evidencia_foto": (BytesIO(b"evidencia apertura"), "apertura.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("No conformidad guardada", response.get_data(as_text=True))
        with app.app_context():
            ncr = NoConformidad.query.one()
            ncr_id = ncr.id
            self.assertEqual(ncr.semaforo(date.today()), "rojo")
            self.assertTrue(ncr.evidencia_foto)

        invalid = self.client.post(
            f"/campo/no-conformidades/{ncr_id}/cerrar",
            data={"accion_correctiva": ""},
            follow_redirects=True,
        )
        self.assertIn(
            "La acción correctiva y la evidencia son obligatorias",
            invalid.get_data(as_text=True),
        )
        response = self.client.post(
            f"/campo/no-conformidades/{ncr_id}/cerrar",
            data={
                "accion_correctiva": "Se repuso y verificó el anclaje.",
                "evidencia_cierre": (BytesIO(b"evidencia cierre"), "cierre.jpg"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("No conformidad cerrada con evidencia", response.get_data(as_text=True))
        with app.app_context():
            ncr = db.session.get(NoConformidad, ncr_id)
            self.assertEqual(ncr.estado, "cerrada")
            self.assertTrue(ncr.evidencia_cierre)
            self.assertEqual(ncr.usuario_resuelve_id, self.ids["supervisor"])

    def test_rfi_notifies_recipient_and_keeps_complete_trace(self):
        self.login("supervisor")
        response = self.client.post(
            "/campo/rfis/nueva",
            data={
                "centro_costo_id": self.ids["obra"],
                "destinatario_id": self.ids["admin"],
                "asunto": "Detalle de impermeabilización",
                "descripcion": "Confirmar traslape mínimo en pretil.",
            },
            follow_redirects=True,
        )
        self.assertIn("RFI enviada y destinatario notificado", response.get_data(as_text=True))
        with app.app_context():
            rfi = RFI.query.one()
            rfi_id = rfi.id
            notification = PurchaseNotification.query.filter_by(
                user_id=self.ids["admin"], tipo="NUEVA_RFI"
            ).one()
            self.assertIn(str(rfi_id), notification.mensaje)
            self.assertEqual(RFIEvento.query.filter_by(rfi_id=rfi_id).count(), 1)

        self.login("admin")
        response = self.client.post(
            f"/campo/rfis/{rfi_id}/responder",
            data={"respuesta": "Usar traslape mínimo de 20 cm."},
            follow_redirects=True,
        )
        self.assertIn("Respuesta guardada y solicitante notificado", response.get_data(as_text=True))
        with app.app_context():
            rfi = db.session.get(RFI, rfi_id)
            self.assertEqual(rfi.estado, "respondida")
            self.assertEqual(RFIEvento.query.filter_by(rfi_id=rfi_id).count(), 2)
            self.assertEqual(rfi.usuario_responde_id, self.ids["admin"])

    def test_subcontract_certification_creates_payment_only_after_approval(self):
        self.login("supervisor")
        response = self.client.post(
            "/campo/certificaciones/nueva",
            data={
                "subcontrato_id": self.ids["subcontract"],
                "fecha_solicitud": date.today().isoformat(),
                "monto_solicitado": "3000",
                "concepto": "Estimación 01 estructura",
            },
            follow_redirects=True,
        )
        self.assertIn("Solicitud enviada para certificación", response.get_data(as_text=True))
        with app.app_context():
            certification = CertificacionSubcontrato.query.one()
            certification_id = certification.id
            self.assertEqual(SubcontractPayment.query.count(), 0)

        response = self.client.post(
            f"/campo/certificaciones/{certification_id}/resolver",
            data={
                "decision": "aprobar",
                "monto_aprobado": "3000",
                "company_id": self.ids["company"],
                "payment_method_id": self.ids["method"],
                "comentario": "Validado contra avance real.",
            },
            follow_redirects=True,
        )
        self.assertIn("Certificación aprobada", response.get_data(as_text=True))
        with app.app_context():
            certification = db.session.get(
                CertificacionSubcontrato, certification_id
            )
            payment = SubcontractPayment.query.one()
            self.assertEqual(certification.estado, "aprobada")
            self.assertEqual(certification.pago_generado_id, payment.id)
            self.assertEqual(payment.monto_sin_iva, Decimal("3000.00"))

    def test_three_way_reconciliation_blocks_difference_then_releases_exact_match(self):
        with app.app_context():
            receipt = GoodsReceipt(
                folio="REC-F5-0001",
                order_id=self.ids["order"],
                fecha=date.today(),
                tipo="PARCIAL",
                received_by_id=self.ids["almacenista"],
            )
            receipt.lines.append(
                GoodsReceiptLine(
                    order_line_id=self.ids["order_line"], cantidad_recibida=5
                )
            )
            db.session.add(receipt)
            db.session.commit()

        self.login("comprador")
        response = self.client.post(
            "/compras/conciliaciones/nueva",
            data={
                "orden_compra_id": self.ids["order"],
                "factura_numero": "FAC-100",
                "fecha_factura": date.today().isoformat(),
                "monto_factura": "1000",
                "motivo_diferencia": "Entrega parcial pendiente.",
            },
            follow_redirects=True,
        )
        self.assertIn("el pago permanece bloqueado", response.get_data(as_text=True))
        with app.app_context():
            conciliation = ConciliacionFactura.query.one()
            conciliation_id = conciliation.id
            order = db.session.get(PurchaseOrder, self.ids["order"])
            self.assertEqual(conciliation.estado, "pendiente")
            self.assertFalse(conciliacion_aprobada_para_pago(order))

            receipt = GoodsReceipt(
                folio="REC-F5-0002",
                order_id=self.ids["order"],
                fecha=date.today(),
                tipo="TOTAL",
                received_by_id=self.ids["almacenista"],
            )
            receipt.lines.append(
                GoodsReceiptLine(
                    order_line_id=self.ids["order_line"], cantidad_recibida=5
                )
            )
            db.session.add(receipt)
            db.session.commit()

        response = self.client.post(
            f"/compras/conciliaciones/{conciliation_id}/editar",
            data={
                "orden_compra_id": self.ids["order"],
                "factura_numero": "FAC-100",
                "fecha_factura": date.today().isoformat(),
                "monto_factura": "1000",
                "motivo_diferencia": "",
            },
            follow_redirects=True,
        )
        self.assertIn("Factura conciliada y liberada para pago", response.get_data(as_text=True))
        with app.app_context():
            conciliation = db.session.get(ConciliacionFactura, conciliation_id)
            order = db.session.get(PurchaseOrder, self.ids["order"])
            self.assertEqual(conciliation.estado, "aprobada")
            self.assertTrue(conciliacion_aprobada_para_pago(order))

    def test_rfq_matrix_and_award_generate_versioned_contract(self):
        with app.app_context():
            requisition = PurchaseRequisition(
                folio="REQ-F5-0001",
                project_id=self.ids["obra"],
                fecha_solicitud=date.today(),
                fecha_requerida=date.today() + timedelta(days=15),
                tipo_requisicion="COMPRAS",
                estado="APROBADA",
                motivo="Adquisición de acero",
                requested_by_id=self.ids["supervisor"],
                approved_by_id=self.ids["admin"],
                fecha_limite_oc=date.today() + timedelta(days=20),
            )
            requisition.lines.append(
                PurchaseRequisitionLine(
                    explosion_item_id=self.ids["explosion"],
                    cantidad_solicitada=10,
                    cantidad_aprobada=10,
                    estado_linea="APROBADA",
                )
            )
            db.session.add(requisition)
            db.session.commit()
            requisition_id = requisition.id

        self.login("comprador")
        response = self.client.post(
            "/compras/licitaciones/nueva",
            data={
                "requisicion_id": requisition_id,
                "fecha_limite": (date.today() + timedelta(days=5)).isoformat(),
                "proveedor_ids": str(self.ids["supplier"]),
            },
            follow_redirects=True,
        )
        self.assertIn("Licitación creada en preparación", response.get_data(as_text=True))
        with app.app_context():
            tender = Licitacion.query.one()
            tender_id = tender.id

        response = self.client.post(
            f"/compras/licitaciones/{tender_id}/enviar",
            data={},
            follow_redirects=True,
        )
        self.assertIn("RFQ enviada a 1 proveedor", response.get_data(as_text=True))
        response = self.client.post(
            f"/compras/licitaciones/{tender_id}/ofertas/nueva",
            data={
                "proveedor_id": self.ids["supplier"],
                "monto_total": "1250",
                "plazo_entrega": "12",
                "condiciones": "50% anticipo y 50% contra entrega.",
            },
            follow_redirects=True,
        )
        self.assertIn("Oferta registrada en la matriz comparativa", response.get_data(as_text=True))
        response = self.client.post(
            f"/compras/licitaciones/{tender_id}/cerrar",
            data={},
            follow_redirects=True,
        )
        self.assertIn("Licitación cerrada", response.get_data(as_text=True))
        with app.app_context():
            offer = Oferta.query.one()
            offer_id = offer.id

        response = self.client.post(
            f"/compras/licitaciones/{tender_id}/ofertas/{offer_id}/adjudicar",
            data={
                "destino": "contrato",
                "tipo_contrato": "suma_alzada",
                "fecha_inicio": date.today().isoformat(),
                "fecha_fin": (date.today() + timedelta(days=12)).isoformat(),
                "condiciones_pago": "50% anticipo y 50% contra entrega.",
                "retencion_garantia": "5",
            },
            follow_redirects=True,
        )
        self.assertIn("Oferta adjudicada", response.get_data(as_text=True))
        with app.app_context():
            contract = Contrato.query.one()
            offer = db.session.get(Oferta, offer_id)
            self.assertEqual(contract.monto_total, Decimal("1250.00"))
            self.assertEqual(contract.version_actual, 1)
            self.assertEqual(contract.oferta_id, offer_id)
            self.assertEqual(offer.resultado_tipo, "contrato")
            self.assertEqual(offer.resultado_id, contract.id)

    def test_warehouse_receipt_records_rejected_and_missing_material(self):
        self.login("almacen")
        response = self.client.post(
            f"/almacen/ordenes/{self.ids['order']}/recibir",
            data={
                "fecha": date.today().isoformat(),
                "documento_proveedor": "REM-55",
                "notas": "Entrega revisada en sitio",
                "lineas-0-order_line_id": self.ids["order_line"],
                "lineas-0-cantidad_recibida": "8",
                "lineas-0-cantidad_rechazada": "1",
                "lineas-0-cantidad_faltante": "1",
                "lineas-0-motivo_discrepancia": "Una pieza dañada y una faltante.",
                "lineas-0-evidencia_discrepancia": (
                    BytesIO(b"evidencia-fase-5"),
                    "discrepancia.jpg",
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("Recepción registrada y comprador notificado", response.get_data(as_text=True))
        with app.app_context():
            receipt = GoodsReceipt.query.one()
            discrepancies = DiscrepanciaRecepcion.query.order_by(
                DiscrepanciaRecepcion.tipo
            ).all()
            self.assertEqual(receipt.lines[0].cantidad_recibida, Decimal("8.0000"))
            self.assertEqual({item.tipo for item in discrepancies}, {"faltante", "rechazado"})
            self.assertTrue(all(item.estado == "abierta" for item in discrepancies))

    def test_ceo_dashboard_is_aggregate_and_cannot_open_administration(self):
        self.login("direccion")
        dashboard = self.client.get("/direccion/")
        text = dashboard.get_data(as_text=True)
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Dirección ejecutiva", text)
        self.assertIn("Sin datos personales de trabajadores", text)
        self.assertNotIn("Residente Fase 5", text)
        self.assertEqual(self.client.get("/admin/usuarios").status_code, 403)


if __name__ == "__main__":
    unittest.main()
