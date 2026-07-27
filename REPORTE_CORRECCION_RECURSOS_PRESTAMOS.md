# Reporte técnico · Recurso requerido por préstamos

## Resultado

La corrección quedó integrada sobre BCH Control con C1, C2, C3, Fase 5,
actualización operativa, CSRF/Logout y multiobra.

La entrega inicial de un préstamo ahora afecta una sola vez el recurso de la
semana y el método correspondientes. Los abonos continúan reduciendo la nómina
neta, pero no se convierten en otra salida de efectivo o banco.

El cruce contable previo al código se encuentra en
`CRUCE_EXHAUSTIVO_RECURSO_PRESTAMOS.md`.

## Hallazgo en la revisión base

La revisión `f4b8c2d9e671` tenía cálculos separados:

- La función común de dashboards no incorporaba el capital entregado.
- El panel “Nóminas y Gastos Operativos” sí listaba préstamos, pero mezclaba
  una fórmula propia con el valor nominal de OC operativas y no separaba por
  método.
- El Excel no tenía una hoja de recurso semanal.

La corrección elimina esa divergencia mediante una sola fuente de cálculo. La
misma fuente excluye expresamente los abonos y evita tanto omisiones como
duplicaciones.

## Fórmula central

Para `m = EFECTIVO` o `TRANSFERENCIA`:

```text
NÓMINA_m =
  SUM(payroll_lines.pago_efectivo o pago_transferencia)

PRÉSTAMOS_NUEVOS_m =
  SUM(loans.monto)
  donde fecha_prestamo está entre lunes y viernes,
  estado está en activo/liquidado,
  obra está dentro del alcance,
  y metodo_entrega corresponde a m

GASTOS_OPERATIVOS_m =
  SUM(office_expenses.monto_capturado)
  + SUM(additional_payments.monto_capturado
        vinculados a OC de OPERACIONES)

PAGOS_ADICIONALES_m =
  SUM(additional_payments.monto_capturado
      no clasificados como OPERACIONES)

SUBCONTRATOS_m =
  SUM(subcontract_payments.monto_capturado)

RECURSO_REQUERIDO_m =
  NÓMINA_m
  + PRÉSTAMOS_NUEVOS_m
  + GASTOS_OPERATIVOS_m
  + PAGOS_ADICIONALES_m
  + SUBCONTRATOS_m
```

Quedan fuera:

```text
loan_payments.monto
payroll_lines.descuento_prestamo como sumando adicional
loans.total_pagar
OC operativas emitidas pero aún no pagadas
```

`CHEQUE` histórico se agrupa con transferencia/banco. Los préstamos nuevos
solo admiten `EFECTIVO` o `TRANSFERENCIA`.

## Modelos y migración

### `Loan`

- `metodo_entrega` ya existía como obligatorio y con valor predeterminado
  `EFECTIVO`.
- `company_id` ya era la FK a `companies` que representa a la empresa que
  entrega el capital. Se mantiene una sola columna y se agregan los alias
  `empresa_entrega_id` y `empresa_entrega`.
- Se agrega `project_id` como FK a `centros_costo` para fotografiar la obra de
  entrega.
- `obra_entrega` usa la fotografía y conserva fallback al trabajador para
  filas históricas que aún fueran nulas.

### Migración

- Revisión: `a9c4e7f2b631`.
- Revisión anterior: `f4b8c2d9e671`.
- Backfill: `loans.project_id = employees.project_id`.
- Índice: `ix_loans_project_id`.
- FK: `fk_loans_project_id`, con `ON DELETE RESTRICT`.
- El `downgrade` se bloquea si la obra histórica ya difiere de la obra actual
  del trabajador.

No se modifica `loan_payments`.

## Fuente única y consumidores

`services/weekly_resources.py` concentra:

- Normalización de semana.
- Canal efectivo/banco.
- Capital entregado por método y obra.
- Clasificación exclusiva de pagos operativos/adicionales.
- Nómina neta, subcontratos, disponibilidad y diferencia.

La función se reutiliza en:

- Dashboard del Administrador.
- Detalle de obra.
- Detalle de nómina.
- Reportes de Nómina.
- Cierre semanal.
- Dashboard del Supervisor.
- Dashboard de Dirección/CEO.
- Panel “Nóminas y Gastos Operativos”.
- Excel de Nómina.
- Excel del panel operativo.

