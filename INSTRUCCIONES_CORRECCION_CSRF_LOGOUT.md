# BCH Control — corrección CSRF y cierre de sesión

## Diagnóstico

`POST /logout` se valida antes de ejecutar `routes/auth.py::logout`.
Cuando Flask-WTF no recibe un token firmado válido para la sesión actual,
`CSRFProtect` responde `400 Bad Request`; por eso `logout_user()` no llega a
ejecutarse.

La revisión acumulativa tenía dos formatos de token:

- `csrf_token`, firmado y validado por Flask-WTF.
- `_csrf_token`, generado por el módulo heredado de Nóminas.

El formulario de logout ya utilizaba correctamente `LogoutForm.hidden_tag()`,
pero la coexistencia de ambos mecanismos hacía frágiles las instalaciones
parciales y las plantillas heredadas. La corrección deja una sola fuente de
verdad: Flask-WTF.

## Cambios

- `app.py`
  - Nóminas ya no está exento de `CSRFProtect`.
  - Todos los Blueprints quedan cubiertos por la misma validación.
  - Los rechazos CSRF registran método, ruta y causa, nunca el token.
- `routes/nominas.py`
  - Se eliminó el generador y validador `_csrf_token` heredado.
- `templates/nominas/`
  - Todos los formularios envían `csrf_token` firmado.
- `templates/400.html`
  - Se agregó una respuesta clara para formularios vencidos o inválidos.
- `tests/test_nominas_integracion.py`
  - Prueba de logout válido e inválido.
  - Prueba de CSRF real en Nóminas.
  - Auditoría automática de todas las plantillas POST.

No cambian modelos, tablas, migraciones, MFA, sesiones, roles ni permisos.

## Instalación

1. Detén Flask.
2. Respalda el proyecto y la base de datos.
3. Extrae el ZIP de actualización sobre la revisión operativa actual,
   conservando tu `.env`, base de datos y adjuntos.
4. Conserva exactamente la misma `SECRET_KEY`; no generes otra al reiniciar.
5. Activa el entorno virtual y ejecuta:

```powershell
cd C:\ruta\de\bch-control
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m unittest -q tests.test_compras tests.test_nominas_integracion tests.test_criticos_c2_c3 tests.test_fase5 tests.test_actualizacion_operativa
flask run
```

No se requiere `flask db upgrade` para esta corrección porque no cambia el
esquema. Tampoco ejecutes `flask db init` ni `flask db migrate`.

Después de reiniciar, abre una pestaña nueva o haz una recarga forzada e inicia
sesión nuevamente. El formulario de logout debe enviar un campo llamado
`csrf_token`; `_csrf_token` ya no debe aparecer.

## Verificación

Resultado validado:

- `POST /logout` con token correcto: `302 /login`.
- `POST /logout` sin token: `400`, sin cerrar la sesión.
- Login con MFA y logout posterior: `302 /login`.
- 135 rutas POST bajo Flask-WTF, sin Blueprints ni vistas exentas.
- 120 formularios POST auditados, ninguno sin token.
- 131 plantillas compiladas sin errores.
- 63 pruebas acumuladas aprobadas.

