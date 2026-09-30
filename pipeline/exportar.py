"""Monta e grava dados.json / dados.js."""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from pipeline import focus, sinais
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
           gerado_em: datetime | None = None, previsoes: dict | None = None) -> dict:
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
        "previsoes": previsoes,
    }


def gravar(dados: dict, pasta: Path | str) -> None:
    pasta = Path(pasta)
    texto = json.dumps(dados, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    (pasta / "dados.json").write_text(texto, encoding="utf-8")
    (pasta / "dados.js").write_text("window.DADOS = " + texto + ";\n", encoding="utf-8")


TRAJETORIAS = [  # chave, indicador no Focus, nome, unidade, série do painel com o histórico
    ("ipca", "IPCA", "IPCA 12 meses", "%", "ipca_12m"),
    ("cambio", "Câmbio", "Dólar (USD/BRL)", "R$", "usd_brl"),
    ("pib", "PIB Total", "PIB (crescimento no ano)", "%", None),
]


def _proj_anual(semanal: dict, indicador: str) -> list[list]:
    """Um ponto por 31/12 com a última semana de cada ano de referência."""
    saida = []
    for ano, linhas in sorted(semanal.get(indicador, {}).items()):
        if linhas:
            u = linhas[-1]
            saida.append([f"{ano}-12-31", u["Mediana"], u["Minimo"], u["Maximo"], u["numeroRespondentes"], ano])
    return saida


def _dmy(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def previsoes(bruto: dict | None, agenda_: list[dict], selic_hoje: float | None, selic_data: str | None, usd_hoje: float | None,
              fed_funds: float | None, juro_hist: list[float], hoje: date, avisos: list[str], *,
              ipca_dez_anterior: float | None = None, usd_fim_anterior: float | None = None) -> dict:
    """Bloco da aba Previsões: sinais, agenda futura e trajetórias. Sem Focus, só a agenda."""
    iso = hoje.isoformat()
    passadas = {a["reuniao"] for a in agenda_ if a["tipo"] == "copom" and a["data"] < iso}
    futura = [dict(a) for a in agenda_ if a["data"] >= iso]
    for a in futura:
        if a["tipo"] == "fomc" and fed_funds is not None:
            a["contexto"] = f"Fed Funds hoje {sinais.fmt_br(fed_funds)}%"
    lista = sinais.sinais_agenda(futura, hoje, fed_funds)
    if bruto is None:
        return {"focus_data": None, "respondentes": None, "sinais": sinais.ordenar(lista),
                "agenda": futura, "trajetorias": {}}

    linhas_selic = {r["Reuniao"]: r for r in bruto.get("selic", [])}
    medianas = {k: float(v["Mediana"]) for k, v in linhas_selic.items()}
    semanal = focus.semanal(bruto.get("anuais", []))
    infl12 = (bruto.get("infl12") or {}).get("Mediana")

    for ind in focus.INDICADORES:
        if ind not in semanal:
            avisos.append(f"Focus sem projeções anuais de {ind}; sinais e gráfico desse indicador ficam de fora")

    ancora = selic_hoje
    ultima = max((a for a in agenda_ if a["tipo"] == "copom" and a["data"] < iso),
                 key=lambda a: a["data"], default=None)
    if selic_hoje is not None and selic_data is not None and ultima is not None and selic_data <= ultima["data"]:
        # a série da Selic ainda não tem a decisão de uma reunião que já passou
        aviso = (f"Selic meta mais recente é de {_dmy(selic_data)}, antes do Copom de "
                 f"{sinais.dm(ultima['data'])} ({ultima['reuniao']}); ")
        if ultima["reuniao"] in medianas:
            ancora = medianas[ultima["reuniao"]]
            avisos.append(aviso + "decisões esperadas contadas a partir da mediana do Focus para essa reunião "
                          f"({sinais.fmt_br(ancora)}%)")
        else:
            ancora = None
            avisos.append(aviso + "sinais do Copom omitidos até a atualização da série")
    if ancora is not None:
        decisoes = sinais.decisoes_esperadas(medianas, ancora, passadas)
        for a in futura:
            if a["tipo"] == "copom" and a["reuniao"] in decisoes:
                a["espera"] = decisoes[a["reuniao"]]
        lista += [s for s in (sinais.sinal_copom(futura, medianas, ancora, hoje, passadas),
                              sinais.sinal_trajetoria(medianas, ancora, hoje, passadas)) if s]
    lista += sinais.sinais_revisao(semanal, hoje)
    lista += [s for s in (sinais.sinal_juro_real(futura, medianas, infl12, juro_hist, hoje),
                          sinais.sinal_cambio(usd_hoje, semanal, hoje)) if s]

    datas = {a["reuniao"]: a["data"] for a in agenda_ if a["tipo"] == "copom"}
    ordem = sorted((r for r in medianas if r not in passadas), key=sinais.chave_reuniao)
    proj_selic = [[datas[r], medianas[r], float(linhas_selic[r]["Minimo"]), float(linhas_selic[r]["Maximo"]),
                   int(linhas_selic[r]["numeroRespondentes"]), r] for r in ordem if r in datas]
    sem_data = [r for r in ordem if r not in datas]
    if datas and sem_data:  # sem agenda nenhuma, o gráfico usa a projeção anual e não há o que avisar
        n = len(sem_data)
        avisos.append(f"Focus tem {n} {'reunião' if n == 1 else 'reuniões'} do Copom sem data em agenda.json "
                      f"({', '.join(sem_data)}); {'fica' if n == 1 else 'ficam'} fora do gráfico")

    trajetorias = {"selic": {"nome": "Selic meta", "unidade": "% a.a.", "serie_hist": "selic_meta",
                             "proj": proj_selic or _proj_anual(semanal, "Selic")}}
    for chave, ind, nome, unidade, hist in TRAJETORIAS:
        trajetorias[chave] = {"nome": nome, "unidade": unidade, "serie_hist": hist, "proj": _proj_anual(semanal, ind)}

    for t in trajetorias.values():
        t["proj_12m"] = None
    ha = bruto.get("ha_12m")
    if ha is None and bruto.get("ha_12m_erro"):
        avisos.append(f"Focus: sem a pesquisa de 12 meses atrás ({bruto['ha_12m_erro']}); comparação omitida")
    if ha:
        med_ha = {r["Reuniao"]: float(r["Mediana"]) for r in ha.get("selic", [])}
        pontos_selic = [[datas[r], med_ha[r], r] for r in sorted(med_ha, key=sinais.chave_reuniao) if r in datas]
        if pontos_selic:
            trajetorias["selic"]["proj_12m"] = {"data_pesquisa": ha["data_pesquisa"], "pontos": pontos_selic}
        anuais_ha: dict[str, dict[str, float]] = {}
        for r in ha.get("anuais", []):
            anuais_ha.setdefault(r["Indicador"], {})[str(r["DataReferencia"])] = float(r["Mediana"])
        for chave, ind, *_ in TRAJETORIAS:
            if anuais_ha.get(ind):
                trajetorias[chave]["proj_12m"] = {
                    "data_pesquisa": ha["data_pesquisa"],
                    "pontos": [[f"{ano}-12-31", v, ano] for ano, v in sorted(anuais_ha[ind].items())]}
        # Retrospectiva: o que a pesquisa de 12 meses atrás previa para o que já aconteceu.
        feitas = [a for a in agenda_ if a["tipo"] == "copom" and a["data"] < iso and a["reuniao"] in med_ha]
        if ancora is not None and feitas:
            a = max(feitas, key=lambda a: a["data"])
            lista.append(sinais.sinal_acerto_selic(med_ha[a["reuniao"]], a["data"], ha["data_pesquisa"], ancora))
        ano_anterior = str(hoje.year - 1)
        previsto = anuais_ha.get("IPCA", {}).get(ano_anterior)
        if previsto is not None and ipca_dez_anterior is not None:
            lista.append(sinais.sinal_acerto_ipca(previsto, ano_anterior, ipca_dez_anterior))
        previsto = anuais_ha.get("Câmbio", {}).get(ano_anterior)
        if previsto is not None and usd_fim_anterior is not None:
            lista.append(sinais.sinal_acerto_cambio(previsto, ano_anterior, usd_fim_anterior))

    ipca_ano = semanal.get("IPCA", {}).get(str(hoje.year)) or []
    return {"focus_data": bruto.get("data_pesquisa"),
            "respondentes": ipca_ano[-1]["numeroRespondentes"] if ipca_ano else None,
            "sinais": sinais.ordenar(lista), "agenda": futura, "trajetorias": trajetorias}
