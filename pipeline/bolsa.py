"""Aba Bolsa: carteiras da B3 (Ibovespa e IFIX), retornos por período, setores e amplitude."""
from __future__ import annotations

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
