"""Monta e grava dados.json / dados.js."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline.series import Serie

CASAS = 4


def listar_diaria(s: pd.Series) -> list[list]:
    return [[d.strftime("%Y-%m-%d"), round(float(v), CASAS)] for d, v in s.items() if not math.isnan(v)]


def listar_mensal(s: pd.Series) -> list[list]:
    return [[str(p), round(float(v), CASAS)] for p, v in s.items() if not math.isnan(v)]


def _variacao(m: pd.Series, defasagem: int, pct: bool) -> float | None:
    """Variação entre o último mês e o mês `defasagem` meses antes; None se esse mês não existe."""
    m = m.dropna()
    if m.empty:
        return None
    alvo = m.index[-1] - defasagem
    if alvo not in m.index:
        return None
    atual, antes = float(m.iloc[-1]), float(m[alvo])
    if pct:
        return None if antes == 0 else round((atual / antes - 1) * 100, CASAS)
    return round(atual - antes, CASAS)


def resumo_serie(serie: Serie, diaria: pd.Series, mensal: pd.Series, status: str) -> dict:
    pct = serie.transformacao == "logret"
    mensal = mensal.dropna()
    if not diaria.empty:
        inicio, fim = diaria.index.min(), diaria.index.max()
    else:
        inicio, fim = mensal.index.min().to_timestamp(), mensal.index.max().to_timestamp(how="end")
    prefixo = {"bcb": "BCB SGS"}.get(serie.fonte, serie.fonte.upper())
    return {
        "nome": serie.nome,
        "grupo": serie.grupo,
        "unidade": serie.unidade,
        "fonte": "derivada" if serie.fonte == "derivada" else f"{prefixo} {serie.codigo}",
        "freq": serie.freq,
        "transformacao": serie.transformacao,
        "status": status,
        "inicio": inicio.strftime("%Y-%m-%d"),
        "fim": fim.strftime("%Y-%m-%d"),
        "ultimo": round(float(mensal.iloc[-1]), CASAS),
        "var_tipo": "pct" if pct else "pp",
        "var_1m": _variacao(mensal, 1, pct),
        "var_12m": _variacao(mensal, 12, pct),
        "diario": listar_diaria(diaria),
        "mensal": listar_mensal(mensal),
    }


def montar(metas: dict[str, Serie], diarias: dict[str, pd.Series], mensais: dict[str, pd.Series],
           status: dict[str, str], avisos: list[str], correl: dict, eventos: list[dict],
           gerado_em: datetime | None = None) -> dict:
    gerado_em = gerado_em or datetime.now()
    series = {}
    vazia = pd.Series(dtype=float)
    for id, meta in metas.items():
        m = mensais.get(id)
        if m is None or m.dropna().empty:
            continue
        series[id] = resumo_serie(meta, diarias.get(id, vazia), m, status.get(id, "ok"))
    return {
        "gerado_em": gerado_em.strftime("%Y-%m-%dT%H:%M:%S"),
        "series": series,
        "correlacao": correl["correlacao"],
        "arestas": correl["arestas"],
        "eventos": sorted(eventos, key=lambda e: e["data"]),
        "avisos": list(avisos),
    }


def gravar(dados: dict, pasta: Path | str) -> None:
    pasta = Path(pasta)
    texto = json.dumps(dados, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    (pasta / "dados.json").write_text(texto, encoding="utf-8")
    (pasta / "dados.js").write_text("window.DADOS = " + texto + ";\n", encoding="utf-8")
