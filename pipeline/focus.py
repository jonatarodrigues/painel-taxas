"""Boletim Focus (API Olinda do BCB): Selic por reunião, projeções anuais e IPCA 12 meses."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import pandas as pd

from pipeline import fontes

BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"
INDICADORES = ("IPCA", "Câmbio", "PIB Total", "Selic")
SEMANAS = 13
TIMEOUT = 90


def url_odata(entidade: str, opcoes: dict) -> str:
    """Monta a URL com espaços como %20: o Olinda responde 400 quando recebe "+"."""
    qs = "&".join(f"${k}={quote(str(v), safe='')}" for k, v in {"format": "json", **opcoes}.items())
    return f"{BASE}/{entidade}?{qs}"


def consultar(entidade: str, **opcoes) -> list[dict]:
    r = fontes._get(url_odata(entidade, opcoes), timeout=TIMEOUT, json=True)
    return r.json().get("value", []) if r is not None else []


def baixar(hoje: date) -> dict:
    selic = consultar("ExpectativasMercadoSelic", filter="baseCalculo eq 0", orderby="Data desc", top=60)
    if not selic:
        raise fontes.RespostaVazia("Focus sem dados da Selic")
    data = selic[0]["Data"]
    selic = [v for v in selic if v["Data"] == data]
    desde = (hoje - timedelta(weeks=SEMANAS)).isoformat()
    indicadores = " or ".join(f"Indicador eq '{i}'" for i in INDICADORES)
    anuais = consultar(
        "ExpectativasMercadoAnuais",
        filter=(f"Data ge '{desde}' and baseCalculo eq 0 and ({indicadores}) "
                f"and DataReferencia ge '{hoje.year}' and DataReferencia le '{hoje.year + 3}'"),
        select="Indicador,Data,DataReferencia,Mediana,Minimo,Maximo,numeroRespondentes")
    infl = consultar("ExpectativasMercadoInflacao12Meses",
                     filter="Indicador eq 'IPCA' and Suavizada eq 'S' and baseCalculo eq 0",
                     orderby="Data desc", top=1)
    if not anuais:
        raise fontes.RespostaVazia("Focus sem projeções anuais")
    if not infl:
        raise fontes.RespostaVazia("Focus sem IPCA 12 meses")
    return {"data_pesquisa": data, "selic": selic, "anuais": anuais, "infl12": infl[0]}


def semanal(anuais: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """{indicador: {ano: [última linha de cada semana]}}; a semana termina na sexta."""
    if not anuais:
        return {}
    df = pd.DataFrame(anuais)
    df["semana"] = pd.to_datetime(df["Data"]).dt.to_period("W-FRI").dt.end_time.dt.strftime("%Y-%m-%d")
    df = df.sort_values("Data").groupby(["Indicador", "DataReferencia", "semana"], as_index=False).last()
    saida: dict[str, dict[str, list[dict]]] = {}
    for (ind, ano), g in df.groupby(["Indicador", "DataReferencia"]):
        saida.setdefault(ind, {})[str(ano)] = [
            {"semana": r.semana, "Mediana": float(r.Mediana), "Minimo": float(r.Minimo),
             "Maximo": float(r.Maximo), "numeroRespondentes": int(r.numeroRespondentes)}
            for r in g.sort_values("semana").itertuples()]
    return saida


def obter(arquivo: Path, offline: bool, hoje: date,
          baixar: Callable[[date], dict]) -> tuple[dict | None, str | None]:
    """Retorna (bruto, aviso). Falha de rede, resposta vazia ou modo offline caem no cache."""
    def do_cache(motivo: str) -> tuple[dict | None, str]:
        if not arquivo.exists():
            return None, f"Focus: {motivo} e sem cache; aba Previsões sem projeções"
        try:
            c = json.loads(arquivo.read_text(encoding="utf-8"))
            return c["bruto"], (f"Focus: lido do cache de {c['baixado_em']} (offline)" if offline
                                else f"Focus: {motivo}; usando cache de {c['baixado_em']}")
        except (ValueError, KeyError, TypeError) as e:
            return None, f"Focus: {motivo} e cache ilegível ({e}); aba Previsões sem projeções"

    if offline:
        return do_cache("offline")
    try:
        bruto = baixar(hoje)
    except Exception as e:  # rede, parsing ou vazio: qualquer falha cai no cache
        return do_cache(f"falha ao baixar ({e})")
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps({"baixado_em": hoje.isoformat(), "bruto": bruto}, ensure_ascii=False),
                       encoding="utf-8")
    return bruto, None
