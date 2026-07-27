# Actualización del orden de indicadores del reporte

Esta actualización modifica únicamente la presentación del resumen ejecutivo del
**Reporte conjunto previo al cierre**. No cambia tablas, datos ni fórmulas.

## Orden de las tarjetas

La cuadrícula se lee de izquierda a derecha y después continúa hacia abajo:

1. Recurso total requerido
2. Total efectivo
3. Total transferencias
4. Total nóminas
5. Total subcontratos
6. Total proveedores

`Total efectivo` y `Total transferencias` incluyen las salidas de nóminas,
proveedores y subcontratos según el método de pago. Los cheques se agrupan con
transferencias, tal como ya lo hace el sistema.

## Instalación en Windows

Detén Flask con `Ctrl + C` y ejecuta la siguiente línea completa en PowerShell:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\erp_v2_actualizacion_orden_indicadores_reporte.zip" -DestinationPath "C:\erp_v2_nuevo" -Force
```

Después inicia nuevamente el sistema:

```powershell
cd C:\erp_v2_nuevo
.\.venv\Scripts\Activate.ps1
flask run
```

No ejecutes `flask db upgrade`, `flask db migrate` ni `flask db init` para esta
actualización.
