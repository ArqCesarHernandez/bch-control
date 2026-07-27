# Cruce exhaustivo previo al código

## Corrección de préstamos en “recurso requerido”

**Proyecto:** BCH Control  
**Revisión base auditada:** `f4b8c2d9e671`  
**Fecha del cruce:** 24 de julio de 2026  
**Alcance:** C1, C2, C3, Fase 5, actualización operativa, multiobra y corrección CSRF/Logout.

Este documento se cerró antes de modificar código productivo. Su objetivo es
definir una sola regla contable y comprobar todos sus consumidores.

## 0. Hallazgos de la revisión base

1. `loans.metodo_entrega` ya existe, es `NOT NULL` y tiene valor
   predeterminado `EFECTIVO`.
2. `loans.company_id` ya es la llave foránea a `companies` que representa a la
   empresa que entrega el préstamo. Es el equivalente funcional de
   `empresa_entrega_id`; no se agregará una segunda columna que pueda
   contradecirla. El modelo expondrá un alias de negocio con ese nombre.
3. La función común `weekly_resource_breakdown()` actualmente suma nómina,
   pagos adicionales, gastos de oficina y subcontratos, pero no suma entregas
   de préstamos.
4. El panel de Compras “Nóminas y Gastos Operativos” tiene un cálculo separado:
   suma nómina neta, préstamos entregados y el valor de OC operativas emitidas,
   pero no separa los métodos de pago ni reutiliza la fórmula del dashboard.
5. `loan_payments` no se consulta hoy dentro de
   `weekly_resource_breakdown()`. Sí se usa para aplicar/revertir retenciones y
   para informar saldo. La corrección conservará esa separación.
6. El Excel de Nóminas no contiene una hoja específica de recurso semanal.
7. El dashboard de Supervisor y el de Dirección no muestran un consolidado de
   recurso requerido con esta fórmula.
8. `loans` no conserva una fotografía de la obra al momento de la entrega. Si
   el trabajador cambia de obra, un reporte histórico podría atribuir el
   préstamo a su obra actual. Se agregará `loans.project_id`, con backfill desde
   `employees.project_id`; los registros históricos nulos conservarán un
   fallback seguro al trabajador.

## 1. Definición única de la fórmula

### Ventana semanal

- `W0`: lunes de la semana.
- `W4`: viernes de la misma semana (`W0 + 4 días`).
- Todas las fechas de préstamos y egresos se filtran de forma inclusiva:
  `BETWEEN W0 AND W4`.
- La nómina se filtra por `payrolls.semana_inicio = W0`.

### Canal de pago

- `EFECTIVO` se conserva como efectivo.
- `TRANSFERENCIA` se conserva como transferencia.
- `CHEQUE` histórico se agrupa con `TRANSFERENCIA`, porque sale de banco.
- Los nuevos préstamos solo admitirán `EFECTIVO` o `TRANSFERENCIA`.

### Componentes por método `m`

```text
NÓMINA_m =
  SUM(payroll_lines.pago_efectivo)                  si m = EFECTIVO
  SUM(payroll_lines.pago_transferencia)             si m = TRANSFERENCIA

PRÉSTAMOS_NUEVOS_m =
  SUM(loans.monto)
  con loans.fecha_prestamo entre W0 y W4,
  loans.estado en ('activo', 'liquidado'),
  obra dentro del alcance
  y canal(loans.metodo_entrega) = m

GASTOS_OPERATIVOS_m =
  SUM(office_expenses.monto_capturado)
  + SUM(additional_payments.monto_capturado
        vinculados a una OC de categoría/tipo OPERACIONES)
  con fecha entre W0 y W4, obra dentro del alcance y canal = m

PAGOS_ADICIONALES_m =
  SUM(additional_payments.monto_capturado
      no clasificados como OPERACIONES)
  con fecha entre W0 y W4, obra dentro del alcance y canal = m

SUBCONTRATOS_m =
  SUM(subcontract_payments.monto_capturado)
  con fecha entre W0 y W4, obra del subcontrato dentro del alcance
  y canal = m

RECURSO_REQUERIDO_m =
  NÓMINA_m
  + PRÉSTAMOS_NUEVOS_m
  + GASTOS_OPERATIVOS_m
  + PAGOS_ADICIONALES_m
  + SUBCONTRATOS_m

RECURSO_REQUERIDO_TOTAL =
  RECURSO_REQUERIDO_EFECTIVO
  + RECURSO_REQUERIDO_TRANSFERENCIA
```

