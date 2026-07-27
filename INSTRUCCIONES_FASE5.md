# BCH Control — Instalación de Fase 5

## Alcance

Esta actualización agrega los roles ampliados y las funcionalidades de campo
sin sustituir los controles C1, C2 y C3 ya instalados:

- Residente/Supervisor: parte diario, avance físico, certificaciones, NCR,
  RFIs y seguridad HSE.
- Comprador: licitaciones/RFQ, matriz comparativa, adjudicación, contratos,
  órdenes de cambio y conciliación de facturas.
- Almacenista: recepción móvil y discrepancias por faltantes o rechazos.
- CEO/Dirección: dashboard ejecutivo de solo lectura.
- Administrador Financiero: aprobación y seguimiento de conciliaciones,
  pagos y flujo financiero.

La revisión final de base de datos es:

```text
c6d9a4c5880d (head)
```

## 1. Antes de instalar

1. Programa una ventana sin usuarios conectados.
2. Detén el proceso web y cualquier tarea que escriba en la base.
3. Conserva el archivo `.env` actual. No lo copies dentro del ZIP ni lo
   reemplaces con un ejemplo.
4. Comprueba la revisión instalada:

   ```powershell
   flask db current
   ```

   La base esperada antes de esta actualización es `c8d1f4a6b720`. Si aparece
   una revisión anterior, instala primero la actualización acumulativa C1+C2+C3
   o utiliza el proyecto completo de recuperación.

5. Genera un respaldo de PostgreSQL en formato comprimido:

   ```powershell
   pg_dump --format=custom --file bch_antes_fase5.dump $env:DATABASE_URL
   ```

   No escribas la contraseña directamente en el comando. Guarda el respaldo
   cifrado, fuera de la carpeta pública de la aplicación.

6. Respalda también la carpeta de adjuntos privados y el código actualmente
   desplegado.

## 2. Copiar la actualización

1. Extrae el ZIP en una carpeta temporal.
2. Copia su contenido sobre el proyecto de BCH Control.
3. No borres ni reemplaces:

   - `.env`
   - la base de datos
   - respaldos
   - adjuntos existentes

4. Activa el entorno virtual e instala las dependencias declaradas:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

La Fase 5 no agrega una dependencia externa nueva. Conserva `pyotp`, requerido
por el MFA de C3.

## 3. Carpeta privada de evidencias

Los archivos de NCR, RFIs, certificaciones y ofertas se almacenan fuera de
`static`. En producción se recomienda definir una ruta persistente:

```text
FASE5_UPLOAD_FOLDER=/ruta/privada/persistente/bch_fase5
```

La cuenta del proceso web debe poder crear y leer archivos en esa carpeta. Los
adjuntos se entregan únicamente mediante rutas autenticadas y con validación de
permiso y obra.

Si no se configura la variable, BCH Control utilizará
`instance/fase5_uploads`.

## 4. Aplicar la migración

Con las mismas variables de entorno que usa la aplicación:

```powershell
flask db upgrade
flask db current
flask db check
```

Resultado esperado:

```text
c6d9a4c5880d (head)
No new upgrade operations detected.
```

No ejecutes:

```text
flask db init
flask db migrate
```

La migración:

- amplía la restricción de roles para `almacenista` y `ceo`;
- agrega `puede_aprobar` a la matriz configurable;
- crea las tablas de Fase 5, llaves foráneas, restricciones e índices;
- agrega cantidad objetivo, unidad y avance real a las partidas;
- materializa los 11 módulos nuevos para cada usuario existente según su rol;
- conserva sin cambios a los usuarios, obras, nóminas, préstamos y compras;
- deja las OC históricas sin bloqueo retroactivo de conciliación;
- exige conciliación de tres vías a las OC nuevas.

El administrador principal `id=1` conserva acceso total.

## 5. Ejecutar las pruebas

```powershell
python -m unittest -q `
  tests.test_compras `
  tests.test_nominas_integracion `
  tests.test_criticos_c2_c3 `
  tests.test_fase5
```

Resultado esperado:

```text
Ran 44 tests
OK
```

Las nueve pruebas de Fase 5 validan:

1. Parte diario y aislamiento entre obras.
2. Cantidades ejecutadas y recálculo de avance.
3. Apertura y cierre de NCR con evidencia.
4. RFI, notificación y trazabilidad.
5. Certificación aprobada y pago de subcontrato generado una sola vez.
6. Diferencia de factura que bloquea el pago y coincidencia que lo libera.
7. Licitación, ofertas, matriz, adjudicación y contrato versionado.
8. Recepción de almacén y discrepancias.
9. Dashboard ejecutivo agregado y de solo lectura.

## 6. Asignar roles y permisos

En `Administración → Usuarios`:

1. Crea o edita al Almacenista.
2. Asígnale una o más obras y el módulo `Recepción de materiales`.
3. Crea o edita al CEO/Dirección.
4. Mantén habilitado únicamente `Dashboard ejecutivo` para ese perfil.
5. Revisa las obras de cada Comprador y Supervisor.
6. Confirma quiénes pueden `aprobar` certificaciones, permisos de trabajo,
   contratos y conciliaciones.

Configuración inicial recomendada:

| Rol | Acceso principal |
|---|---|
| `admin` | Todo el sistema |
| `admin_financiero` | Pagos, conciliación, tarjetas, nómina financiera y dashboard |
| `comprador` | RFQ, ofertas, adjudicación, contratos y conciliación |
| `supervisor` | Campo, certificaciones, NCR, RFI y HSE |
| `capturista` | Nómina actual |
| `almacenista` | Recepción y discrepancias de sus obras |
| `ceo` | Dashboard ejecutivo, solo lectura |

## 7. Preparación funcional

Antes de capturar avances:

1. Abre cada partida presupuestaria.
2. Define `Cantidad objetivo` y `Unidad de medida`.
3. Vincula los subcontratos a la partida correspondiente.

Antes de registrar pagos de OC nuevas:

1. Emite la OC.
2. Registra la recepción real.
3. Captura la factura en `Compras → Conciliaciones`.
4. Verifica pedido, recepción y factura.
5. Solo una conciliación exacta y aprobada libera el pago.

Para procesar las alertas manualmente:

```powershell
flask fase5-alertas
```

Las alertas automáticas se ejecutan una vez al día y notifican:

- NCR próximas a vencer;
- certificaciones pendientes;
- licitaciones cerradas sin adjudicación.

Las RFIs notifican inmediatamente al destinatario.

## 8. Verificación posterior

Con una cuenta de prueba por rol:

1. Supervisor: registra un parte diario y una medición.
2. Supervisor: abre una NCR con foto y una RFI.
3. Supervisor autorizado: aprueba una certificación dentro del avance real.
4. Comprador: crea una licitación, registra dos ofertas y revisa la matriz.
5. Almacenista: registra una recepción parcial y un faltante.
6. Comprador: comprueba que una factura con diferencia no permite pago.
7. CEO: confirma que solo ve totales y nunca trabajadores, NSS o salarios.
8. Usuario de otra obra: confirma que los documentos ajenos responden 404.

Después de la verificación, reinicia el proceso web y vuelve a habilitar el
acceso de usuarios.

## 9. Recuperación

No uses `flask db downgrade` como método de recuperación después de capturar
información de Fase 5, porque las tablas nuevas deben eliminarse para volver a
la revisión anterior.

Si necesitas regresar:

1. Detén la aplicación.
2. Restaura el código anterior.
3. Restaura el respaldo completo de PostgreSQL.
4. Restaura los adjuntos privados.
5. Verifica `flask db current` antes de reabrir el acceso.

