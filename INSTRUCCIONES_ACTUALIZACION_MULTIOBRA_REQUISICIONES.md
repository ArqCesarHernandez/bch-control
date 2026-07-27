# Instalación · Multiobra, Requisiciones y CSRF/Logout

Esta actualización se instala directamente sobre **BCH Control C1 + C2 + C3
+ Fase 5 + Actualización operativa**. Incluye también la corrección
**CSRF/Logout** que no se había instalado; no apliques ese ZIP por separado.

La revisión final de base de datos es:

```text
f4b8c2d9e671 (head)
```

## 1. Detener el sistema

Detén Flask/Gunicorn y evita que otros usuarios capturen datos durante el
respaldo y la migración.

Ejemplos:

```bash
sudo systemctl stop bch-control
```

o, si se ejecuta en una terminal, presiona `Ctrl+C`.

## 2. Respaldar antes de sobrescribir

Conserva una copia completa de:

- La carpeta actual del proyecto.
- El archivo `.env`.
- La base SQLite indicada en `DATABASE_URL`.
- La carpeta de adjuntos/cargas.

Ejemplo para SQLite en Linux:

```bash
cp /ruta/bch_control/instance/erp_v2.db \
   /ruta/respaldos/erp_v2_antes_multiobra_2026-07-24.db
```

En Windows, copia manualmente el archivo `.db` con Flask detenido. No copies
una base SQLite mientras el servidor esté escribiendo.

## 3. Aplicar el ZIP correcto

### Actualizar la instalación existente

Extrae el ZIP acumulativo en la raíz del proyecto actual y acepta sobrescribir
los archivos incluidos.

No reemplaces ni elimines:

- `.env`
- La base `.db`
- `instance/`
- La carpeta de adjuntos
- El entorno virtual

### Recuperación completa

El ZIP de proyecto completo sirve para una instalación limpia o recuperación.
Copia después tu `.env`, base y adjuntos respaldados.

## 4. Conservar la misma SECRET_KEY

No cambies `SECRET_KEY`. Flask-WTF firma el token CSRF con esa clave y
Flask-Login la usa para la sesión. Cambiarla durante la actualización invalida
sesiones y formularios abiertos.

La corrección integrada unifica todos los formularios POST bajo el campo
firmado `csrf_token`. Ya no existe el mecanismo heredado `_csrf_token`.

## 5. Dependencias

No se agregaron dependencias. Activa el entorno existente e instala el archivo
de requisitos solo para verificar que esté completo:

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

Antes de actualizar, la revisión esperada es `e3a7b9c1d245`. Después debe
mostrar:

```text
f4b8c2d9e671 (head)
No new upgrade operations detected.
```

No ejecutes:

```text
flask db init
flask db migrate
```

La migración:

- Conserva `user_projects` y todas sus asignaciones.
- Sincroniza automáticamente todos los compradores con todas las obras.
- Conserva requisiciones, cotizaciones, OC, pagos, recepciones y permisos.
- Calcula la reserva de borradores que ya estuvieran abiertos.
- Agrega trazabilidad a las cotizaciones históricas.
- No sobrescribe permisos personalizados existentes.

## 7. Ejecutar pruebas

```bash
python -m unittest -q \
  tests.test_compras \
  tests.test_nominas_integracion \
  tests.test_criticos_c2_c3 \
  tests.test_fase5 \
  tests.test_actualizacion_operativa
```

Resultado esperado:

```text
Ran 69 tests
OK
```

## 8. Reiniciar y validar

Reinicia Flask/Gunicorn y realiza estas comprobaciones:

1. Inicia sesión como Administrador.
2. Ve a **Administración → Usuarios → Editar** y asigna dos obras a un
   Supervisor.
3. Inicia sesión como ese Supervisor y cambia la obra activa en la barra
   superior.
4. Confirma que dashboard, nóminas, requisiciones y OC muestren únicamente la
   obra activa.
5. Crea una requisición con dos materiales y guárdala como borrador.
6. Comprueba en la explosión que ambos saldos quedaron reservados.
7. Cancela el borrador y confirma que las cantidades regresaron.
8. Entra como Comprador y revisa el contador de pendientes por obra.
9. Completa cualquier aviso de dirección de entrega.
10. Selecciona dos requisiciones y usa **Consolidar para cotización**.
11. Abre una OC, confirma su dirección y revisa la vista de impresión.
12. Captura una nómina y selecciona la partida de cada trabajador.
13. Cierra sesión; el POST `/logout` debe redirigir a `/login`, no responder
    `400`.

Si el navegador mantenía una página abierta antes del reinicio, recárgala
antes de enviar el formulario para recibir un token CSRF de la sesión vigente.

## 9. Recuperación

La recuperación recomendada es:

1. Detener el sistema.
2. Restaurar la carpeta de código respaldada.
3. Restaurar la base `.db` respaldada.
4. Conservar el mismo `.env`.
5. Reiniciar.

La migración admite `downgrade` únicamente cuando no existen direcciones o
cotizaciones consolidadas nuevas. Esa protección evita borrar datos que la
revisión anterior no puede representar. Para una recuperación productiva usa
siempre el respaldo completo, no un `downgrade` destructivo.

