# BCH Control — instalación acumulativa C1, C2 y C3

## Decisión de instalación

**No instales por separado el paquete anterior de C1.** Instala únicamente el
ZIP acumulativo C1+C2+C3 entregado con esta guía. La cadena de migraciones
reconoce tanto una base que todavía está en `e9a3f7c2d614` como una que ya
alcanzó `a4c7e2f9b615`.

La revisión final esperada es:

```text
c8d1f4a6b720 (head)
```

## Qué cambia en los datos existentes

- La migración C1 `a4c7e2f9b615` materializa el alcance de los compradores
  existentes. Después debe revisarse en **Administración → Usuarios** y dejar
  únicamente las obras que correspondan a cada persona.
- Las nóminas históricas `BORRADOR` pasan a `borrador` y las `CERRADA` pasan a
  `aprobada`. El sistema no supone que una nómina histórica ya fue pagada; el
  Administrador financiero debe comprobarlo antes de marcarla `pagada`.
- Los préstamos existentes no reciben interés retroactivo: conservan su monto
  contractual, se migran con tasa `0%` y `total_pagar = monto`. Los préstamos
  creados después de instalar calculan automáticamente capital más 5%. La
  migración conserva al creador como solicitante, pero no inventa aprobador ni
  fecha para registros históricos que nunca guardaron esos datos.
- Los préstamos históricos `ACTIVO`, `PAGADO` y `CANCELADO` pasan a `activo`,
  `liquidado` y `rechazado`, respectivamente.
- La cuenta principal `id=1` queda activa, con rol `admin` y acceso total.
- Se crean los permisos sensibles `seguridad` y `ver_nss_completo`. El NSS se
  muestra completo solo cuando la acción **Ver** del segundo está habilitada.

## 1. Preparar un respaldo sin riesgo

1. Detén Flask con `Ctrl + C` y cierra cualquier proceso que use la base.
2. Comprueba dónde está la base antes de copiarla. En la instalación local
   descrita en las guías anteriores normalmente es
   `C:\erp_v2_nuevo\instance\erp_v2.db`.
3. Crea un respaldo con fecha:

```powershell
New-Item -ItemType Directory -Force C:\erp_v2_backups
$fechaBch = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item C:\erp_v2_nuevo\instance\erp_v2.db "C:\erp_v2_backups\erp_v2_antes_C1_C2_C3_$fechaBch.db"
Get-FileHash "C:\erp_v2_backups\erp_v2_antes_C1_C2_C3_$fechaBch.db" -Algorithm SHA256
```

4. Para que el respaldo con NSS y sueldos no quede legible, comprímelo con
   cifrado AES-256 usando 7-Zip. `-p` sin escribir la contraseña hace que 7-Zip
   la solicite; guárdala en el administrador de contraseñas de BCH:

```powershell
& "C:\Program Files\7-Zip\7z.exe" a -t7z -mhe=on -p `
  "C:\erp_v2_backups\erp_v2_antes_C1_C2_C3_$fechaBch.7z" `
  "C:\erp_v2_backups\erp_v2_antes_C1_C2_C3_$fechaBch.db"
& "C:\Program Files\7-Zip\7z.exe" t `
  "C:\erp_v2_backups\erp_v2_antes_C1_C2_C3_$fechaBch.7z"
```

No elimines el respaldo anterior hasta terminar toda la verificación.

## 2. Instalar la actualización acumulativa

Usa el nombre exacto del ZIP entregado. En PowerShell:

```powershell
Expand-Archive `
  -Path "$env:USERPROFILE\Downloads\erp_v2_bch_control_C1_C2_C3_actualizacion_acumulativa.zip" `
  -DestinationPath "C:\erp_v2_nuevo" `
  -Force

cd C:\erp_v2_nuevo
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
flask db current
flask db upgrade
flask db current
flask db check
```

El segundo `flask db current` debe mostrar:

```text
c8d1f4a6b720 (head)
```

Y `flask db check` debe terminar con:

```text
No new upgrade operations detected.
```

No ejecutes `flask db init` ni `flask db migrate`.

## 3. Ejecutar la regresión

```powershell
python -m unittest `
  tests.test_compras `
  tests.test_nominas_integracion `
  tests.test_criticos_c2_c3 `
  -v
```

Resultado esperado:

```text
Ran 35 tests
OK
```

Las pruebas usan bases temporales; no modifican la base operativa.

## 4. Verificación funcional antes de trabajar

1. Inicia con `flask run` y abre `http://127.0.0.1:5000`.
2. Entra con el administrador principal. El primer acceso administrativo,
   también en local, abrirá la configuración obligatoria de MFA. Registra el
   secreto mostrado en Google Authenticator, Microsoft Authenticator u otra
   aplicación TOTP y confirma un código de seis dígitos. Conserva una copia
   protegida del secreto en el administrador de contraseñas corporativo; no lo
   envíes por correo ni mensajería.
