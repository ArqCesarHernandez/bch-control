# Instalación única · Partidas semanales y recurso de préstamos

Esta entrega se instala una sola vez sobre **BCH Control con C1, C2, C3,
Fase 5 y actualización operativa**. Incluye de forma acumulativa:

- corrección CSRF y cierre de sesión;
- multiobra, requisiciones, consolidación y direcciones de entrega;
- corrección del recurso requerido por préstamos;
- partida y subpartida por línea de nómina.

No instales previamente ninguno de esos ZIP intermedios. La revisión final de
base de datos es:

```text
b7d2f6a8c914 (head)
```

## 1. Programar una ventana sin capturas

Detén Flask/Gunicorn y pide a los usuarios que cierren BCH Control. No debe
haber altas, cierres de nómina, requisiciones ni pagos durante el respaldo y
la migración.

Ejemplo con systemd:

```bash
sudo systemctl stop bch-control
```

Si Flask se ejecuta en una terminal, usa `Ctrl+C`.

## 2. Registrar la revisión actual

Desde la raíz del proyecto, con el entorno virtual activado:

```bash
flask --app app db current
```

La instalación puede estar en cualquiera de estas revisiones:

```text
e3a7b9c1d245  actualización operativa
f4b8c2d9e671  multiobra
a9c4e7f2b631  recurso de préstamos
```

No continúes si el comando falla o muestra más de una cabeza.

## 3. Crear un respaldo completo

Con el servidor detenido, respalda:

- carpeta completa de BCH Control;
- archivo `.env`;
- base SQLite indicada por `DATABASE_URL`;
- `instance/`, adjuntos y cargas.

Ejemplo:

```bash
cp /ruta/bch_control/instance/erp_v2.db \
   /ruta/respaldos/erp_v2_antes_partidas_semanales_2026-07-24.db
```

Comprueba que el archivo respaldado existe y tiene un tamaño razonable. No
copies SQLite mientras el servidor esté escribiendo.

## 4. Extraer el paquete correcto

Para actualizar la instalación actual usa únicamente:

```text
erp_v2_bch_control_partidas_prestamos_integrado_actualizacion_acumulativa.zip
```

Extráelo en la raíz de BCH Control y acepta sobrescribir los archivos
incluidos.

No reemplaces ni elimines:

- `.env`;
- la base `.db`;
- `instance/`;
- adjuntos;
- el entorno virtual.

El ZIP de proyecto completo es solo para recuperación o instalación limpia.
Después de extraerlo debes reincorporar tu `.env`, base y adjuntos respaldados.

## 5. Conservar la misma `SECRET_KEY`

No cambies `SECRET_KEY`. Flask-Login, MFA y Flask-WTF dependen de ella.
Después del reinicio, recarga las pestañas que hubieran quedado abiertas para
obtener un token CSRF vigente.

## 6. Verificar dependencias

No se agregaron dependencias. Con el entorno virtual activo:

```bash
python -m pip install -r requirements.txt
```

## 7. Aplicar las migraciones

Ejecuta exactamente:

```bash
flask --app app db current
flask --app app db upgrade
flask --app app db current
flask --app app db check
```

El resultado final debe incluir:

```text
b7d2f6a8c914 (head)
No new upgrade operations detected.
```

No ejecutes:

```text
flask db init
flask db migrate
```

Según la revisión inicial, Alembic aplicará solo lo pendiente:

1. `f4b8c2d9e671`: multiobra, reservas, consolidación y direcciones.
2. `a9c4e7f2b631`: fotografía de obra en préstamos.
3. `b7d2f6a8c914`: `partida_id` y `subpartida_id` en líneas de nómina.

La última migración:

- vuelve nullable `payroll_lines.budget_item_id`;
- agrega las dos llaves foráneas e índices nuevos;
- convierte cada asignación histórica raíz o hija sin perderla;
- conserva `budget_item_id` como ítem efectivo compatible;
- normaliza métodos históricos de préstamo a efectivo/transferencia;
- agrega la restricción de método de entrega.

`employees.budget_item_id` ya era nullable. Se conserva solo por compatibilidad,
pero la aplicación lo deja vacío y no lo usa en fórmulas.

## 8. Ejecutar la regresión

```bash
python -m unittest discover -s tests -v
```

Resultado esperado:

```text
Ran 75 tests
OK
```

## 9. Reiniciar

Ejemplo:

```bash
sudo systemctl start bch-control
sudo systemctl status bch-control
```

Revisa el log de arranque y confirma que no existan errores de esquema,
relaciones o plantillas.

## 10. Validación funcional posterior

### Trabajadores y nómina

1. Abre **Trabajadores → Nuevo**.
2. Confirma que no se soliciten partida ni subpartida.
3. Crea una nómina para una obra con una partida que tenga subpartidas.
4. Confirma que cada trabajador muestre ambos selectores.
5. Intenta guardar sin partida y verifica el mensaje:

   ```text
   Debe asignar una partida a cada trabajador antes de guardar.
   ```

6. Elige una partida con hijos e intenta guardar sin subpartida; debe aparecer
   el mismo bloqueo.
7. Asigna partida/subpartida, guarda y aprueba.
8. Abre la semana siguiente y confirma la sugerencia editable.
9. Cambia la partida en esa semana y verifica que la anterior no cambie.
10. Exporta Excel y revisa las columnas **Partida** y **Subpartida**.
11. Filtra el reporte por la partida padre y por una subpartida.
12. Como Supervisor multiobra, cambia la obra activa y confirma que no aparezcan
    partidas de otra obra.

### Préstamos y recurso

1. Registra y aprueba un préstamo en efectivo.
2. Registra y aprueba otro por transferencia.
3. Abre el panel semanal y confirma que cada capital aparezca una sola vez en
   su método.
4. Cierra una nómina con abono de préstamo; el requerido no debe aumentar.
5. Reabre la nómina; revertir el abono tampoco debe cambiar el requerido.
6. Revisa el panel de proveedores; no debe contener entregas ni abonos de
   préstamos.
7. Verifica el dashboard del Supervisor, Dirección/CEO y la hoja Excel
   **Recurso semanal**.

La fórmula instalada por método es:

```text
RECURSO REQUERIDO =
  NÓMINA NETA
  + CAPITAL DE PRÉSTAMOS ENTREGADOS EN LA SEMANA
  + GASTOS OPERATIVOS PAGADOS
  + PAGOS ADICIONALES
  + SUBCONTRATOS
```

No se suman `loan_payments`, retenciones, intereses ni `loans.total_pagar`.

## 11. Recuperación

Ante un problema:

1. Detén el sistema.
2. Restaura la carpeta de código respaldada.
3. Restaura la base `.db` respaldada.
4. Conserva el mismo `.env`.
5. Reinicia y verifica.

No uses `downgrade` como mecanismo habitual de recuperación. La migración lo
bloquea si existen borradores sin partida porque la revisión anterior no puede
representarlos; la revisión de préstamos también protege la obra histórica.
En producción, la reversión segura es restaurar código y base del mismo
respaldo.
