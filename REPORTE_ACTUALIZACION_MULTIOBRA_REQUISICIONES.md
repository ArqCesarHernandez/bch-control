# Reporte técnico · Multiobra, Requisiciones y Compras

## Base y alcance

- Base: BCH Control con C1, C2, C3, Fase 5 y actualización operativa.
- Corrección CSRF/Logout integrada en el mismo paquete.
- Frameworks conservados: Flask, SQLAlchemy, Flask-WTF, Jinja2, Bootstrap 5
  y SQLite.
- Revisión Alembic final: `f4b8c2d9e671`.

## Modelos

### Relación Supervisor–Obra

Se reutilizó `user_projects`, cuya llave compuesta
`(user_id, project_id)` ya permite muchas obras por usuario. No se creó otra
tabla ni se alteraron asignaciones históricas.

La columna `usuarios.centro_costo_id` se mantiene como obra principal de
compatibilidad. La selección operativa se guarda en sesión como
`active_project_id`; nunca amplía el conjunto persistente de obras asignadas.

### Explosión y reserva

`budget_explosion_items` agrega:

- `cantidad_reservada_borrador NUMERIC(16,4) NOT NULL DEFAULT 0`
- `ck_explosion_draft_reserved_quantity`

El disponible se calcula como presupuesto menos OC activas, cantidades
aprobadas pendientes y reservas de borrador. La actualización de la reserva se
realiza dentro de la base y se revierte completa ante cualquier validación.

### Cotización consolidada

Se agregaron:

- `quotation_requisitions`
- `quotation_line_sources`
- `quotation_lines.supply_item_id`

`quotations.requisition_id` se conserva como ancla histórica. La restricción
que impedía más de una cotización por requisición/proveedor se retiró para
permitir documentos consolidados sin perder trazabilidad.

### Direcciones

Se agregaron:

- `centros_costo.direccion_entrega`
- `purchase_orders.direccion_entrega`
- `purchase_orders.direccion_entrega_confirmada_at`
- `purchase_orders.direccion_entrega_confirmada_por_id`

La OC conserva una instantánea editable y auditable de la dirección. No puede
pasar automáticamente a `CERRADA` hasta que la recepción, el pago y la
confirmación de dirección estén completos.

### Nómina

No se duplicó la llave de partida. `payroll_lines.budget_item_id` ya
representaba la partida de costo y se expone además mediante los alias de
negocio `partida_id` y `partida`.

## Rutas y seguridad

- `POST /obra-activa`
- `GET /compras/api/requisiciones/obras/<id>/partidas`
- `GET /compras/api/requisiciones/obras/<id>/materiales`
- `POST /compras/cotizaciones/consolidar`
- `GET|POST /compras/obras/<id>/direccion-entrega`
- `GET /compras/cotizaciones/<id>/solicitud`
- `GET /compras/ordenes/<id>/imprimir`
- `POST /compras/ordenes/<id>/confirmar-direccion`

El backend vuelve a comprobar:

- Permiso granular por módulo y acción.
- Asignación persistente a la obra.
- Obra activa del Supervisor.
- Tipo de requisición u OC permitido.
- Estado transaccional del documento.

Una obra ajena o distinta de la activa responde `404`; una acción sin permiso
responde `403`.

El Comprador tiene alcance global de obra por regla de negocio. Sus vínculos en
`user_projects` también se sincronizan para integraciones históricas y toda
obra creada desde cualquiera de las dos pantallas existentes se agrega
automáticamente.

## Flujo de requisición

1. El Supervisor selecciona una de sus obras.
2. Selecciona partida y subpartida dependiente.
3. La API carga los materiales de la explosión vigente.
4. La búsqueda filtra por clave o descripción sin consultar de nuevo.
5. Se seleccionan varios materiales con cantidades editables.
6. El navegador valida el máximo y conserva el formulario.
7. El servidor vuelve a validar y responde `422` JSON si existe un conflicto.
8. Al guardar, todas las cantidades quedan reservadas.
9. Cancelar o eliminar el borrador reintegra las reservas.

La tabla contiene únicamente selección, descripción, unidad, cantidad
solicitada, disponible posterior y comentarios. El campo histórico
`proveedor_sugerido` permanece en base para no destruir información, pero ya
no se captura, filtra ni muestra.

## Cotización y OC

La consolidación exige dos o más requisiciones aprobadas y un proveedor. Los
insumos repetidos se agrupan por `supply_item_id`, suman sus cantidades y
conservan cada línea fuente.

La solicitud de cotización muestra logo, proveedor, una o varias direcciones,
clave, descripción, unidad, cantidad y espacios para precio/importe, además de
condiciones y fecha límite.

La impresión de OC muestra logo, folio, fecha, proveedor/beneficiario,
dirección, clave y concepto, subtotal, IVA, total, condiciones y firmas. No
incluye una columna Origen.

## CSRF y logout

- `CSRFProtect` permanece global.
- `LogoutForm` usa Flask-WTF.
- El formulario de barra lateral envía `logout_form.hidden_tag()`.
- Nóminas usa el mismo `csrf_token` firmado.
- No quedan rutas exentas ni campos `_csrf_token`.
- Los errores CSRF muestran página `400` y registran solo la causa, nunca el
  valor del token.

## Verificación realizada

- 69/69 pruebas automatizadas aprobadas.
- 135 plantillas Jinja compiladas.
- 231 rutas Flask registradas.
- 125 formularios POST auditados; 0 sin CSRF.
- Migración sobre base nueva.
- Migración sobre base histórica con permisos revocados, dos obras,
  requisición borrador y cotización existente.
- Ciclo `subir → bajar → subir`.
- `flask db check`: sin operaciones pendientes.
- Backfill histórico validado:
  - Permisos personalizados conservados.
  - Comprador sincronizado con todas las obras.
  - Reserva de borrador reconstruida.
  - Cotización y línea fuente preservadas.

## Archivos principales modificados

- `models.py`
- `compras_models.py`
- `nominas_models.py`
- `forms.py`
- `routes/auth.py`
- `routes/admin.py`
- `routes/supervisor.py`
- `routes/compras.py`
- `routes/comprador_fase5.py`
- `routes/nominas.py`
- `services/actualizacion_operativa.py`
- `services/fase5.py`
- `utils/access.py`
- `utils/project_scope.py`
- `migrations/versions/f4b8c2d9e671_multiobra_requisiciones_consolidadas.py`
- Plantillas de usuarios, dashboard, requisiciones, cotizaciones, OC, obras y
  nóminas.
- `static/css/style.css`
- Pruebas de Compras, Nóminas y actualización operativa.

