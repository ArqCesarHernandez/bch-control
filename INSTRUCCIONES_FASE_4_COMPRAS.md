# BCH Control — actualización acumulativa de flujos e identidad corporativa

Esta actualización acumulativa se instala sobre la revisión
`b6e1c9f4a820` que ya está funcionando. Conserva los registros actuales y
agrega la migración de tipos de OC, permisos y tarjetas, además de la nueva
interfaz corporativa y el endurecimiento crítico de autorización. No es
necesario instalar primero el ZIP anterior
`erp_v2_oc_tipos_permisos_tarjetas_actualizacion.zip`.

La revisión final debe quedar en:

```text
a4c7e2f9b615 (head)
```

## Cambios incluidos

### Identidad BCH Control

- El sistema se identifica como **BCH Control** en todas las pestañas del
  navegador, el sidebar y la página de acceso.
- Inicio, Administración, Nóminas y Compras comparten un sidebar corporativo
  de 250 px, navegación por permisos, estado activo y versión móvil
  colapsable.
- El fondo azul oscuro del sidebar y el contraste de textos e íconos quedan
  fijados frente a los estilos responsivos de Bootstrap, tanto en escritorio
  como en móvil.
- El encabezado incluye breadcrumb y título de página; el usuario y el cierre
  de sesión permanecen en la parte inferior del sidebar.
- La interfaz usa Inter, azul corporativo `#1a3a5c`, naranja `#e87e2f`, fondo
  `#f5f6f8` y sidebar `#0d2137`.
- Se integran tarjetas, tablas, controles y botones responsivos, además de
  conservar el formato vertical compacto de impresión.
- Se incluyen `static/img/logo.png` para el acceso y
  `static/img/logo-sidebar.png` para la navegación. Si alguna imagen falta,
  aparece automáticamente el nombre BCH Control con un ícono de construcción.

### Órdenes y requisiciones separadas

- Las requisiciones y OC ahora se clasifican como `COMPRAS` u `OPERACIONES`.
- Los registros históricos se conservan como `COMPRAS` para no cambiar su
  tratamiento contable.
- Las OC de Compras mantienen el flujo requisición → cotización → OC →
  recepción → pago y solo aparecen en los reportes de Compras.
- Las OC de Operaciones pueden ser creadas por Supervisor o Administrador. Un
  Supervisor las envía a autorización administrativa antes de emitirlas; no
  pasan por la bandeja del Comprador.
- Una OC de Operaciones únicamente acepta insumos marcados como operativos:
  agregados, tierra para relleno, arena, retiro de escombro, grava, agua,
  renta por hora de retroexcavadora/excavadora/bobcat y gastos de oficina.
- El catálogo de insumos permite activar `Insumo de Operaciones` y elegir su
  categoría. La migración solo marca automáticamente coincidencias claras;
  conviene revisar el catálogo después de instalar.
- Las requisiciones de Operaciones quedan fuera de la bandeja del Comprador y
  las de Compras quedan fuera de la bandeja operativa del Supervisor.

### Reportes del Administrador

- **Nóminas y Gastos Operativos:** nóminas, préstamos y OC de Operaciones,
  agrupados por obra y semana, con detalle de cada gasto.
- **Pagos a Proveedores:** OC de Compras, pagos de proveedores, créditos y
  pagos de tarjetas empresariales.
- Cada OC guarda una categoría de pago: `NOMINA` para una OC operativa pagada
  con fondo de nómina o `COMPRAS` para el flujo normal. Los pagos de crédito se
  identifican como `CREDITO` en los filtros.
- El reporteador general y el reporte semanal continúan mostrando únicamente
  el flujo de Compras, evitando mezclar gastos operativos.

### Permisos configurables por usuario

- Se agrega la tabla `permisos`, con permisos de ver, crear, editar y eliminar
  por usuario y módulo.
