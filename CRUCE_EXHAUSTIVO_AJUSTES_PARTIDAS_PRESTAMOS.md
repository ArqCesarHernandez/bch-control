# Cruce exhaustivo previo al código

## Separación de partida en nómina y recurso requerido por préstamos

**Proyecto:** BCH Control  
**Fecha de auditoría:** 24 de julio de 2026  
**Base revisada:** migración `a9c4e7f2b631`, construida sobre `f4b8c2d9e671`  
**Regresión previa a cambios:** 74 de 74 pruebas aprobadas

Este documento se cerró antes de modificar modelos, rutas, plantillas o
migraciones. Su objetivo es fijar una sola interpretación para todos los
totales afectados y evitar fórmulas paralelas.

## 1. Diagnóstico de la última entrega

### Ya implementado correctamente

- `payroll_lines.budget_item_id` ya guarda una asignación semanal; los reportes
  actuales no obtienen la partida desde `employees`.
- El servicio `services/weekly_resources.py` ya es la fuente central del
  recurso semanal.
- `loans.metodo_entrega`, `loans.company_id` —expuesto en el modelo como
  `empresa_entrega_id`— y `loans.project_id` ya existen.
- El recurso semanal suma una sola vez `loans.monto` en la semana de entrega,
  según `metodo_entrega`.
- `loan_payments` no se consulta en la fórmula central de recurso.
- Admin, CEO, Supervisor, panel operativo y Excel ya consumen la misma función
  central de préstamos.

### Faltante detectado

- El alta y la importación de trabajadores todavía exigen
  `employees.budget_item_id`.
- La captura de nómina tiene un solo selector y solo admite partidas raíz; no
  guarda por separado partida y subpartida.
- `payroll_lines` no tiene aún las columnas físicas `partida_id` y
  `subpartida_id`.
- La precarga usa la última nómina cerrada, aunque no sea la semana inmediata,
  y ante ausencia selecciona silenciosamente la partida del empleado o la
  primera partida de la obra.
- El filtro de reportes compara un único `budget_item_id`; no agrega las
  subpartidas al filtrar una partida padre.
- El Excel de nóminas muestra una sola columna combinada.
- El dashboard del Supervisor no presenta todavía el desglose de mano de obra
  por partida/subpartida.

## 2. Convenciones y fórmulas maestras

### Semana operativa

```text
semana_inicio = lunes
semana_fin    = viernes = semana_inicio + 4 días
```

### Costo de mano de obra

Por línea de nómina:

```text
Costo_MO_línea =
    payroll_lines.monto_devengado
  + payroll_lines.pago_extra
  + payroll_lines.descuento_imss
```

`descuento_imss` conserva su nombre histórico, pero representa costo patronal:
se suma al costo y no se resta del neto del trabajador.

Por partida o subpartida:

```text
Costo_MO_asignación = Σ Costo_MO_línea
```

Solo se considera consumo presupuestal definitivo cuando
`payrolls.estado IN ('aprobada', 'pagada', 'conciliada')`.

### Asignación presupuestaria de una línea

```text
Partida      = payroll_lines.partida_id
Subpartida   = payroll_lines.subpartida_id, si la partida tiene hijas
Ítem efectivo para presupuesto =
    COALESCE(payroll_lines.subpartida_id, payroll_lines.partida_id)
```

`payroll_lines.budget_item_id` se conservará como columna de compatibilidad y
se sincronizará con el ítem efectivo. Ninguna fórmula nueva consultará
`employees.budget_item_id`.

### Recurso semanal por método

Para `M ∈ {EFECTIVO, TRANSFERENCIA}`:

```text
Recurso_M =
    Nómina_neta_M
  + Capital_préstamos_nuevos_M
  + Gastos_operativos_M
  + Pagos_adicionales_M
  + Pagos_subcontratos_M
```

Donde:

```text
Nómina_neta_M =
  Σ payroll_lines.pago_efectivo
  o Σ payroll_lines.pago_transferencia

Capital_préstamos_nuevos_M =
  Σ loans.monto

Recurso_total = Recurso_EFECTIVO + Recurso_TRANSFERENCIA
```

Los cheques históricos se agrupan en `TRANSFERENCIA`. Los préstamos nuevos
solo aceptan `EFECTIVO` o `TRANSFERENCIA`.

Quedan expresamente fuera:

```text
loan_payments.monto
payroll_lines.descuento_prestamo como sumando independiente
loans.total_pagar
intereses
saldos pendientes
valor nominal de órdenes de compra
```