`SUBCONTRATOS` no estaba enumerado en la solicitud nueva, pero ya forma parte
del recurso requerido vigente. Se conserva para no reducir ni romper el total
operativo existente.

### Exclusión obligatoria

```text
loan_payments.monto NO forma parte de ningún sumando anterior.
payroll_lines.descuento_prestamo NO se suma al recurso requerido.
```

La retención ya está incorporada indirectamente porque:

```text
payroll_lines.neto_pagar =
  monto disponible antes del préstamo - descuento_prestamo

pago_efectivo + pago_transferencia = neto_pagar
```

Por ello, sumar además la retención sería una duplicación.

### Capital contra total a pagar

Se usa `loans.monto`, porque es el capital efectivamente entregado.  
`loans.total_pagar` incluye interés y se conserva únicamente para saldo y
amortización; no representa la salida inicial de caja/banco.

## 2. Cruce por consumidor

### 2.1 Dashboard del Administrador

**Fórmula exacta:** la fórmula única del apartado 1, para `EFECTIVO` y
`TRANSFERENCIA`.

**Tablas consultadas:**

- `payrolls`
- `payroll_lines`
- `loans`
- `employees` únicamente como fallback histórico de obra
- `additional_payments`
- `purchase_orders`, solo para clasificar un pago como operativo
- `office_expenses`
- `subcontract_payments`
- `subcontracts`
- `weekly_resource_availability`
- `companies`, solo para desglose informativo por empresa

**Filtros:**

- Semana: `payrolls.semana_inicio = W0`; las demás fechas entre `W0` y `W4`.
- Obra: todas las obras accesibles para el usuario; para acceso global no se
  aplica restricción.
- Método: canal normalizado `EFECTIVO` o `TRANSFERENCIA`.
- Préstamo: solo `activo` o `liquidado`; nunca `pendiente`, `aprobado` sin
  entrega o `rechazado`.

**Disponibilidad y diferencia:**

```text
DIFERENCIA_m =
  weekly_resource_availability.monto_disponible - RECURSO_REQUERIDO_m
```

**Confirmación de abonos excluidos:** no se consulta `loan_payments`; la
retención solo reduce el neto de la línea.

### 2.2 Panel “Nóminas y Gastos Operativos”

**Fórmula exacta:** idéntica a la fórmula única del apartado 1.

**Tablas consultadas:** las mismas del punto 2.1, excepto
`weekly_resource_availability` cuando el panel solo presenta requerido.

**Filtros:**

- Cada renglón se agrupa por lunes de semana, obra y método.
- El filtro de obra restringe todos los componentes, no solo la nómina.
- El intervalo de fechas se interpreta por semanas completas de lunes a
  viernes.
- Las OC operativas emitidas pueden seguir mostrándose como información
  documental, pero su valor nominal no se suma como recurso. Solo se suma el
  pago capturado correspondiente, evitando contar una OC no pagada o contarla
  otra vez al pagarla.

**Confirmación de abonos excluidos:** `loan_payments` y
`payroll_lines.descuento_prestamo` no son categorías del panel.

### 2.3 Panel “Pagos a Proveedores”

**Fórmula vigente que se conserva:**

```text
TOTAL_CATEGORÍA =
  SUM(additional_payments.monto_sin_iva)
  según purchase_orders.categoria_pago

TOTAL_TARJETAS =
  SUM(credit_card_payments.monto)
```

**Tablas consultadas:**

- `additional_payments`
- `purchase_orders`
- `suppliers`
- `credit_card_payments`
- `credit_cards`

**Filtros:**

- Rango de fechas solicitado.
- Obras accesibles.
- Proveedor y categoría, si se seleccionan.

