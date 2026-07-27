# Fuente de verdad y compatibilidad

La fuente funcional usada fue:

```text
Sistema_Nominas_Semanales_actualizado_2026-07-17.zip
SHA-256: 0c8aff8a3162493891fe45d00514620176be399b67b74a33b3a360cf07706d84
```

El `app.py` original tiene SHA-256:

```text
872485953d9c690d2d863b766ea59265903cd3e7c28581224bb54ad1931869ec
```

## Cambios permitidos durante la integración

- `User` fue sustituido por `Usuario` del ERP.
- `Project` fue sustituido por `CentroCosto` del ERP.
- La bitácora original escribe en `bitacora_auditoria`.
- Las rutas se agruparon en el Blueprint `nominas`.
- Las plantillas viven bajo `templates/nominas/`.
- El CSRF original se conserva dentro del módulo; Flask-WTF protege el resto.
- Los valores `OBRA/OFICINA` se almacenan como `obra/oficina`, igual que Fase 2.

No se cambiaron las fórmulas de nómina, préstamo, IMSS, pago mixto, costos,
subcontratos, recursos semanales ni cierre/precarga.

## Pruebas ejecutadas

- Flujo completo: trabajador, préstamo, nómina, cierre, precarga y Excel.
- Costos con y sin IVA, oficina, subcontrato, avance y alertas.
- Importaciones masivas y múltiples administradores.
- Acceso por obras, permisos administrativos y CSRF.
- Migración desde Fase 2 sin la tabla simplificada.
- Migración desde Fase 3 con datos, preservando la tabla cancelada.
- Importación simulada y real desde una base del sistema original.

