"""Aba Bolsa: carteiras da B3 (Ibovespa e IFIX), retornos por período, setores e amplitude."""
from __future__ import annotations

from typing import NamedTuple
import pandas as pd

PERIODOS = ("dia", "semana", "mes", "ano", "m12")
INDICES = {  # chave -> (código na B3, nome, símbolo do índice no Yahoo)
    "ibov": ("IBOV", "Ibovespa", "^BVSP"),
    "ifix": ("IFIX", "IFIX", "IFIX.SA"),
}
OUTROS = "Outros"
LIMIAR_SEM_DADO = 0.20


# ---------------- carteira da B3 ----------------
def numero_br(texto) -> float | None:
    """'1.460.506.056' -> 1460506056.0; '2,792' -> 2.792; vazio ou inválido -> None."""
    if texto is None:
        return None
    t = str(texto).strip().replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _data_b3(texto: str) -> str | None:
    partes = str(texto).strip().split("/")
    if len(partes) != 3 or not all(p.isdigit() for p in partes):
        return None
    dia, mes, ano = partes
    if len(ano) == 2:
        ano = "20" + ano
    return f"{ano}-{int(mes):02d}-{int(dia):02d}"


def parse_carteira_b3(payload) -> dict | None:
    """Carteira teórica do dia. None quando o formato não bate ou não sobra nenhum ativo."""
    try:
        data = _data_b3(payload["header"]["date"])
        resultados = payload["results"]
    except (KeyError, TypeError):
        return None
    if data is None or not isinstance(resultados, list):
        return None
    ativos = []
    for r in resultados:
        if not isinstance(r, dict):
            continue
        ticker = str(r.get("cod") or "").strip()
        peso = numero_br(r.get("part"))
        if not ticker or peso is None:
            continue
        segmento = " ".join(str(r.get("segment") or "").split())
        setor = segmento.split("/")[0].strip() or OUTROS
        nome = " ".join(str(r.get("asset") or ticker).split())
        ativos.append({"ticker": ticker, "nome": nome, "setor": setor, "subsetor": segmento, "peso": peso})
    return {"data": data, "ativos": ativos} if ativos else None


# ---------------- retornos ----------------
def _base(s: pd.Series, limite: pd.Timestamp, inclusivo: bool = False) -> float | None:
    sel = s[s.index <= limite] if inclusivo else s[s.index < limite]
    return float(sel.iloc[-1]) if not sel.empty else None


def retornos(s: pd.Series | None, data_ref: pd.Timestamp) -> dict[str, float | None]:
    """Retorno em % de data_ref contra o último fechamento anterior a cada período."""
    vazio = {p: None for p in PERIODOS}
    if s is None:
        return vazio
    s = s.dropna()
    s = s[s.index <= data_ref]
    if s.empty or s.index[-1] != data_ref:
        return vazio
    atual = float(s.iloc[-1])
    segunda = data_ref - pd.Timedelta(days=data_ref.weekday())
    bases = {
        "dia": _base(s, data_ref),
        "semana": _base(s, segunda),
        "mes": _base(s, data_ref.replace(day=1)),
        "ano": _base(s, pd.Timestamp(data_ref.year, 1, 1)),
        "m12": _base(s, data_ref - pd.DateOffset(months=12), inclusivo=True),
    }
    return {p: (None if not b else round((atual / b - 1) * 100, 2)) for p, b in bases.items()}


# ---------------- mini-série semanal ----------------
def semanas(data_ref: pd.Timestamp, n: int = 52) -> pd.PeriodIndex:
    return pd.period_range(end=data_ref.to_period("W-FRI"), periods=n, freq="W-FRI")


def rotulos_semanas(periodos: pd.PeriodIndex, data_ref: pd.Timestamp) -> list[str]:
    """Sexta-feira de cada semana; na semana corrente, a própria data_ref."""
    return [min(p.end_time.normalize(), data_ref).strftime("%Y-%m-%d") for p in periodos]


def semanal(s: pd.Series | None, data_ref: pd.Timestamp, periodos: pd.PeriodIndex) -> list[float | None]:
    """Último valor de cada semana, alinhado a `periodos`; None onde não houve pregão."""
    if s is None:
        return [None] * len(periodos)
    s = s.dropna()
    s = s[s.index <= data_ref]
    if s.empty:
        return [None] * len(periodos)
    ultimo = s.groupby(s.index.to_period("W-FRI")).last()
    return [round(float(ultimo[p]), 2) if p in ultimo.index else None for p in periodos]