- Al crear un usuario se asignan valores predeterminados por rol:
  - Administrador: acceso total.
  - Supervisor: Nómina, requisiciones de Operaciones y OC de Operaciones; sin
    acceso a OC de Compras ni proveedores.
  - Comprador: Compras, requisiciones de Compras, proveedores y reportes; sin
    Nómina.
  - Costos: reportes y centros de costo; lectura en Compras y requisiciones.
  - Capturista: Nómina, según el alcance ya existente.
- En **Administración → Usuarios → Editar** aparece la matriz de permisos. Un
  Administrador puede cambiar las casillas de otras cuentas sin modificar el
  rol base; su propia matriz permanece en solo lectura.
- Rutas, botones y menús comprueban los permisos individuales en el servidor y
  en la interfaz.

### Seguridad de usuarios y alcance de obra

- Ninguna cuenta puede cambiar su propio rol, sus propios permisos ni sus
  propias obras asignadas, aunque manipule el formulario o invoque una ruta
  directamente.
- Un usuario delegado solo puede conceder permisos que él mismo posee; un
  perfil no administrador tampoco puede crear o promover otro administrador.
- El Comprador deja de tener alcance global implícito y opera únicamente las
  obras que tiene asignadas. Los compradores existentes reciben durante la
  migración asignaciones explícitas a las obras activas que ya podían operar.
- Nómina y Compras reutilizan `verificar_acceso_obra(...)`. Guardar, cerrar,
  reabrir o eliminar una nómina, y editar, emitir, autorizar, cancelar o
  recibir una OC ajena responden `404` sin modificar el documento.
- Administración muestra rol, permisos y alcance como solo lectura al editar
  la cuenta con la que se inició sesión.

### Tarjetas de crédito

- Se agregan tarjetas por empresa pagadora con número enmascarado, fecha de
  corte, fecha de pago, límite y saldo actual.
- El ERP solo conserva los últimos cuatro dígitos; no almacena el número
  completo.
- Cada pago registra fecha, monto, saldos anterior/nuevo, referencia, notas y
  usuario capturista.
- El dashboard muestra alerta cuando faltan tres días o menos para pagar una
  tarjeta con saldo, incluida una tarjeta ya vencida.
- La revisión diaria genera notificaciones idempotentes para los usuarios con
  acceso a Tarjetas.

### Filtros e interfaz

- Requisiciones: obra, solicitante, tipo y estado.
- Órdenes: obra, proveedor, tipo de OC, estado y rango de fechas.
- Pagos: proveedor, rango de fechas y tipo `NOMINA`, `COMPRAS` o `CREDITO`.
- Proveedores: empresa, nombre y estado de crédito activo/vencido.
- Las observaciones del Supervisor aparecen en una columna separada y con
  texto secundario.
- Requisiciones y OC usan tablas compactas, márgenes de impresión reducidos y
  orientación vertical.
- Todas las pantallas incluyen un botón visible para volver a su lista o panel.

Se conservan el cierre exacto de requisiciones, cotizaciones por correo,
recepciones parciales, edición de borradores, histórico proveedor–insumo,
reporteador, anticipos, SMNC, crédito desde fecha de factura y las demás
funciones de la revisión `b6e1c9f4a820`.

## Cambios de base de datos

La migración `e9a3f7c2d614`:

- crea `permisos` y asigna nueve módulos a cada usuario existente;
- agrega clasificación operativa a `supply_items`;
- agrega tipo a `purchase_requisitions`;
- agrega tipo, categoría y autorización a `purchase_orders`;
- crea `tarjetas_credito` y `tarjetas_credito_pagos`;
- agrega el contador de tarjetas por vencer a la bitácora diaria.

La migración `a4c7e2f9b615` convierte el acceso histórico de cada Comprador en
asignaciones explícitas dentro de `user_projects`. No elimina ni modifica
requisiciones, OC, nóminas, pagos o permisos existentes.

