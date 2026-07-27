# BCH Control · Nóminas, Compras y Operación de Obra

Esta versión conserva la autenticación, usuarios y centros de costo de las
Fases 1–2 del ERP V2 e integra el sistema de nóminas que funcionó en
PythonAnywhere el 17 de julio de 2026.

No usa el prototipo simplificado de “registros semanales” de la antigua Fase 3.
La nómina se captura por obra y trabajador, exactamente con el flujo operativo
del sistema original.

## Funciones recuperadas

- Trabajadores, altas, bajas, cuadrillas y supervisores.
- Asistencia de lunes a viernes y faltas automáticas.
- Sueldo semanal, extras, Infonavit, otros descuentos y vales.
- IMSS como costo patronal fijo o porcentual.
- Préstamos con 5% de interés, antigüedad mínima, aprobación y retención desde
  la semana siguiente.
- Pago mixto: transferencia y efectivo por empresa.
- Ciclo de nómina `borrador → enviada → aprobada → pagada → conciliada`, con
  bloqueo definitivo de reapertura después de ejecutar el pago.
- Partidas, presupuestos, pagos adicionales y gastos de oficina.
- Contratistas, subcontratos, avance y pagos.
- Recurso semanal por método, reporte previo al cierre y exportación Excel.
- Importaciones Excel de trabajadores y subcontratistas; los pagos nuevos de
  proveedores se registran únicamente desde una OC de Compras.
- Auditoría, MFA administrativo, bloqueo de login y alcance de obra validado en
  el servidor.
- NSS enmascarado salvo permiso explícito `ver_nss_completo`.
- Parte diario móvil, cantidades ejecutadas, NCR, RFIs y permisos HSE.
- Certificaciones de subcontrato verificadas contra el avance físico.
- Licitaciones/RFQ, matriz de ofertas, adjudicación y contratos versionados.
- Conciliación de facturas contra OC y recepción antes de liberar el pago.
- Recepción móvil para Almacenista y dashboard ejecutivo para Dirección.

## Estructura principal

| Archivo | Contenido |
|---|---|
| `app.py` | Aplicación Flask, login compartido y registro de Blueprints. |
| `models.py` | Usuarios, centros de costo y bitácora del ERP. |
| `nominas_models.py` | Tablas operativas recuperadas del sistema original. |
| `compras_models.py` | Explosión, histórico proveedor–insumo, requisiciones, cotizaciones, OC, crédito, anticipos, recepciones y SMNC. |
| `fase5_models.py` | Campo, certificaciones, RFIs, HSE, licitaciones, contratos, conciliaciones y discrepancias. |
| `fase5_forms.py` | Formularios Flask-WTF de los flujos nuevos. |
| `routes/nominas.py` | Fórmulas y rutas originales adaptadas al ERP. |
| `routes/compras.py` | Flujo completo y dashboard semanal de Compras. |
| `routes/supervisor.py` | Operación móvil de campo. |
| `routes/comprador_fase5.py` | RFQ, contratos y conciliación de tres vías. |
| `routes/almacenista.py` | Recepción móvil y discrepancias. |
| `routes/ceo.py` | Dashboard ejecutivo de solo lectura. |
| `services/fase5.py` | Archivos privados, notificaciones, avance y reglas compartidas. |
| `utils/access.py` | Política compartida de alcance por obra con respuesta 404. |
| `utils/user_permissions.py` | Límites de rol, autoedición y concesión de permisos. |
| `templates/nominas/` | Interfaz completa de nóminas. |
| `static/nominas/` | CSS y JavaScript del sistema original. |
| `migrations/` | Cadena completa desde una base nueva hasta Nóminas. |
| `tools/importar_pythonanywhere.py` | Importador seguro y opcional de la base anterior. |
| `tests/test_criticos_c2_c3.py` | Regresiones del ciclo financiero, MFA, login, NSS y producción. |

## Inicio rápido con SQLite

En PowerShell, dentro de `C:\erp_v2`:

```powershell
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
flask db upgrade
flask run
```

En `.env`, utiliza una clave secreta real y conserva:

```dotenv
FLASK_ENV=development
DATABASE_URL=sqlite:///erp_v2.db
```

Abre `http://127.0.0.1:5000`. El acceso al módulo está en el botón **Nóminas**
del ERP y su dashboard se encuentra en `/panel`.

## Actualizar una instalación existente

Consulta `INSTRUCCIONES_FASE5.md`. El procedimiento obligatorio
es: detener Flask, respaldar la base, reemplazar el código, instalar
dependencias, ejecutar las pruebas y finalmente `flask db upgrade`.

No ejecutes `flask db init` ni `flask db migrate` en una instalación existente.

## Importar datos de PythonAnywhere

La integración funciona vacía sin la base anterior. Si se necesitan los datos
históricos, descarga primero `instance/nominas.sqlite3` de PythonAnywhere y usa
el importador en modo simulación. La guía contiene los comandos exactos.

## Pruebas

```powershell
python -m unittest tests.test_compras tests.test_nominas_integracion tests.test_criticos_c2_c3 tests.test_fase5 -v
```

Las pruebas usan una base temporal en memoria. No modifican la base del ERP.
La revisión `c6d9a4c5880d` ejecuta 44 pruebas. Incluye las regresiones de C1–C3
y nueve pruebas integrales de los flujos nuevos.

## Fase 5 · Roles ampliados y campo

La Fase 5 añade los roles `almacenista` y `ceo`, amplía Supervisor y Comprador,
y conserva la matriz configurable por acción (`ver`, `crear`, `editar`,
`eliminar`, `aprobar`). Las mutaciones siguen exigiendo permiso y alcance de
obra. Los adjuntos se guardan fuera de `static`, las acciones relevantes se
auditan y el centro de notificaciones alerta RFIs, NCR, certificaciones y
licitaciones pendientes. Consulta `INSTRUCCIONES_FASE5.md`.

## Fase 4 · Compras

La Fase 4 incorpora explosión real de insumos, requisiciones cualquier día,
autorización parcial, cotizaciones, OC consolidadas, anticipos, recepciones,
pagos dirigidos, SMNC e histórico proveedor–insumo. El reporteador general
permite filtrar, configurar columnas y exportar a Excel; también incluye un
reporte semanal de pagos por obra. El dashboard separa comprometido, comprado
y consumido real, además de mostrar líneas de crédito, estados de cuenta y
vencimientos desde la fecha de factura. Cada compra queda vinculada con
Obra → Partida/Subpartida → Insumo y controla importes sin IVA en MXN. La
revisión operativa añade avance exacto de compra por material, proveedor
sugerido, correos de cotización y recepción, edición completa de borradores,
búsqueda de proveedores, filtros acumulativos de OC y separación de roles.
Consulta `INSTRUCCIONES_FASE_4_COMPRAS.md`.

## Alcance fiscal

Este módulo es control administrativo y de costos. No calcula ISR, movimientos
SUA/IDSE, salario base de cotización ni timbrado CFDI. El IMSS es una provisión
patronal configurada por el administrador. Los importes reales deben validarse
con Contabilidad y Seguridad Social.