La retención ya está incorporada al calcular `payroll_lines.neto_pagar`; volver
a sumarla sería duplicarla.

## 3. Cruce de los 19 puntos obligatorios

### 1. Dashboard del Supervisor: mano de obra por partida

**Fórmula exacta**

```text
Costo_MO(partida, subpartida) =
  Σ(monto_devengado + pago_extra + descuento_imss)
```

**Tablas y campos**

- `payrolls`: `id`, `project_id`, `semana_inicio`, `estado`.
- `payroll_lines`: `payroll_id`, `partida_id`, `subpartida_id`,
  `monto_devengado`, `pago_extra`, `descuento_imss`.
- `budget_items`: `id`, `project_id`, `parent_id`, `codigo`, `nombre`.

**Filtros**

- `payrolls.project_id = obra_activa_id`.
- Consumo confirmado:
  `payrolls.estado IN ('aprobada','pagada','conciliada')`.
- Desglose por `payroll_lines.partida_id` y, cuando exista,
  `payroll_lines.subpartida_id`.

**Control**

No se une con `employees` para resolver la partida. Cada línea se suma una sola
vez en su asignación semanal.

### 2. Reporte de costo por partida

**Fórmula exacta**

```text
Nómina_con_IMSS = Σ Costo_MO_línea
IMSS_incluido   = Σ descuento_imss
Consumido_total =
    Nómina_con_IMSS
  + pagos_adicionales_sin_IVA
  + subcontratos_pagados_sin_IVA
  + gastos_oficina_sin_IVA
Disponible = presupuesto_partida - Consumido_total
```

**Tablas y campos**

- Mano de obra: `payrolls` y `payroll_lines.partida_id/subpartida_id`.
- Presupuesto: `budget_items.presupuesto`.
- Otros costos: `additional_payments.monto_sin_iva`,
  `subcontract_payments.monto_sin_iva`,
  `office_expenses.monto_sin_iva`.

**Filtros**

- Obra accesible.
- Nómina en estado final.
- Partida padre: incluye todas sus líneas, tengan o no subpartida.
- Subpartida: incluye únicamente `payroll_lines.subpartida_id = id`.

**Control**

Una línea con subpartida se agrega al total de su partida padre, pero no se
duplica dentro del total general de la obra.

### 3. Cierre de nómina

**Fórmula/validación exacta**

```text
Para toda línea:
  partida_id es obligatorio
  si la partida tiene subpartidas activas:
      subpartida_id es obligatorio
  la partida y subpartida pertenecen a payroll.project_id
  subpartida.parent_id = partida_id
```

Mensaje obligatorio ante asignación incompleta:

> Debe asignar una partida a cada trabajador antes de guardar.

**Tablas y campos**

- `payrolls.id`, `payrolls.project_id`, `payrolls.estado`.
- `payroll_lines.partida_id`, `payroll_lines.subpartida_id`.
- `budget_items.project_id`, `budget_items.parent_id`,
  `budget_items.activa`.

**Filtros**

- Solo nómina accesible.
- Guardado explícito únicamente en `borrador`.
- Envío/aprobación desde los estados permitidos por el ciclo existente.

**Control**

La misma validación de asignación se ejecuta al guardar, enviar y aprobar; no
existe una ruta de cierre que la omita.

### 4. Precarga semanal

**Regla exacta**

```text
semana_anterior = semana_nueva - 7 días

Para cada trabajador:
  sugerencia_partida =
      línea del mismo trabajador, misma obra y semana_anterior
  sugerencia_subpartida =
      subpartida de esa misma línea
```

Si no existe línea válida en la semana inmediata anterior, ambos campos quedan
sin seleccionar. No se usa `employees.budget_item_id` ni la primera partida de
la obra como sustituto.

**Tablas y campos**

- `payrolls.project_id`, `payrolls.semana_inicio`.
- `payroll_lines.employee_id`, `partida_id`, `subpartida_id`.
- `employees.project_id`, `employees.activo` para decidir a quién precargar,
  no para decidir la partida.

**Filtros**

- Misma obra.
- Semana exacta anterior.
- Mismo trabajador.
- Partida/subpartida activas y pertenecientes a la obra nueva.

**Control**

Cada nómina conserva su propia fotografía. Editar la sugerencia no modifica la
semana anterior ni el maestro del trabajador.

### 5. Exportación a Excel

**Fórmula exacta**

Cada renglón exporta los importes almacenados en su `payroll_line`. Las
columnas presupuestarias serán:

```text
Partida    = payroll_lines.partida_id → budget_items.etiqueta
Subpartida = payroll_lines.subpartida_id → budget_items.etiqueta, o vacío
```

El costo mostrado sigue siendo:

```text
monto_devengado + pago_extra + descuento_imss
```

**Tablas y campos**

- `payrolls`, `payroll_lines`, `budget_items`.

**Filtros**

- Los mismos filtros de obra, estado, fecha y partida aplicados en pantalla.

**Control**

No se exporta la partida del empleado. Una sola línea produce un solo renglón.

### 6. Filtros de reportes por partida

**Fórmula exacta**

```text
Si filtro = partida padre:
    payroll_lines.partida_id = filtro

Si filtro = subpartida:
    payroll_lines.subpartida_id = filtro
```

Para filas históricas migradas, ambos campos serán rellenados antes de
habilitar la nueva versión.

**Tablas y campos**

- `budget_items.id`, `parent_id`, `project_id`.
- `payroll_lines.partida_id`, `subpartida_id`.
- `payrolls.project_id`, `estado`, `semana_inicio`.

**Filtros**

- Primero obra accesible; después partida válida de esa obra.
- Se conservan estado, rango de semanas y filtro de faltas.

**Control**

Filtrar la partida padre incluye sus subpartidas sin hacer un `UNION` que
repita líneas.

### 7. Interacción con presupuestos

**Fórmula exacta**

```text
Ítem_consumido =
  subpartida_id, si existe
  de lo contrario partida_id

Consumo_MO_ítem =
  Σ(monto_devengado + pago_extra + descuento_imss)

Consumo_MO_partida_padre =
  Σ líneas con partida_id = partida_padre
```

**Tablas y campos**

- `budget_items.presupuesto`, `parent_id`, `categoria`.
- `payroll_lines.partida_id`, `subpartida_id`,
  `monto_devengado`, `pago_extra`, `descuento_imss`.
- `payrolls.estado`.

**Filtros**

- Obra de la nómina.
- Solo estados finales para consumo real.

**Control**

La subpartida recibe el detalle y la partida padre recibe el agregado. El total
de obra usa las líneas, no la suma padre más hijos.

### 8. Múltiples obras

**Regla exacta**

```text
Partidas disponibles =
  budget_items WHERE project_id = obra_activa_id
                 AND parent_id IS NULL
                 AND activa = 1

Subpartidas disponibles =
  budget_items WHERE parent_id = partida_seleccionada
                 AND project_id = obra_activa_id
                 AND activa = 1
```

**Tablas y campos**

- `user_projects.user_id`, `project_id`.
- Sesión: `active_project_id`.
- `budget_items.project_id`, `parent_id`, `activa`.
- `payrolls.project_id`.

**Filtros**

- El Supervisor solo opera la obra activa.
- Admin/finanzas conservan su alcance global o asignado.

**Control**

Backend y selector aplican el mismo alcance; manipular el HTML con una partida
de otra obra produce rechazo y no reasigna la línea.

### 9. Dashboard del Administrador: efectivo y transferencias

**Fórmula exacta**

Para cada método:

```text
Requerido =
    Σ pago_nómina_del_método
  + Σ loans.monto entregado por el método
  + Σ gasto_operativo_del_método
  + Σ pago_adicional_del_método
  + Σ pago_subcontrato_del_método
```

**Tablas y campos**

- `payrolls.semana_inicio`, `project_id`, `estado`.
- `payroll_lines.pago_efectivo`, `pago_transferencia`.
- `loans.fecha_prestamo`, `monto`, `metodo_entrega`, `estado`,
  `project_id`.
- `office_expenses.fecha`, `monto_capturado`, `metodo_pago`.
- `additional_payments.fecha`, `monto_capturado`, `metodo_pago`.
- `subcontract_payments.fecha`, `monto_capturado`, `metodo_pago`.

**Filtros**

- Fecha entre lunes y viernes de la semana.
- Global para Admin con acceso total; obras accesibles para un perfil limitado.
- `loans.estado IN ('activo','liquidado')`.
- Método normalizado: efectivo contra banco.

**Control**

No se consulta `loan_payments`. Se usa capital `loans.monto`, nunca
`total_pagar`.

### 10. Panel “Nóminas y Gastos Operativos”

**Fórmula exacta**

La misma fórmula del punto 9, reutilizando `weekly_resource_breakdown()` para
cada combinación de semana y obra.

**Tablas y campos**

Las mismas del punto 9.

**Filtros**

