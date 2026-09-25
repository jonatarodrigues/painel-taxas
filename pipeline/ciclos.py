"""Detecta viradas de ciclo da Selic meta e gera eventos automáticos."""
from __future__ import annotations

import pandas as pd

SERIES_AFETADAS = ["selic_meta", "cdi", "usd_brl", "ibovespa", "ipca_12m"]


def _pct(v: float) -> str:
    return f"{v:.2f}".replace(".", ",") + "%"


def ciclos_copom(selic_meta: pd.Series) -> list[dict]:
    """Um evento por virada de direção (alta -> baixa ou baixa -> alta) da Selic meta."""
    if selic_meta.empty:
        return []
    s = selic_meta.dropna().sort_index()
    mudancas = s[s.diff().fillna(0) != 0]
    eventos: list[dict] = []
    direcao_anterior = 0
    for data, valor in mudancas.items():
        anterior = float(s[s.index < data].iloc[-1])
        direcao = 1 if valor > anterior else -1
        if direcao != direcao_anterior:
            tipo = "alta" if direcao > 0 else "baixa"
            eventos.append({
                "data": data.strftime("%Y-%m-%d"),
                "titulo": f"Copom inicia ciclo de {tipo}: {_pct(anterior)} → {_pct(float(valor))}",
                "categoria": "copom",
                "descricao": (f"Primeira {'alta' if direcao > 0 else 'queda'} da Selic meta após um período de "
                              f"{'cortes ou estabilidade' if direcao > 0 else 'altas ou estabilidade'}. "
                              "Detectado automaticamente na série 432 do BCB."),
                "series": SERIES_AFETADAS,
                "auto": True,
            })
            direcao_anterior = direcao
    return eventos
