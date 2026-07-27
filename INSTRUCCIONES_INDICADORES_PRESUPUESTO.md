# Actualización de indicadores presupuestales

Esta actualización alinea los cinco indicadores del dashboard de cada proyecto:

1. **Total:** presupuesto total de la obra.
2. **Consumido real:** costo de las nóminas cerradas, incluido el IMSS patronal.
3. **Comprometido:** suma del presupuesto de todas las subpartidas.
4. **Disponible real:** disponible dentro de las partidas más el presupuesto que aún no se distribuye a partidas. Equivale a `Total - Comprometido`.
5. **Disponible comprometido:** presupuesto de subpartidas que todavía no se consume. Equivale a `Comprometido - Consumido real`.

Las nóminas en borrador no reducen el consumido real. Los pagos adicionales, gastos de oficina y pagos a subcontratistas conservan sus controles y reportes propios, pero no se mezclan con estos cinco indicadores.

## Instalación

1. Detén Flask con `Ctrl + C`.
2. Respalda la base de datos:

```powershell
New-Item -ItemType Directory -Force C:\erp_v2_backups
Copy-Item C:\erp_v2_nuevo\instance\erp_v2.db C:\erp_v2_backups\erp_v2_antes_indicadores.db
```

3. Extrae el ZIP dentro del proyecto:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\erp_v2_actualizacion_indicadores_presupuesto.zip" -DestinationPath C:\erp_v2_nuevo -Force
```

4. Activa el entorno y valida:

```powershell
cd C:\erp_v2_nuevo
.\.venv\Scripts\Activate.ps1
python -m py_compile routes\nominas.py tests\test_nominas_integracion.py
python -m unittest tests.test_nominas_integracion -v
```

El resultado de las pruebas debe terminar en `OK`.

5. Inicia el sistema:

```powershell
flask run
```

No ejecutes `flask db init`, `flask db migrate` ni `flask db upgrade`: esta actualización no cambia la base de datos.