**Confirmación de abonos excluidos:** ni `loans` ni `loan_payments` forman
parte de este reporte. La entrega inicial y las retenciones no modificarán sus
totales.

### 2.4 Dashboard del Supervisor

**Fórmula exacta:** la fórmula única del apartado 1.

**Tablas consultadas:** las mismas del punto 2.1.

**Filtros:**

- `project_ids = {obra_activa_id}`.
- La obra activa debe pertenecer a `user_projects`.
- Semana actual `W0..W4`.
- Método de pago normalizado.

**Confirmación de abonos excluidos:** no se consulta `loan_payments`.

El selector multiobra cambia el único `project_id` del alcance. Un préstamo de
otra obra asignada, pero no activa, no aparece hasta que el Supervisor cambie
la obra activa.

### 2.5 Exportación a Excel

Se agregará una hoja **“Recurso semanal”**.

**Fórmula exacta:** la fórmula única del apartado 1.

**Columnas:**

- Semana
- Alcance / obra
- Nómina en efectivo
- Préstamos nuevos en efectivo
- Gastos operativos en efectivo
- Pagos adicionales en efectivo
- Subcontratos en efectivo
- Efectivo requerido
- Nómina por transferencia
- Préstamos nuevos por transferencia
- Gastos operativos por transferencia
- Pagos adicionales por transferencia
- Subcontratos por transferencia
- Transferencias requeridas
- Recurso total requerido

**Tablas y filtros:** los mismos del punto 2.1, respetando los filtros de
semana y obra del reporte.

La hoja **“Préstamos”** continuará mostrando capital, total con interés,
retención y saldo como información; esos campos no se mezclarán con el recurso
semanal.

**Confirmación de abonos excluidos:** ninguna columna de recurso toma
`loan_payments`; el abono solo permanece en las hojas de nómina/préstamos como
dato informativo.

### 2.6 Cierre de nómina

**Operación financiera existente:**

```text
INSERT loan_payments(loan_id, payroll_line_id, monto)
UPDATE loans.estado = 'liquidado' cuando el saldo llega a cero
```

**Efecto en recurso requerido:**

```text
RECURSO_DESPUÉS_DEL_CIERRE = RECURSO_ANTES_DEL_CIERRE
```

La suma de nómina ya utilizaba el neto reducido antes del cierre. Cambiar el
estado del préstamo de `activo` a `liquidado` tampoco altera la entrega
histórica, porque ambos estados son elegibles únicamente en la semana de
`fecha_prestamo`.

**Confirmación de abonos excluidos:** el `INSERT` no es leído por la fórmula.

### 2.7 Reapertura de nómina

**Operación financiera existente:**

```text
DELETE loan_payments de las líneas de la nómina
UPDATE loans.estado = 'activo' cuando vuelve a existir saldo
recalcular descuento_prestamo y neto_pagar
```

**Efecto en recurso requerido:**

```text
RECURSO_DESPUÉS_DE_REABRIR = RECURSO_ANTES_DE_REABRIR
```

**Confirmación de abonos excluidos:** el `DELETE` no modifica ningún sumando
directo del recurso. La recalculación repone la misma retención prevista y el
mismo neto mientras no cambien otros datos de la línea.

### 2.8 Pagos adicionales relacionados con préstamos

En la revisión base no existe una relación automática
`Loan -> AdditionalPayment`: aprobar un préstamo no crea un pago adicional.

**Regla de no duplicación:**

- La entrega se toma una sola vez desde `loans`.
- Cada `additional_payment` se clasifica en exactamente una categoría:
  `GASTOS_OPERATIVOS` o `PAGOS_ADICIONALES`, nunca en ambas.
- Ningún `loan_payment` se transforma en `additional_payment`.
- Se agregará una prueba que confirme que solicitar/aprobar/cerrar/reabrir un
  préstamo no crea registros en `additional_payments`.

Si una persona registra manualmente un egreso independiente además del
préstamo, el sistema lo considera un movimiento distinto; no se intentará
deduplicar por texto, beneficiario o importe, porque sería inseguro.

### 2.9 Múltiples obras

**Fórmula exacta:** la fórmula única, con filtro de obra.

