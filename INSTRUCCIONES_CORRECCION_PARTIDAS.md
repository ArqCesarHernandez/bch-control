# Corrección de acceso a partidas

Esta actualización hace visible la administración de partidas desde:

- El panel principal del ERP.
- El listado de Centros de costo.
- El listado de Obras y partidas del módulo de Nóminas.
- La pantalla de Nueva nómina.
- El detalle de una obra sin partidas.

Además, al crear un centro de costo nuevo, el sistema abre directamente su
control para registrar la primera partida.

## Instalación en Windows

1. Detén Flask con `Ctrl + C`.
2. Extrae `erp_v2_correccion_acceso_partidas.zip` dentro de
   `C:\erp_v2_nuevo`, aceptando el reemplazo de archivos.
3. Desde PowerShell ejecuta:

```powershell
cd C:\erp_v2_nuevo
.\.venv\Scripts\Activate.ps1
python -m py_compile routes\admin.py
flask run
```

No ejecutes `flask db migrate` ni `flask db upgrade`: esta corrección no
modifica tablas ni datos.

## Uso

Como administradora, abre **Centros de costo** y pulsa **Agregar partidas** en
la obra correspondiente. Para que una partida pueda utilizarse en trabajadores
y nóminas, selecciona la categoría **Mano de obra** y déjala activa.

