"""Retira del formulario el prototipo de captura semanal cancelado."""

from pathlib import Path


path = Path(__file__).resolve().parents[1] / "forms.py"
source = path.read_text(encoding="utf-8")
marker = "\n\nclass RegistroSemanalForm(FlaskForm):"
if marker in source:
    path.write_text(source.split(marker, 1)[0].rstrip() + "\n", encoding="utf-8")