- Rango solicitado convertido a semanas completas.
- Obra seleccionada o todas las obras accesibles.
- Dos renglones exclusivos por obra/semana: efectivo y transferencia.

**Control**

Los totales de pantalla y Excel se obtienen del mismo diccionario. No existe
una suma separada de abonos.

### 11. Panel “Pagos a Proveedores”

**Fórmula exacta**

```text
Proveedor_recurso =
    Σ additional_payments.monto_capturado
  + Σ office_expenses.monto_capturado
```

El valor nominal de una OC es informativo hasta que existe el pago capturado.

**Tablas y campos**

- `additional_payments`.
- `office_expenses`.
- `purchase_orders` solo como referencia documental.

**Filtros**

- Semana y obra del pago.

**Control**

No se unen `loans` ni `loan_payments`. Las entregas y abonos de préstamos no
aparecen como proveedores.

### 12. Dashboard del Supervisor: recurso de sus obras

**Fórmula exacta**

La fórmula del punto 9 con:

```text
project_ids = [obra_activa_id]
```

Para préstamos se usa:

```text
COALESCE(loans.project_id, employees.project_id)
```

El `COALESCE` solo cubre registros históricos; los nuevos préstamos fotografían
la obra en `loans.project_id`.

**Tablas y campos**

Las del punto 9, más `user_projects` y la obra activa de sesión.

**Filtros**

- Semana actual.
- Obra activa asignada al Supervisor.
- Método de entrega/pago.

**Control**

Un préstamo no aparece en dos obras y no se mueve si después se reasigna al
trabajador.

### 13. Cierre de nómina y abonos

**Fórmula exacta**

```text
neto_pagar =
  devengado + extras
  - Infonavit
  - otros descuentos
  - descuento_prestamo

recurso_nómina =
  pago_efectivo + pago_transferencia = neto_pagar
```

Al aprobar se crea `loan_payments`, pero:

```text
Δ Recurso_requerido por crear el abono = 0
```

**Tablas y campos**

- `payroll_lines.descuento_prestamo`, `neto_pagar`,
  `pago_efectivo`, `pago_transferencia`.
- `loan_payments.loan_id`, `payroll_line_id`, `monto`.

**Filtros**

- Nómina que se aprueba.
- Préstamos activos elegibles desde la semana posterior a su entrega.

**Control**

La función de recurso no importa ni consulta `LoanPayment`; el abono no se suma
por segunda vez.

### 14. Reapertura de nómina

**Fórmula exacta**

```text
Reapertura:
  eliminar loan_payments de las líneas
  recalcular la retención prevista
  conservar pago_efectivo + pago_transferencia = neto_pagar

Δ Recurso_requerido por revertir el abono = 0
```

**Tablas y campos**

- `payrolls.estado`.
- `payroll_lines`.
- `loan_payments`.
- `loans.estado`.

**Filtros**

- Solo `aprobada → borrador`.
- No se permite reabrir `pagada` o `conciliada`.

**Control**

La reversión cambia saldo/estado del préstamo, no crea una entrada ni una salida
de caja.

### 15. Pagos adicionales

**Fórmula exacta**

Cada salida entra en una sola categoría:

```text
Si AdditionalPayment pertenece a OC de OPERACIONES:
    componente = gastos_operativos
En otro caso:
    componente = pagos_adicionales
```

**Tablas y campos**

- `additional_payments.monto_capturado`, `metodo_pago`,
  `purchase_order_id`.
- `purchase_orders.categoria_pago`, `tipo_oc`.
- `loans` se procesa por separado.

**Filtros**

- Misma semana, obra y método.

**Control**

Crear o cerrar un préstamo no crea un `AdditionalPayment`. Por tanto, no hay
duplicación automática. Un desembolso de préstamo debe registrarse únicamente
en `loans`; la interfaz no ofrece un vínculo que lo replique como pago
adicional.

### 16. Reporte semanal de recursos

**Fórmula exacta**

La tabla “Recurso por método” usa directamente el resultado del punto 9.
El resumen por obra concilia así:

```text
Recurso_total_obra =
    nómina_neta
  + proveedores_recurso
  + subcontratos_recurso
  + préstamos_entregados
```

`nomina_prestamos` se presenta solo como retención informativa.

**Tablas y campos**

- Las del punto 9.
- `loan_payments` únicamente para mostrar abonos y saldo, no para
  `recurso_total`.

**Filtros**

- Semana solicitada.
- Todas las obras autorizadas para el reporte consolidado.

**Control**

La suma por obra debe coincidir con efectivo más transferencias de la fuente
central. La retención no se añade al total.

