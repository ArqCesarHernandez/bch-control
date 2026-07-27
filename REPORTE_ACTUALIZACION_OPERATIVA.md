# BCH Control — reporte final de actualización operativa

## Resultado

La actualización quedó integrada sobre C1, C2, C3 y Fase 5, sin duplicar los
módulos existentes.

| Verificación | Resultado |
|---|---:|
| Revisión Alembic | `e3a7b9c1d245 (head)` |
| Pruebas heredadas | 44/44 |
| Pruebas nuevas | 17/17 |
| Total | 61/61 |
| Plantillas Jinja compiladas | 132 |
| Rutas Flask registradas | 220 |
| `flask db check` | Limpio |
| Base nueva | Aprobada |
| Base Fase 5 con información histórica | Aprobada |
| Ciclo subir–bajar–subir | Aprobado |

## 1. Modelos y datos

### Explosión versionada

- `explosion_revisions`
- Revisión vigente por obra.
- Conservación de revisiones históricas.
- Clasificación por concepto:

  - `NORMAL`
  - `OPERATIVO`
  - `EQUIPO_ESPECIAL`
  - `ELECTRODOMESTICO`

- Indicador `requiere_autorizacion_previa`.
- Referencia al renglón histórico usado en garantías.

### Requisiciones y RFQ

- Autorización por renglón en requisiciones mixtas.
- Fecha de liberación por concepto.
- `licitacion_lineas` enlaza únicamente los renglones liberados.
- La RFQ se genera o amplía sin recapturar la requisición.

### OC de Operaciones

- Proveedor de catálogo, empresa y método de pago anulables únicamente en el
  flujo operativo.
- Beneficiario libre sin alta automática en proveedores.
- Validación financiera independiente del beneficiario.
- Condición `PAGO_CONTRA_ENTREGA`.
- Porcentaje o monto de anticipo.
- Clasificación, observación y vínculo SMNC por renglón.
- Versión actual y fecha de actualización.

### Programación y revisión de OC

- `purchase_order_payment_schedules`

  - Anticipo solicitado.
  - Saldo contra recepción o entrega total.
  - Autorización, liberación, pago parcial y pago total separados.

- `purchase_order_revisions`

  - Usuario.
  - Fecha.
  - Motivo.
  - Valores anteriores.
  - Valores nuevos.

- Los pagos se vinculan a su programación cuando corresponde.

### Garantías

- `garantias_obras`.
- Centro de costo hijo con `tipo = garantia`.
- Relación con la obra principal sin reactivarla.
- Estados:

  `reportada → diagnostico → autorizada → en_ejecucion → pendiente_cierre → cerrada`

- Terminación alternativa `rechazada`.
- Explosión histórica clonada solo como clasificación de referencia.
- Presupuesto y avance físico del centro de garantía inician en cero.
- SMNC y costos quedan ligados al centro hijo.

### Almacén

- Evidencia persistente por discrepancia.
- Recepción parcial o total.
- Cantidades recibidas, rechazadas y faltantes validadas sin doble conteo.

## 2. Permisos y alcance

La matriz contiene 46 módulos y nueve acciones:

```text
ver, crear, editar, eliminar, aprobar,
emitir, cancelar, pagar, conciliar
```

Se separaron, entre otros:

- Dashboards general, Supervisor y Ejecutivo.
- Submódulos reales de Nómina.
- Dashboard de Compras, explosión, insumos, requisiciones y RFQ.
- OC de Compras y OC de Operaciones.
- Programación de pagos y pagos a proveedores.
- Recepciones, discrepancias y bandeja de Almacén.
- Proveedores y datos sensibles de proveedores.
- SMNC, garantías, contratos y conciliación.
- Campo Fase 5.
- Usuarios, seguridad y NSS.

Controles aplicados:

- El sidebar comprueba el permiso granular.
- La ruta repite la comprobación.
- La mutación vuelve a validar acción, tipo de documento y obra.
- Una obra ajena responde `404`.
- Una acción no autorizada responde `403`.
- Supervisor y Almacenista no obtienen alcance global por rol.
- La migración no sustituye permisos CRUD/aprobación existentes.

## 3. Rutas principales

### Supervisor y garantías