3. En **Administración → Usuarios**:
   - confirma que César (`id=1`) siga activo y como Administrador;
   - revisa las obras asignadas a cada Supervisor, Capturista y Comprador;
   - crea o asigna el rol **Administrador financiero** a quien ejecutará pagos;
   - entrega `seguridad.editar` únicamente a quienes realmente administren
     permisos;
   - entrega `ver_nss_completo.ver` únicamente a personal autorizado.
4. Abre un trabajador con más de seis meses, solicita un préstamo pequeño y
   verifica: estado pendiente, interés 5%, total correcto y aviso al admin.
5. Aprueba el préstamo con un admin general. Confirma que la retención aparezca
   desde la siguiente semana, nunca en la semana de entrega.
6. Prueba una nómina con el flujo:
   `borrador → enviada → aprobada → pagada → conciliada`.
7. Antes de marcar nóminas históricas como pagadas, compáralas con el banco o
   la dispersión real. Después de `pagada` ya no pueden reabrirse.
8. Abre una lista y una exportación de nómina con una cuenta sin permiso de NSS;
   debe verse `****1234`. Con el permiso explícito debe verse el valor completo.

## 5. Configuración obligatoria de producción

BCH Control aborta el arranque si producción usa SQLite, una clave corta o una
clave de ejemplo. Genera una clave distinta para cada ambiente:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Configura en Render/PythonAnywhere, sin guardar estos valores en el código:

```dotenv
FLASK_ENV=production
SECRET_KEY=PEGA_AQUI_LA_CLAVE_GENERADA
DATABASE_URL=postgresql://USUARIO:CONTRASENA@HOST:5432/BASE
```

Requisitos operativos:

- `DATABASE_URL` debe ser PostgreSQL; producción rechazará SQLite y otros
  motores.
- El proxy de Render debe enviar `X-Forwarded-Proto: https`. La aplicación usa
  cookies seguras, esquema HTTPS y HSTS por un año.
- Ejecuta `flask db upgrade` como comando previo al arranque de la versión.
- El primer acceso de cada cuenta con rol `admin` exige configurar TOTP. El rol
  `admin_financiero` no recibe MFA por defecto porque el requisito especifica
  únicamente el rol `admin`; puede endurecerse en una fase posterior.
- El bloqueo ocurre al quinto fallo de contraseña o TOTP dentro de 15 minutos.
  Cada fallo queda registrado como `LOGIN_FALLIDO` en la bitácora.

## 6. Respaldos PostgreSQL cifrados

Para producción, activa los respaldos cifrados y recuperación punto en el
tiempo del proveedor. Además, conserva una copia externa periódica:

```powershell
$fechaBch = Get-Date -Format "yyyyMMdd_HHmmss"
pg_dump "$env:DATABASE_URL" --format=custom `
  --file="C:\erp_v2_backups\bch_control_$fechaBch.backup"
& "C:\Program Files\7-Zip\7z.exe" a -t7z -mhe=on -p `
  "C:\erp_v2_backups\bch_control_$fechaBch.7z" `
  "C:\erp_v2_backups\bch_control_$fechaBch.backup"
& "C:\Program Files\7-Zip\7z.exe" t `
  "C:\erp_v2_backups\bch_control_$fechaBch.7z"
```

Guarda la contraseña fuera del servidor, restringe el acceso a la carpeta y
realiza una restauración de prueba al menos una vez al mes. El archivo temporal
sin cifrar debe retirarse solo después de comprobar el `.7z`, conforme a la
política de retención de BCH.

## 7. Recuperación si algo falla

No sigas capturando si la migración o las pruebas fallan. Conserva el mensaje
completo y aplica esta recuperación:

1. Detén Flask.
2. Conserva una copia de la base que falló para diagnóstico.
3. Restaura el archivo `.db` previo y la copia completa anterior del código.
4. Inicia y confirma que la revisión vuelva a la que mostraba antes de instalar.

Aunque la migración fue probada bajando y subiendo, no se recomienda usar
`flask db downgrade` después de comenzar a operar con estados `pagada` o
`conciliada`, porque una versión anterior no conoce esa distinción. Restaurar
el respaldo previo conserva con mayor fidelidad el estado original.

## Controles entregados

- C1: techo de permisos, bloqueo de autoelevación y 404 para obras ajenas.
- C2: préstamo al 5%, antigüedad mayor a seis meses, tope de salario semanal,
  aprobación/rechazo auditables y saldo sobre `total_pagar`.
- C2: ciclo financiero de nómina, reversión auditada solo desde `aprobada` y
  bloqueo de reapertura desde `pagada`.
- C3: secretos obligatorios, PostgreSQL/HTTPS, encabezados HTTP, rate limiting,
  NSS enmascarado, exportación condicionada y MFA TOTP para administradores.