# ---------------- montagem de uma visão ----------------
class Preco(NamedTuple):
    serie: pd.Series | None
    desatualizado: bool = False
    sem_proventos: bool = False


def data_referencia(indice: pd.Series | None, series: list[pd.Series | None]) -> pd.Timestamp | None:
    """Último pregão do índice; sem índice, a data mais frequente entre os últimos pregões dos ativos."""
    if indice is not None and not indice.dropna().empty:
        return indice.dropna().index[-1]
    ultimos = [s.dropna().index[-1] for s in series if s is not None and not s.dropna().empty]
    return pd.Series(ultimos).mode().max() if ultimos else None


def agregar_setores(ativos: list[dict]) -> list[dict]:
    """Retorno de cada setor = média dos ativos com dado, ponderada pelo peso no índice."""
    grupos: dict[str, list[dict]] = {}
    for a in ativos:
        grupos.setdefault(a["setor"], []).append(a)
    saida = []
    for nome, lista in grupos.items():
        ret = {}
        for p in PERIODOS:
            com = [a for a in lista if a["ret"][p] is not None]
            soma = sum(a["peso"] for a in com)
            ret[p] = round(sum(a["peso"] * a["ret"][p] for a in com) / soma, 2) if soma > 0 else None
        saida.append({"nome": nome, "peso": round(sum(a["peso"] for a in lista), 3), "ret": ret})
    return sorted(saida, key=lambda s: -s["peso"])


def amplitude(ativos: list[dict]) -> dict[str, dict]:
    return {p: {"alta": sum(1 for a in ativos if a["ret"][p] is not None and a["ret"][p] > 0),
                "total": sum(1 for a in ativos if a["ret"][p] is not None)} for p in PERIODOS}


def montar_visao(chave: str, carteira: dict | None, carteira_cache: bool, precos: dict[str, Preco],
                 indice: pd.Series | None, tipos: dict[str, str] | None, avisos: list[str]) -> dict | None:
    """Uma visão (ibov ou ifix) pronta para o painel. None quando não há índice nem preços."""
    nome = INDICES[chave][1]
    itens = carteira["ativos"] if carteira else []
    ref = data_referencia(indice, [precos.get(a["ticker"], Preco(None)).serie for a in itens])
    if ref is None:
        return None
    if carteira is None:
        avisos.append(f"{nome}: carteira indisponível (B3 fora do ar e sem cache).")
    periodos = semanas(ref)
    ativos, sem_tipo = [], []
    for item in itens:
        p = precos.get(item["ticker"], Preco(None))
        r = retornos(p.serie, ref)
        a = {"ticker": item["ticker"], "nome": item["nome"], "setor": item["setor"],
             "subsetor": item["subsetor"], "peso": round(item["peso"], 3)}
        if tipos is not None:
            a.pop("subsetor")
            a["setor"] = tipos.get(item["ticker"], OUTROS)
            if item["ticker"] not in tipos:
                sem_tipo.append(item["ticker"])
        parado = p.serie is None or ref not in p.serie.dropna().index
        a.update({"ret": r, "parado": parado,
                  "desatualizado": p.desatualizado, "sem_proventos": p.sem_proventos,
                  "semanal": semanal(p.serie, ref, periodos)})
        ativos.append(a)
    if sem_tipo:
        n = len(sem_tipo)
        avisos.append(f"{nome}: {n} {'fundo' if n == 1 else 'fundos'} sem tipo em fiis.json: "
                      f"{', '.join(sorted(sem_tipo))} (fica{'' if n == 1 else 'm'} em Outros).")
    sem_dado = sum(1 for a in ativos if a["ret"]["dia"] is None)
    alerta = None
    if ativos and sem_dado / len(ativos) > LIMIAR_SEM_DADO:
        alerta = (f"{nome}: {sem_dado} de {len(ativos)} ativos sem cotação em {ref:%d/%m/%Y}; "
                  f"o mapa não representa o índice inteiro.")
        avisos.append(alerta)
    return {
        "nome": nome,
        "data_ref": ref.strftime("%Y-%m-%d"),
        "carteira_data": carteira["data"] if carteira else None,
        "carteira_cache": bool(carteira_cache and carteira),
        "alerta": alerta,
        "semanas": rotulos_semanas(periodos, ref),
        "indice": {"ret": retornos(indice, ref)},
        "amplitude": amplitude(ativos),
        "setores": agregar_setores(ativos),
        "ativos": ativos,
    }
