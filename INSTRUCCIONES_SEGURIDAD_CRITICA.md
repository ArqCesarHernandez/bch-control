# BCH Control — corrección crítica de autorización

## Resultado

La revisión final es `a4c7e2f9b615`. El parche evita la autoelevación de
privilegios y aplica alcance de obra antes de mutar nóminas u órdenes de
compra. Una solicitud sobre una obra ajena responde `404` y no modifica datos.

## Cambios de código

### Política única de obra

`utils/access.py` define la función compartida:

```python
def verificar_acceso_obra(usuario, centro_costo_id):
    if usuario.acceso_global_obras:
        return True
    if usuario.centro_costo_id == centro_costo_id:
        return True
    if any(obra.id == centro_costo_id for obra in usuario.projects):
        return True
    abort(404)
```

`routes/nominas.py` la ejecuta al guardar, agregar o quitar líneas, cerrar,
reabrir y eliminar una nómina. `routes/compras.py` la ejecuta antes de editar,
emitir, autorizar, cancelar y registrar la recepción de una OC. La validación
de obra ocurre antes de cualquier cambio de estado o escritura en la base.

### Administración de usuarios

`utils/user_permissions.py` incorpora tres límites:

- la cuenta activa no puede cambiar su propio rol;
- la cuenta activa no puede cambiar sus propios permisos ni sus propias obras;
- solo se puede activar para otra cuenta un permiso que el actor ya posee.

El rol `admin` solo puede ser otorgado por otro administrador. Un usuario no
administrador tampoco puede editar una cuenta administradora ni asignar una
obra fuera de su propio alcance.

Ambas rutas quedan cubiertas:

```text
/admin/usuarios/<id>/editar
/usuarios/<id>/editar
```

En la interfaz, el rol, la matriz de permisos y las obras aparecen como solo
lectura cuando una persona abre su propia cuenta. La seguridad real permanece
en el servidor aunque se modifique el HTML.

### Alcance del Comprador

El rol Comprador ya no obtiene acceso global por el nombre del rol. Los
compradores nuevos deben recibir una obra activa. La migración
`a4c7e2f9b615` crea para los compradores existentes asignaciones explícitas a
las obras activas que podían operar antes del parche, evitando interrumpir su
trabajo al instalar.

Después de actualizar, el Administrador debe revisar esas asignaciones en
**Administración → Usuarios** y conservar únicamente las obras que correspondan
a cada Comprador.

## Pruebas negativas

Se agregaron pruebas que confirman que:

1. Un Supervisor no puede reabrir una nómina cerrada de otra obra: recibe
   `404` y la nómina permanece `CERRADA`.
2. Un Comprador no puede cancelar una OC de otra obra: recibe `404` y la OC
   permanece `BORRADOR`.
3. Un usuario con `usuarios.editar` no puede cambiarse a `admin` mediante
   ninguna de las dos rutas.
4. Ese usuario tampoco puede activar en otra cuenta un permiso que él no posee.

La regresión completa ejecuta 28 pruebas:

```powershell
python -m unittest tests.test_compras tests.test_nominas_integracion -v
```

Resultado esperado:

```text
Ran 28 tests
OK
```

## Instalación

Detén Flask y respalda primero la base:

```powershell
New-Item -ItemType Directory -Force C:\erp_v2_backups
Copy-Item C:\erp_v2_nuevo\instance\erp_v2.db C:\erp_v2_backups\erp_v2_antes_seguridad_critica.db

Expand-Archive -Path "$env:USERPROFILE\Downloads\erp_v2_bch_control_seguridad_critica_actualizacion_acumulativa.zip" -DestinationPath "C:\erp_v2_nuevo" -Force

cd C:\erp_v2_nuevo
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask db upgrade
flask db current
flask db check
python -m unittest tests.test_compras tests.test_nominas_integracion -v
flask run
```

El resultado de migración debe ser:

```text
a4c7e2f9b615 (head)
No new upgrade operations detected.
```

No ejecutes `flask db init` ni `flask db migrate`.
