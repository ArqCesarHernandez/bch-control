# Instalación de Nóminas original dentro del ERP V2

## Qué se conserva

- El administrador inicial y las cuentas creadas en el ERP.
- Los centros de costo de la Fase 2.
- La bitácora existente.
- La base SQLite actual.
- Si la Fase 3 simplificada llegó a aplicarse, su tabla queda intacta pero el
  ERP deja de usarla. No se borra automáticamente.

## 1. Detener y respaldar

Detén Flask con `Ctrl+C`. Después, desde PowerShell:

```powershell
New-Item -ItemType Directory -Force C:\erp_v2_backups
Copy-Item C:\erp_v2\instance\erp_v2.db C:\erp_v2_backups\erp_v2_antes_nominas_original.db
```

No continúes sin confirmar que el archivo de respaldo existe.

## 2. Instalar el paquete de actualización

Extrae `erp_v2_nominas_integracion_actualizacion.zip` dentro de `C:\erp_v2` y
acepta reemplazar archivos:

```powershell
Expand-Archive `
  -Path "$env:USERPROFILE\Downloads\erp_v2_nominas_integracion_actualizacion.zip" `
  -DestinationPath C:\erp_v2 `
  -Force
```

El paquete no contiene `.env`, `.venv`, `instance` ni bases de datos.

## 3. Dependencias y validación

```powershell
cd C:\erp_v2
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m py_compile app.py models.py nominas_models.py forms.py routes\nominas.py
python -m unittest tests.test_nominas_integracion -v
```

Las pruebas deben terminar con `OK`.

## 4. Aplicar la migración

```powershell
flask db upgrade
```

No ejecutes `flask db init` ni `flask db migrate`. La actualización incluye la
migración `8b6d4f2a1c90` y un marcador compatible para la Fase 3 cancelada.

Los centros existentes reciben códigos provisionales `CC-0001`, `CC-0002`,
etc. Después puedes cambiarlos por códigos reales desde Administración.

## 5. Iniciar y verificar

```powershell
flask run
```

1. Inicia sesión con el administrador existente.
2. Abre **Nóminas**.
3. Confirma que aparezcan dashboard, obras, trabajadores, préstamos y reportes.
4. Abre **Obras y partidas** y edita el código de cada centro si es provisional.
5. Crea una partida de mano de obra.
6. Registra un trabajador de prueba.
7. Crea una nómina de una semana y verifica la precarga.

## 6. Datos históricos de PythonAnywhere — opcional

Primero descarga desde PythonAnywhere:

```text
instance/nominas.sqlite3
```

Guárdala, por ejemplo, en:

```text
C:\erp_v2_import\nominas_pythonanywhere.sqlite3
```

Con Flask detenido, ejecuta primero la simulación:

```powershell
python tools\importar_pythonanywhere.py `
  --source C:\erp_v2_import\nominas_pythonanywhere.sqlite3 `
  --erp-db C:\erp_v2\instance\erp_v2.db
```

Debe decir `SIMULACIÓN; NO SE GUARDÓ NADA`. Revisa los conteos. Solo si son
correctos, aplica:

```powershell
python tools\importar_pythonanywhere.py `
  --source C:\erp_v2_import\nominas_pythonanywhere.sqlite3 `
  --erp-db C:\erp_v2\instance\erp_v2.db `
  --apply
```

La herramienta crea otro respaldo antes de escribir y se niega a mezclar datos
si el módulo destino ya contiene nóminas o movimientos.

## Recuperación

Si la aplicación no coincide con lo esperado:

1. Detén Flask.
2. Conserva la base que presentó el problema.
3. Copia el respaldo sobre `instance\erp_v2.db`.
4. No ejecutes `flask db downgrade`, porque eliminaría tablas del módulo.