| Método | Ruta | Función |
|---|---|---|
| GET | `/campo/dashboard-supervisor` | Dashboard agregado y acotado |
| GET/POST | `/campo/garantias/nueva` | Reporte y centro hijo |
| GET/POST | `/campo/garantias/<id>/diagnostico` | Diagnóstico |
| POST | `/campo/garantias/<id>/resolver` | Autorizar o rechazar |
| POST | `/campo/garantias/<id>/iniciar` | Iniciar ejecución |
| GET/POST | `/campo/garantias/<id>/solicitar-cierre` | Acción y evidencia |
| POST | `/campo/garantias/<id>/cerrar` | Validación final |

### Compras y Finanzas

| Método | Ruta | Función |
|---|---|---|
| GET/POST | `/compras/ordenes-operaciones/nueva` | Guardar y emitir OC operativa |
| GET/POST | `/compras/ordenes/<id>/revision` | Revisión auditable |
| POST | `/compras/ordenes/<id>/aprobar-emision` | Aprobar y emitir |
| POST | `/compras/ordenes/<id>/validar-beneficiario` | Validación financiera |
| GET | `/compras/programacion-pagos` | Bandeja financiera |
| POST | `/compras/programacion-pagos/<id>/resolver` | Autorizar/rechazar anticipo |
| GET | `/compras/cotizaciones` | RFQ y cotizaciones |
| GET/POST | `/compras/smnc/nueva` | SMNC normal o de garantía |

### Almacén

| Método | Ruta | Función |
|---|---|---|
| GET | `/almacen/` | Recepciones pendientes por alcance |
| GET/POST | `/almacen/ordenes/<id>/recibir` | Recepción y discrepancias |
| GET | `/almacen/discrepancias` | Bandeja de discrepancias |
| POST | `/almacen/discrepancias/<id>/resolver` | Resolución |

## 4. Plantillas

Se incorporaron o actualizaron:

- Dashboard Supervisor responsive.
- Formulario directo de OC de Operaciones.
- Formulario de revisión de OC emitida.
- Programación financiera.
- Detalle/listado/formularios de garantías.
- RFQ por renglón liberado.
- Recepción móvil y evidencia de discrepancias.
- Proveedores con vista básica y campos sensibles segregados.
- Matriz administrativa de permisos.
- Sidebar generado por permisos granulares.
- Reportes y dashboard CEO compatibles con beneficiario libre.

## 5. Reglas financieras verificadas

- Emitir no paga.
- Aprobar un anticipo no lo marca como pagado.
- Sin anticipo, el saldo solo se libera contra recepción validada.
- Una recepción parcial libera únicamente el importe proporcional.
- Con anticipo, se separan anticipo y saldo.
- Supervisor solicita; Finanzas autoriza, valida beneficiario y registra pago.
- Una OC operativa sin proveedor de catálogo conserva beneficiario y
  trazabilidad sin crear un proveedor.
- Las OC históricas no reciben bloqueos retroactivos.

## 6. Cobertura automatizada nueva

Las 17 regresiones nuevas validan:

1. Alcance del Dashboard Supervisor.
2. Presupuesto desde la última explosión vigente.
3. Indicador “Sin explosión vigente”.
4. OC de Operaciones sin proveedor de catálogo.
5. Clasificación y observación obligatorias.
6. Rechazo de concepto SMNC no aprobado.
7. Pago contra recepción proporcional.
8. Anticipo, saldo y separación de funciones.
9. Emisión con un solo envío.
10. Revisión de OC emitida y valores anteriores.
11. Requisición mixta y RFQ por renglón.
12. Recepción parcial.
13. Faltante, rechazo y evidencia.
14. Garantía sobre obra inactiva sin reactivación.
15. SMNC ligada a garantía.
16. `403` por falta de permiso y `404` fuera de obra.
17. Matriz granular, proveedor básico seguro y emisión del Comprador.

## 7. Migración y compatibilidad

La revisión `e3a7b9c1d245`:

- Parte exclusivamente de `c6d9a4c5880d`.
- No recrea tablas de Fase 5 equivalentes.
- Materializa explosiones históricas como revisión 1.
- Conserva OC y pagos existentes.
- No crea programaciones para documentos históricos.
- Permite descenso únicamente mientras no existan datos nuevos incompatibles.
- Detiene el descenso con mensaje explícito antes de una pérdida.

Pruebas de migración realizadas:

- Base vacía hasta `head`.
- Base Fase 5 con administrador, Supervisor y Comprador.
- Permisos personalizados y revocados.
- Explosión, requisición y OC emitida históricas.
- `upgrade → downgrade → upgrade`.
- Verificación final con `flask db check`.

