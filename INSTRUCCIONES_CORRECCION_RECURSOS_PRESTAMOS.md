# Instalación · Corrección de recurso requerido por préstamos

Esta actualización se instala directamente sobre **BCH Control con C1, C2,
C3, Fase 5, actualización operativa, CSRF/Logout y multiobra**.

La revisión final de base de datos es:

```text
a9c4e7f2b631 (head)
```

## 1. Detener el sistema

Detén Flask/Gunicorn y evita nuevas capturas mientras se respalda y migra la
base.

Ejemplos:

```bash
sudo systemctl stop bch-control
```

o, si Flask se ejecuta en una terminal, presiona `Ctrl+C`.

## 2. Crear un respaldo completo

Conserva una copia de:

- La carpeta actual del proyecto.
- El archivo `.env`.
- La base SQLite indicada en `DATABASE_URL`.
- La carpeta de adjuntos/cargas.

Ejemplo:

```bash
cp /ruta/bch_control/instance/erp_v2.db \
   /ruta/respaldos/erp_v2_antes_recurso_prestamos_2026-07-24.db
```

No copies una base SQLite mientras el servidor esté escribiendo.

## 3. Aplicar el paquete correcto

### Instalación existente

Usa el ZIP **de actualización acumulativa**. Extráelo en la raíz de BCH
Control y acepta sobrescribir los archivos incluidos.

No reemplaces ni elimines:

- `.env`
- La base `.db`
- `instance/`
- Adjuntos
- El entorno virtual

### Recuperación o instalación limpia

El ZIP **de proyecto completo** sirve como recuperación. Después incorpora el
`.env`, la base y los adjuntos respaldados.

## 4. Conservar la misma `SECRET_KEY`

No cambies `SECRET_KEY`. La sesión, MFA, Flask-Login y los tokens CSRF
dependen de esa clave. Después del reinicio, recarga cualquier pestaña que
hubiera quedado abierta antes de enviar un formulario.

## 5. Dependencias

No se agregaron dependencias. Activa el entorno existente y verifica:

```bash
python -m pip install -r requirements.txt
```

## 6. Ejecutar la migración

Desde la raíz del proyecto:

```bash
flask --app app db current
flask --app app db upgrade
flask --app app db current
flask --app app db check
```

Antes de actualizar, la revisión esperada es:

```text
f4b8c2d9e671
```

Después debe mostrar:

```text
a9c4e7f2b631 (head)
No new upgrade operations detected.
```

No ejecutes:

```text
flask db init
flask db migrate
```

La migración:

- Agrega `loans.project_id` como fotografía de la obra de entrega.
- Rellena ese campo desde `employees.project_id` para préstamos históricos.
- Conserva `loans.metodo_entrega`.
- Conserva `loans.company_id`, que ya es la empresa que entrega el préstamo y
  se expone como `empresa_entrega_id` en el modelo.
- No modifica `loan_payments`, nóminas, saldos, intereses ni permisos.

## 7. Ejecutar pruebas

```bash
python -m unittest discover -s tests -v
```

Resultado esperado:

```text
Ran 74 tests
OK
```

## 8. Reiniciar y validar

Reinicia Flask/Gunicorn y comprueba:

1. Inicia sesión como Administrador.
2. Registra un préstamo en efectivo y otro por transferencia.
3. Aprueba ambos.
4. Abre **Nóminas → Panel**:
   - El capital en efectivo debe aparecer solo en efectivo.
   - El capital transferido debe aparecer solo en transferencias.
5. Abre **Compras → Reportes → Nóminas y Gastos Operativos** y confirma los
   mismos totales.
6. Exporta el Excel y revisa la hoja **Recurso semanal**.
7. Cierra una nómina con retención de préstamo: el requerido no debe crecer.
8. Reabre la misma nómina: el requerido debe permanecer igual.
9. Con un Supervisor multiobra, cambia la obra activa y confirma que solo
   aparezca el recurso de esa obra.
10. Abre el dashboard de Dirección y confirma el consolidado.
11. Abre **Pagos a Proveedores** y verifica que no existan entregas ni abonos
    de préstamos.

## 9. Regla de cálculo instalada

Para cada método:

```text
RECURSO REQUERIDO =
  NÓMINA NETA
  + CAPITAL DE PRÉSTAMOS ENTREGADOS EN LA SEMANA
  + GASTOS OPERATIVOS PAGADOS
  + PAGOS ADICIONALES
  + SUBCONTRATOS
```

No se suma:

- `loan_payments.monto`
- `payroll_lines.descuento_prestamo`
- El interés de `loans.total_pagar`
- El valor nominal de una OC operativa todavía no pagada

## 10. Recuperación

La recuperación recomendada es:

1. Detener el sistema.
2. Restaurar el código respaldado.
3. Restaurar la base `.db` respaldada.
4. Conservar el mismo `.env`.
5. Reiniciar.

No uses `downgrade` si un trabajador ya fue reasignado después de entregar un
préstamo. La migración bloquea ese descenso porque la revisión anterior no
puede conservar la obra histórica de entrega. En producción, restaura siempre
el respaldo completo.
