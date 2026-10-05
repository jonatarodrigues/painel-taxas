"""Aba Bolsa: carteiras da B3 (Ibovespa e IFIX), retornos por período, setores e amplitude."""
from __future__ import annotations

import pandas as pd

PERIODOS = ("dia", "semana", "mes", "ano", "m12")
INDICES = {  # chave -> (código na B3, nome, símbolo do índice no Yahoo)
    "ibov": ("IBOV", "Ibovespa", "^BVSP"),
    "ifix": ("IFIX", "IFIX", "IFIX.SA"),
}
OUTROS = "Outros"


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
