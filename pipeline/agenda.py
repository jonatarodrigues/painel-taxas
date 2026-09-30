"""Agenda curada (agenda.json): reuniões do Copom e do FOMC e divulgações do IPCA."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

TIPOS = {"copom", "fomc", "ipca"}
RE_REUNIAO = re.compile(r"^R[1-8]/\d{4}$")


def _data_valida(v) -> bool:
    try:
        return isinstance(v, str) and len(v) == 10 and date.fromisoformat(v).isoformat() == v
    except ValueError:
        return False


def valida(e) -> bool:
    if not isinstance(e, dict) or e.get("tipo") not in TIPOS or not _data_valida(e.get("data")):
        return False
    if not (isinstance(e.get("titulo"), str) and e["titulo"].strip()):
        return False
    if e["tipo"] == "copom":
        return isinstance(e.get("reuniao"), str) and bool(RE_REUNIAO.match(e["reuniao"]))
    return True


def carregar(arquivo: Path, avisos: list[str]) -> list[dict]:
    """Lê agenda.json; problemas viram avisos, nunca exceção."""
    if not arquivo.exists():
        avisos.append("agenda.json não encontrado; aba Previsões sem agenda")
        return []
    try:
        brutos = json.loads(arquivo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        avisos.append(f"agenda.json inválido ({e}); aba Previsões sem agenda")
        return []
    if not isinstance(brutos, list):
        avisos.append("agenda.json inválido (esperava uma lista); aba Previsões sem agenda")
        return []
    validos = [e for e in brutos if valida(e)]
    if len(validos) < len(brutos):
        avisos.append(f"agenda.json: {len(brutos) - len(validos)} entrada(s) ignorada(s) por formato inválido")
    return sorted(validos, key=lambda e: e["data"])
