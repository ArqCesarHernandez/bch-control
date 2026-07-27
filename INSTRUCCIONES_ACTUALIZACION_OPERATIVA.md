# BCH Control — instalación de la actualización operativa

Esta actualización se aplica sobre la revisión vigente de Fase 5:

- Revisión de origen: `c6d9a4c5880d`
- Revisión nueva: `e3a7b9c1d245`
- Base funcional: C1, C2, C3 y Fase 5

No reinstala Almacenista, CEO, Campo, RFQ, licitaciones, contratos,
recepciones ni conciliación. Amplía los modelos y flujos existentes.

## 1. Preparación obligatoria

1. Programa una ventana de mantenimiento y detén temporalmente la aplicación.
2. Confirma que no haya procesos de nómina, pagos o recepciones en curso.
3. Respalda por separado:

   - La base PostgreSQL completa.
   - La carpeta configurada en `FASE5_UPLOAD_FOLDER`.
   - El archivo `.env` del servidor.
   - La versión actual del código.

4. Comprueba la revisión de origen:

   ```bash
   flask db current
   ```

   En una instalación Fase 5 vigente debe aparecer:

   ```text
   c6d9a4c5880d
   ```

Si aparece otra revisión, no ejecutes la migración hasta identificar la
diferencia.

## 2. Aplicar el ZIP de actualización

Extrae el ZIP acumulativo encima de una copia del proyecto Fase 5, conservando
la estructura de carpetas. No reemplaces el `.env`, la base ni los adjuntos.

Activa el entorno virtual e instala las dependencias declaradas:

```bash
python -m pip install -r requirements.txt
```

La actualización no necesita secretos nuevos. Conserva las variables actuales,
en particular:

```text
FLASK_ENV
DATABASE_URL
SECRET_KEY
FASE5_UPLOAD_FOLDER
```

## 3. Migrar la base

Con la aplicación todavía detenida:

```bash
flask db upgrade
flask db current
flask db check
```

Resultado esperado:

```text
e3a7b9c1d245 (head)
No new upgrade operations detected.
```

La migración:

- Conserva usuarios, OC, requisiciones, recepciones, explosiones y pagos.
- Crea una primera revisión para cada explosión histórica existente.
- Marca las OC históricas con beneficiario previamente validado para no
  bloquear pagos nacidos bajo el flujo anterior.
- No crea programaciones de pago para OC históricas.
- Inserta solamente permisos granulares ausentes.
- Conserva las acciones CRUD y `aprobar` que ya estuvieran personalizadas.
- No vuelve a conceder módulos nuevos derivados de un permiso agrupado que
  estuviera revocado.

No ejecutes `flask db init` ni `flask db migrate`.

## 4. Ejecutar las pruebas

Desde la raíz del proyecto:

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
Ran 61 tests
OK
```

## 5. Revisión administrativa después de migrar

Entra con el Administrador principal y revisa:

1. **Administración → Usuarios → Editar**.
2. Confirma las obras asignadas a Supervisores, Compradores y Almacenistas.
3. Revisa los permisos individuales de cada usuario.
4. Habilita expresamente capacidades sensibles solo cuando correspondan:

   - `emitir` o `cancelar` OC.
   - `aprobar` requisiciones, garantías, SMNC o anticipos.
   - `pagar`.
   - `conciliar`.
   - Datos sensibles de proveedores.

Los roles son únicamente una plantilla inicial. La fila individual de permiso
es la autoridad efectiva.

## 6. Verificación funcional por perfil

### Supervisor

- Solo ve información de sus obras en el Dashboard Supervisor.
- Puede crear requisiciones y OC de Operaciones según sus permisos.
- Una OC sin anticipo queda contra recepción; no queda pagada.
- Una OC con anticipo genera programación de anticipo y saldo.
- No puede aprobar ni pagar su propio anticipo por defecto.
- No ve empresas, métodos de pago, reportes globales, contratos ni datos
  fiscales/financieros de proveedores.

### Almacenista

- Solo ve OC pendientes de sus obras.
- Registra cantidades recibidas, rechazadas y faltantes.
- Una discrepancia exige motivo y evidencia.
- No ve precios, proveedores, pagos ni edición de OC.

### Finanzas

- Valida al beneficiario libre, empresa y método antes de transferir.
- Autoriza o rechaza anticipos sin confundir autorización con pago.
- Solo puede pagar el monto liberado por la programación.
- En pago contra recepción, la liberación es proporcional a lo recibido.

### Garantías

- La obra principal debe estar `cerrada`, `inactiva` o `finalizada`.
- El sistema crea un centro hijo de tipo `garantia`.
- La obra principal no se reactiva.
- Los costos de garantía quedan separados del avance y ejecución originales.

## 7. Puesta en servicio

Reinicia el proceso web y los workers habituales. Después verifica:

```bash
flask db current
flask db check
```

Realiza una prueba controlada con un usuario de cada perfil antes de abrir el
sistema a todos los usuarios.

## 8. Recuperación

La recuperación recomendada es restaurar juntos:

1. El respaldo de PostgreSQL.
2. La carpeta de adjuntos respaldada.
3. El código Fase 5 anterior.
4. El `.env` original.

El comando siguiente solo es admisible durante la ventana de instalación,
antes de crear garantías, programaciones de pago, revisiones u OC del flujo
nuevo:

```bash
flask db downgrade c6d9a4c5880d
```

La migración detiene intencionalmente el `downgrade` si detecta información
nueva que Fase 5 no puede representar sin pérdida. Si el sistema ya fue usado,
no fuerces el descenso ni borres registros: restaura el respaldo completo.

## 9. Instalación nueva

Para una base vacía:

```bash
python -m pip install -r requirements.txt
flask db upgrade
flask db current
flask db check
```

La revisión esperada también es `e3a7b9c1d245 (head)`.