La migración fue validada sobre SQLite con usuarios de los cinco roles y con
requisición y OC existentes. También fue probada bajando a `b6e1c9f4a820` y
volviendo a subir sin llaves foráneas rotas.

## Instalación en Windows

Detén Flask con `Ctrl + C` y ejecuta en PowerShell:

```powershell
New-Item -ItemType Directory -Force C:\erp_v2_backups
Copy-Item C:\erp_v2_nuevo\instance\erp_v2.db C:\erp_v2_backups\erp_v2_antes_bch_control.db

Expand-Archive -Path "$env:USERPROFILE\Downloads\erp_v2_bch_control_seguridad_critica_actualizacion_acumulativa.zip" -DestinationPath "C:\erp_v2_nuevo" -Force

cd C:\erp_v2_nuevo
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
flask db upgrade
flask db current
flask db check
```

El resultado esperado es:

```text
a4c7e2f9b615 (head)
No new upgrade operations detected.
```

Ejecuta la regresión y reinicia:

```powershell
python -m unittest tests.test_compras tests.test_nominas_integracion -v
flask run
```

La suite ejecuta **28 pruebas** y debe terminar en `OK`. Después actualiza el
navegador con `Ctrl + F5`.

No ejecutes `flask db init` ni `flask db migrate`.

## Verificación funcional recomendada

1. Entra como Administrador a **Usuarios → Editar**, cambia un permiso de una
   cuenta de prueba y confirma que el menú y la ruta respeten la modificación.
2. En el catálogo, revisa los insumos marcados como Operaciones y clasifica los
   que falten.
3. Como Supervisor, crea una requisición de Operaciones y verifica que solo
   permita insumos operativos.
4. Convierte la requisición en OC, envíala a autorización y confirma como
   Administrador que pueda emitirse y pagarse con categoría Nómina.
5. Entra como Comprador y confirma que esa requisición y OC operativas no
   aparezcan en su bandeja.
6. Crea una requisición y OC de Compras y confirma que aparezcan en Pagos a
   Proveedores, no en Gastos Operativos.
7. Registra una tarjeta con saldo y fecha de pago dentro de tres días; revisa
   la alerta del dashboard y registra un pago parcial.
8. Combina los filtros de requisiciones, OC, pagos y proveedores.
9. Imprime una requisición y una OC para verificar el formato vertical compacto.
10. Revisa el login, abre el sidebar desde un teléfono o una ventana angosta y
    confirma que el botón hamburguesa muestre el mismo menú permitido por rol.
11. Confirma que cada Comprador tenga asignadas las obras correctas en
    **Administración → Usuarios**; la migración conserva inicialmente todas
    las obras activas que podía operar antes del parche.

## Cambiar el logotipo posteriormente

El paquete ya incluye los dos logotipos proporcionados. Para sustituirlos sin
modificar código:

1. Guarda el logotipo completo como
   `C:\erp_v2_nuevo\static\img\logo.png`.
2. Guarda la versión corta como
   `C:\erp_v2_nuevo\static\img\logo-sidebar.png`.
3. Usa archivos PNG con fondo transparente. El tamaño se adapta mediante CSS;
   se recomienda alrededor de 200 × 60 px para una versión horizontal.
4. Reinicia Flask y presiona `Ctrl + F5` en el navegador.

Si solo existe un logotipo, se puede copiar con ambos nombres. Si el archivo no
puede cargarse, BCH Control muestra automáticamente el respaldo de texto e
ícono.

## Protección de datos

- El ZIP no incluye bases de datos, `.env`, credenciales ni entornos virtuales.
- Los registros actuales conservan el tipo `COMPRAS` y sus importes, estados y
  relaciones no se recalculan.
- Conserva el respaldo `erp_v2_antes_bch_control.db` hasta terminar la
  verificación funcional.
- Si una instalación se interrumpe, conserva el mensaje completo de PowerShell
  y no vuelvas a ejecutar `db init` ni `db migrate`.
