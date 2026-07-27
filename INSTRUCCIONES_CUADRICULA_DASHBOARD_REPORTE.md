# Corrección de cuadrícula del Dashboard de Reporte

Esta actualización corrige únicamente la presentación del **Reporte conjunto previo al cierre**.

## Resultado

- Los seis indicadores vuelven a mostrarse en una cuadrícula fija de **2 columnas por 3 filas**.
- El orden se conserva de izquierda a derecha y después hacia abajo:
  1. Recurso total requerido | Total efectivo
  2. Total transferencias | Total nóminas
  3. Total subcontratos | Total proveedores
- La impresión mantiene la cuadrícula y permite que las tablas largas continúen en la hoja siguiente, evitando una primera hoja casi vacía.
- No se modifican fórmulas, cálculos, tablas ni datos.

## Instalación

Detén Flask con `Ctrl + C` y ejecuta la línea completa:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\erp_v2_correccion_cuadricula_dashboard_reporte.zip" -DestinationPath "C:\erp_v2_nuevo" -Force
```

Después:

```powershell
cd C:\erp_v2_nuevo
.\.venv\Scripts\Activate.ps1
python -m unittest tests.test_nominas_integracion -v
flask run
```

No ejecutes `flask db upgrade`, `flask db migrate` ni `flask db init` para esta corrección.

Si el navegador conserva el diseño anterior, recarga la página con `Ctrl + F5`.
