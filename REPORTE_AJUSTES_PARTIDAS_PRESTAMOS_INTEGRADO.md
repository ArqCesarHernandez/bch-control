# Reporte técnico · Partidas semanales y recurso de préstamos

**Fecha:** 24 de julio de 2026  
**Base auditada:** `a9c4e7f2b631`  
**Revisión final:** `b7d2f6a8c914`  
**Suite final:** 75 de 75 pruebas aprobadas

## Resultado

BCH Control quedó integrado sobre C1, C2, C3, Fase 5, actualización operativa,
CSRF/Logout y multiobra. La partida ya no pertenece al maestro del trabajador:
se asigna por cada línea y semana de nómina, con subpartida dependiente cuando
corresponde.

La corrección de préstamos que ya existía en la última entrega se conservó y
se volvió a cruzar contra todos los consumidores. El capital se suma una sola
vez en la semana de entrega y los abonos quedan fuera del recurso requerido.

El análisis previo, con fórmula, tablas, campos, filtros y control de
duplicaciones para los 19 puntos obligatorios, está en:

```text
CRUCE_EXHAUSTIVO_AJUSTES_PARTIDAS_PRESTAMOS.md
```

Ese documento fue cerrado antes de editar modelos, rutas, plantillas o
migraciones.

## Diagnóstico de la última entrega

### Ya estaba implementado

- `loans.metodo_entrega`.
- `loans.company_id`, expuesto como `empresa_entrega_id`.
- `loans.project_id` como fotografía de la obra.
- servicio central `services/weekly_resources.py`;
- capital `loans.monto` por semana y método;
- exclusión total de `loan_payments` de la fórmula;
- Admin, Supervisor, CEO, panel operativo y Excel usando la fuente central.

### Faltaba completar

- quitar partida del alta e importación de trabajadores;
- crear columnas físicas separadas en `payroll_lines`;
- selector dependiente por cada renglón;
- bloqueo idéntico al guardar, enviar o aprobar;
- precarga solo desde la semana inmediata anterior;
- filtro jerárquico padre/hija;
- columnas separadas en Excel;
- consumo presupuestal por asignación semanal;
- desglose de mano de obra por partida en el dashboard del Supervisor.

## Cambios de modelo

### `Employee`

- `budget_item_id` permanece nullable solo para compatibilidad histórica.
- Altas, ediciones e importaciones nuevas lo guardan en `NULL`.
- Ningún cálculo o reporte consulta ese campo.

### `PayrollLine`

Se agregaron:

```text
partida_id       FK budget_items.id, nullable durante el borrador
subpartida_id    FK budget_items.id, nullable
```

`budget_item_id` se conserva nullable y sincronizado como:

```text
COALESCE(subpartida_id, partida_id)
```

Las propiedades `partida_resuelta`, `subpartida_resuelta` y
`budget_item_efectivo` permiten leer filas nuevas e históricas sin bifurcar las
fórmulas.

El sincronizador conserva un `budget_item_id` legado cuando una integración
externa todavía no envía las columnas nuevas; al leerlo se infiere
partida/subpartida. Las capturas web nuevas siempre escriben las tres llaves
coherentemente.

### `Loan`

- Se conservaron `metodo_entrega`, `company_id`/`empresa_entrega_id`,
  `project_id` y `monto`.
- Se agregó la restricción de base:

  ```text
  metodo_entrega IN ('EFECTIVO','TRANSFERENCIA')
  ```

- `LoanPayment` no cambió y no participa en el recurso requerido.

## Formularios y validación

Este proyecto no tiene clases `EmpleadoForm` ni `NominaForm`; esos dos flujos
usan formularios Jinja dinámicos y validación transaccional en
`routes/nominas.py`. No se creó una segunda capa WTForms que pudiera
contradecir el comportamiento existente.

- Alta individual: nombre, ingreso, puesto, obra, salario e IMSS/Infonavit.
- Los datos operativos opcionales permanecen disponibles al editar.
- Importación de trabajadores: se eliminó `PARTIDA_CODIGO`.
- Nómina: cada renglón tiene `partida_id` y `subpartida_id`.
- El navegador filtra subpartidas y el servidor repite todas las validaciones.
- Mensaje común:

  ```text
  Debe asignar una partida a cada trabajador antes de guardar.
  ```