### 17. CEO/Admin consolidado

**Fórmula exacta**

```text
Recurso_global_M = weekly_resource_breakdown(semana, project_ids=None)[M]
Recurso_global = Recurso_global_EFECTIVO + Recurso_global_TRANSFERENCIA
```

**Tablas y campos**

Las del punto 9.

**Filtros**

- Semana actual.
- Sin filtro de obra para un rol global.
- Método.

**Control**

La consulta global procesa cada fila una vez; no suma primero obras y después
vuelve a agregar el consolidado.

### 18. Reporte de costos totales

**Fórmula exacta**

```text
Costo_total =
    Costo_MO
  + proveedores_costo_sin_IVA
  + subcontratos_costo_sin_IVA

Recurso_total =
    nómina_neta
  + proveedores_recurso_capturado
  + subcontratos_recurso_capturado
  + capital_préstamos_entregados
```

**Tablas y campos**

- Costo MO: `payroll_lines.partida_id/subpartida_id`,
  `monto_devengado`, `pago_extra`, `descuento_imss`.
- Recursos: tablas del punto 9.

**Filtros**

- Misma semana y obra para conciliación.
- Estado final para consumo presupuestal; la vista de recurso puede incluir el
  borrador vigente porque representa necesidad de fondos.

**Control**

Capital de préstamo es salida de recurso, pero no costo de obra. Abono de
préstamo reduce el neto, pero no es costo ni una nueva salida. La diferencia
entre costo y recurso es intencional y trazable.

### 19. Conciliación contable

**Identidades exactas**

```text
Nómina_neta = Efectivo_nómina + Transferencia_nómina

Recurso_total =
    Efectivo_requerido + Transferencias_requeridas

Capital_entregado_semana =
    Préstamos_efectivo + Préstamos_transferencia

Abonos_informativos =
    Σ loan_payments.monto

Abonos_informativos no se agregan a Recurso_total
```

**Tablas y campos**

- `payroll_lines`.
- `loans`.
- `loan_payments` solo como control de cartera.
- Tablas de egresos operativos indicadas en el punto 9.

**Filtros**

- Misma semana de lunes a viernes.
- Misma obra o consolidado.
- Mismo canal de pago.

**Control**

Cada salida real tiene una sola fuente:

- nómina: `payroll_lines`;
- capital prestado: `loans`;
- operación/proveedor: `additional_payments` u `office_expenses`;
- subcontrato: `subcontract_payments`.

No se usa una tabla de abonos como fuente de salida.

## 4. Hallazgos adicionales incorporados

### 20. Alta e importación masiva de trabajadores

El formulario y la plantilla de importación eliminarán
`PARTIDA_CODIGO`. El alta individual pedirá únicamente nombre, fecha de
ingreso, puesto, obra, salario e IMSS/Infonavit; los datos operativos
predeterminados seguirán disponibles al editar al trabajador. La importación
masiva conserva sus columnas operativas opcionales, pero tampoco asigna
partida.

`employees.budget_item_id` ya es nullable. Se conservará temporalmente en el
esquema para compatibilidad, pero no se capturará, no se precargará y no se
consultará para costos.

### 21. Migración y compatibilidad histórica

Para cada línea existente:

```text
Si budget_item_id apunta a partida raíz:
    partida_id = budget_item_id
    subpartida_id = NULL

Si budget_item_id apunta a una subpartida:
    partida_id = budget_items.parent_id
    subpartida_id = budget_item_id
```

Después:

```text
budget_item_id =
  COALESCE(subpartida_id, partida_id)
```

`budget_item_id` se vuelve nullable para permitir crear el borrador inicial de
una semana cuando un trabajador nuevo aún no tiene sugerencia. El guardado
explícito, envío y aprobación continúan bloqueados hasta completar todas las
asignaciones.

## 5. Criterios de aceptación

- Alta individual y masiva sin partida.
- Selector dependiente partida/subpartida por cada línea de nómina.
- Mensaje obligatorio exacto ante una línea sin asignación.
- Sugerencia solo desde la semana inmediata anterior y siempre editable.
- Ningún reporte obtiene partida desde `employees`.
- Filtro padre incluye subpartidas sin duplicar líneas.
- Dashboard del Supervisor muestra mano de obra por partida de la obra activa.
- Excel separa partida y subpartida.
- Recurso semanal continúa usando solo `loans.monto` en la semana de entrega.
- Cierre y reapertura no cambian el recurso por crear/eliminar abonos.
- Migración conserva el 100% de líneas históricas y sus costos.
