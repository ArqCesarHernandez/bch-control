"""Adapta las plantillas originales al namespace del ERP V2."""

from __future__ import annotations

import sys
from pathlib import Path


REPLACEMENTS = (
    ("{% extends 'base.html' %}", "{% extends 'nominas/base.html' %}"),
    ('{% extends "base.html" %}', '{% extends "nominas/base.html" %}'),
    ("from '_macros.html'", "from 'nominas/_macros.html'"),
    ('from "_macros.html"', 'from "nominas/_macros.html"'),
    ("filename='style.css'", "filename='nominas/style.css'"),
    ("filename='app.js'", "filename='nominas/app.js'"),
    ("url_for('logout')", "url_for('auth.logout')"),
    ("url_for('register')", "url_for('admin.usuario_nuevo')"),
    ("url_for('login')", "url_for('auth.login')"),
    ("project.tipo == 'OBRA'", "project.tipo == 'obra'"),
    ("project.tipo=='OBRA'", "project.tipo=='obra'"),
    ("project.tipo != 'OBRA'", "project.tipo != 'obra'"),
    ("project.tipo!='OBRA'", "project.tipo!='obra'"),
    ("project.tipo == 'OFICINA'", "project.tipo == 'oficina'"),
    ("project.tipo=='OFICINA'", "project.tipo=='oficina'"),
    ("project.tipo != 'OFICINA'", "project.tipo != 'oficina'"),
    ("project.tipo!='OFICINA'", "project.tipo!='oficina'"),
    ('value="OBRA"', 'value="obra"'),
    ('value="OFICINA"', 'value="oficina"'),
)


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: build_nominas_templates.py DIRECTORIO_PLANTILLAS")
        return 2
    root = Path(sys.argv[1]).resolve()
    for path in root.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for old, new in REPLACEMENTS:
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