- La misma regla bloquea guardar borrador, enviar y aprobar/cerrar.
- Una partida manipulada de otra obra se rechaza sin mutar la línea.

## Precarga e independencia semanal

La única fuente de sugerencia es:

```text
misma obra
+ mismo trabajador
+ semana_inicio = nueva_semana - 7 días
```

Si falta esa semana, los selectores quedan vacíos. No se usa la partida del
empleado ni la primera partida de la obra. Cambiar la sugerencia modifica
únicamente la línea actual.

## Fórmulas consolidadas

### Costo de mano de obra

```text
Costo línea =
  monto_devengado
  + pago_extra
  + descuento_imss patronal
```

El consumo real usa nóminas `aprobada`, `pagada` o `conciliada`.

```text
Ítem efectivo = subpartida_id si existe; en otro caso partida_id
```

La partida padre agrega todas sus líneas una sola vez; el total de obra nunca
suma padre más hijos.

### Recurso requerido

Para efectivo y transferencia por separado:

```text
Recurso =
  nómina neta del método
  + loans.monto entregado en la semana por el método
  + gastos operativos
  + pagos adicionales
  + subcontratos
```

Se excluyen:

```text
loan_payments.monto
payroll_lines.descuento_prestamo como sumando
loans.total_pagar
intereses y saldos
```

Cerrar o reabrir una nómina crea o elimina abonos, pero su variación directa
en el recurso es cero.

## Reportes y paneles

- Dashboard del Supervisor: mano de obra por partida/subpartida de la obra
  activa.
- Reporte de nómina: filtro jerárquico seguro por obra y partida.
- Excel de nóminas: columnas separadas **Partida** y **Subpartida**.
- Presupuesto por partida: consumo desde `PayrollLine`.
- Admin, CEO, Supervisor, “Nóminas y Gastos Operativos” y hoja **Recurso
  semanal**: misma función central.
- “Pagos a Proveedores”: sin préstamos ni abonos.
- Recursos multiobra: `loans.project_id`, con fallback histórico controlado.

## Migración

Archivo:

```text
migrations/versions/b7d2f6a8c914_partida_subpartida_semanal.py
```

Backfill:

```text
ítem raíz:
  partida_id = budget_item_id
  subpartida_id = NULL

ítem hijo:
  partida_id = budget_items.parent_id
  subpartida_id = budget_item_id
```

Se probaron:

- base vacía hasta `b7d2f6a8c914`;
- base histórica en `a9c4e7f2b631`;
- línea asignada a raíz;
- línea asignada a subpartida;
- normalización de préstamo histórico;
- preservación de capital, empresa y obra;
- ciclo subir → bajar → subir;
- `flask db check` sin operaciones pendientes.

## Archivos modificados respecto de la última entrega

```text
nominas_models.py
routes/nominas.py
routes/supervisor.py
static/nominas/app.js
static/nominas/style.css
templates/campo/dashboard_supervisor.html
templates/nominas/base.html
templates/nominas/employees/detail.html
templates/nominas/employees/form.html
templates/nominas/employees/list.html
templates/nominas/payrolls/detail.html
templates/nominas/reports/index.html
tests/test_actualizacion_operativa.py
tests/test_criticos_c2_c3.py
tests/test_nominas_integracion.py
```

Archivo nuevo:

```text
migrations/versions/b7d2f6a8c914_partida_subpartida_semanal.py
```

No fue necesario modificar `forms.py`: no contiene los formularios de
trabajador o nómina.

## Verificación final

```text
75/75 pruebas aprobadas
63 tablas
231 rutas
135 plantillas Jinja compiladas
JavaScript válido con node --check
Python válido con compileall
b7d2f6a8c914 (head)
flask db check limpio
```

Las regresiones específicas cubren:

- alta y Excel masivo sin partida;
- partida y subpartida obligatorias;
- cierre bloqueado cuando falta asignación;
- rechazo de partida de otra obra;
- precarga exacta e independencia semanal;
- ausencia de fallback cuando existe un hueco semanal;
- filtro padre/hija;
- Excel y presupuesto;
- dashboard Supervisor por obra activa;
- capital por método;
- cierre/reapertura sin duplicar abonos;
- Admin, Supervisor, CEO y panel operativo;
- proveedores sin préstamos.