**Tablas consultadas para alcance:**

- `user_projects`
- `centros_costo`
- `loans.project_id` como fotografía de la obra de entrega
- `employees.project_id` solo como fallback para préstamos históricos

**Filtros:**

- Supervisor: obra activa.
- Administrador con filtro: obra seleccionada.
- Administrador global: todas las obras.

**Confirmación de abonos excluidos:** el proyecto de
`loan_payments.payroll_line_id` no se usa para sumar recurso.

### 2.10 Consolidado CEO / Administrador General

**Fórmula exacta:** la fórmula única con alcance global.

**Tablas consultadas:** las mismas del punto 2.1.

**Filtros:**

- Semana actual.
- Todas las obras.
- Método de pago.

El dashboard mostrará efectivo requerido, transferencias requeridas y total
requerido. Su flujo proyectado de cuentas por pagar conservará su significado
actual y no se mezclará con el nuevo indicador.

**Confirmación de abonos excluidos:** el consolidado reutiliza la misma función
central; no ejecuta una consulta separada de `loan_payments`.

## 3. Otros totales afectados encontrados

### 3.1 Reporte conjunto previo al cierre

**Cambio:**

```text
recurso_total_por_obra =
  nomina_neto
  + proveedores_recurso
  + subcontratos_recurso
  + prestamos_entregados
```

El préstamo no se suma a `costo_total`, porque entregar capital genera una
cuenta por cobrar al trabajador, no un costo presupuestal.

El desglose “Empresa que paga” añadirá la categoría `PRÉSTAMOS`.

### 3.2 Disponible contra requerido

Al agregarse el préstamo inicial:

```text
diferencia_efectivo =
  efectivo_disponible - efectivo_requerido_corregido

diferencia_transferencia =
  transferencia_disponible - transferencia_requerida_corregida
```

No se cambia la captura de disponibilidad ni se distribuye automáticamente por
obra.

### 3.3 Saldo del préstamo

Permanece:

```text
saldo_pendiente =
  loans.total_pagar - SUM(loan_payments.monto)
```

Este saldo no es recurso requerido. Tampoco lo es la tasa de interés.

### 3.4 Desglose por empresa

La entrega inicial se agrupa usando `loans.company_id` y
`loans.metodo_entrega`. Esto permite saber de qué empresa/caja/banco debe salir
el capital sin crear un segundo movimiento.

## 4. Matriz de invariantes para pruebas

1. Préstamo efectivo nuevo: aumenta solo efectivo por `loans.monto`.
2. Préstamo transferencia nuevo: aumenta solo transferencias.
3. Préstamo pendiente o rechazado: aumenta cero.
4. Interés: no aumenta la salida inicial.
5. Cierre con abono: el requerido no cambia.
6. Reapertura con reversión: el requerido no cambia.
7. Semana siguiente: no vuelve a incluir el capital entregado.
8. Varias retenciones: nunca aparecen como sumando.
9. Supervisor: solo obra activa.
10. Cambio posterior de obra del trabajador: el préstamo permanece en la obra
    fotografiada al entregarse.
11. Panel de proveedores: idéntico antes y después del préstamo.
12. Excel, dashboard, panel operativo, reporte de cierre y CEO: mismos totales.
13. Pago adicional operativo: se clasifica una sola vez.
14. Subcontratos: permanecen dentro del recurso vigente.
15. `requerido_total = efectivo_requerido + transferencia_requerida`.

## 5. Archivos previstos

- `nominas_models.py`: fotografía `Loan.project_id` y alias de empresa de
  entrega.
- `services/weekly_resources.py`: única fuente de cálculo.
- `routes/nominas.py`: consumidor, cierre conjunto y Excel.
- `routes/compras.py`: panel operativo alineado.
- `routes/supervisor.py`: recurso de obra activa.
- `routes/ceo.py`: consolidado semanal.
- Plantillas de dashboards y reportes: columnas de préstamos nuevos y desglose
  corregido.
- Migración posterior a `f4b8c2d9e671`.
- Pruebas de regresión específicas de los invariantes anteriores.