El panel “Pagos a Proveedores” conserva su consulta propia y no importa ni
consulta `Loan` o `LoanPayment`.

## Filtros e invariantes

- Semana: lunes a viernes inclusivos.
- Nómina: `payrolls.semana_inicio = lunes`.
- Préstamo: `loans.fecha_prestamo BETWEEN lunes AND viernes`.
- Estado de entrega: `activo` o `liquidado`.
- Obra: `COALESCE(loans.project_id, employees.project_id)`.
- Supervisor: únicamente obra activa perteneciente a `user_projects`.
- Admin/CEO: consolidado global, salvo filtro explícito.
- Método: efectivo o transferencia; cheque histórico va a banco.
- Capital: `loans.monto`, no capital más interés.
- Cierre/reapertura: insertar o borrar `loan_payments` no cambia ningún
  sumando del recurso.
- Una OC operativa se muestra como referencia, pero entra al requerido solo
  cuando existe su pago capturado.
- Un `AdditionalPayment` se clasifica en una sola categoría.
- El flujo soportado de préstamos no crea `AdditionalPayment`; por ello no
  existe un segundo movimiento automático de la entrega.

## Excel

El archivo de Nómina agrega la hoja **Recurso semanal** con:

- Nómina efectivo
- Préstamos nuevos efectivo
- Gastos operativos efectivo
- Pagos adicionales efectivo
- Subcontratos efectivo
- Efectivo requerido
- Nómina transferencia
- Préstamos nuevos transferencia
- Gastos operativos transferencia
- Pagos adicionales transferencia
- Subcontratos transferencia
- Transferencias requeridas
- Recurso total requerido

La hoja **Préstamos** ahora muestra la **Obra de entrega**, no la obra actual
del trabajador.

El panel de Compras también exporta una hoja por semana, obra y método.

## Validación numérica de regresión

La prueba central usa:

- Nómina: $1,000 efectivo + $2,000 transferencia, ya neta de una retención de
  $500.
- Préstamo nuevo efectivo: $500 de capital; total a pagar $525.
- Préstamo nuevo transferencia: $700 de capital; total a pagar $735.
- Gastos operativos efectivo: $250.
- Pago adicional transferencia: $200.
- Subcontrato efectivo: $300.

Resultado:

```text
EFECTIVO      = 1,000 + 500 + 250 + 0 + 300 = 2,050
TRANSFERENCIA = 2,000 + 700 + 0 + 200 + 0   = 2,900
TOTAL                                            4,950
```

La retención de $500 y los $60 de interés total no se agregan.

## Pruebas realizadas

- **74/74 pruebas automatizadas aprobadas**.
- Cinco pruebas nuevas de recurso:
  - Fórmula y exclusión de abonos.
  - Cierre y reapertura invariantes.
  - Admin, Compras, Supervisor multiobra y CEO.
  - Excel global y filtrado por obra.
  - Validación de método y fallback efectivo.
- 135 plantillas Jinja compiladas.
- 231 rutas Flask registradas.
- 63 tablas SQLAlchemy creadas.
- Auditoría CSRF existente aprobada para todos los formularios POST.
- Fuente central inspeccionada por AST: no importa ni usa `LoanPayment`.
- Migración desde base vacía.
- Ciclo `subir → bajar → subir`.
- Migración desde base histórica `f4b8c2d9e671`.
- Backfill histórico validado.
- Reasignación posterior del trabajador validada.
- Bloqueo de `downgrade` con pérdida de trazabilidad validado.
- `flask db check`: sin operaciones pendientes.

## Archivos principales modificados

- `nominas_models.py`
- `services/weekly_resources.py`
- `routes/nominas.py`
- `routes/compras.py`
- `routes/supervisor.py`
- `routes/ceo.py`
- `migrations/versions/a9c4e7f2b631_recurso_prestamos_por_entrega.py`
- `templates/nominas/dashboard.html`
- `templates/nominas/projects/detail.html`
- `templates/nominas/payrolls/detail.html`
- `templates/nominas/reports/index.html`
- `templates/nominas/reports/weekly_closing.html`
- `templates/nominas/loans/form.html`
- `templates/campo/dashboard_supervisor.html`
- `templates/ceo/dashboard.html`
- `templates/compras/reports/payroll_operations.html`
- `tests/test_recursos_prestamos.py`
- Pruebas heredadas de Nómina y Compras actualizadas para la nueva hoja y la
  validación estricta del método.
