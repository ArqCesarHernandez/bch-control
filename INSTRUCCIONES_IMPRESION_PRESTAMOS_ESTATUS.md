# Corrección de impresión: Préstamos y estatus

Esta actualización corrige exclusivamente la tabla **7. Préstamos y estatus** del
Reporte conjunto previo al cierre.

## Qué cambia

- La tabla usa todo el ancho disponible de la hoja.
- Sus nueve columnas tienen proporciones fijas para evitar que el extremo derecho
  quede recortado.
- Los encabezados y textos largos pueden dividirse en varias líneas al imprimir.
- La tipografía se compacta solamente en impresión; la vista normal no cambia.
- Se conservan la cuadrícula del dashboard, el orden de los seis indicadores y
  todos los cálculos existentes.

No modifica la base de datos y no requiere migraciones.

## Instalación

Detén Flask con `Ctrl + C` y ejecuta la siguiente línea completa en PowerShell:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\erp_v2_correccion_impresion_prestamos_estatus.zip" -DestinationPath "C:\erp_v2_nuevo" -Force
```

Después inicia nuevamente el sistema:

```powershell
cd C:\erp_v2_nuevo
.\.venv\Scripts\Activate.ps1
python -m unittest tests.test_nominas_integracion -v
flask run
```

Actualiza el navegador con `Ctrl + F5` y vuelve a usar **Imprimir / Guardar PDF**.
La hoja se configura automáticamente en orientación horizontal.
