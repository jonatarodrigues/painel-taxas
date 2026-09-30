"""Sinais da aba Previsões: regras puras sobre o Focus, a agenda e as séries do painel.

Os textos descrevem fatos e contexto; nunca recomendam compra ou venda.
Marcação única: **negrito**.
"""
from __future__ import annotations

from datetime import date

EPS = 1e-9
DIAS_DESTAQUE_COPOM = 7


def fmt_br(v: float, casas: int = 2, sinal: bool = False) -> str:
    v = round(float(v), casas)
    if v == 0:
        v = 0.0  # evita "-0,0"
    texto = f"{abs(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if v < 0:
        return "-" + texto
    return ("+" + texto) if (sinal and v > 0) else texto


def dm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def quando(dias: int) -> str:
    return "hoje" if dias == 0 else ("amanhã" if dias == 1 else f"em {dias} dias")


def chave_reuniao(r: str) -> tuple[int, int]:
    n, ano = r[1:].split("/")
    return int(ano), int(n)


def verbo(dif: float) -> str:
    if abs(dif) < EPS:
        return "manter"
    return f"cortar {fmt_br(-dif)} p.p." if dif < 0 else f"subir {fmt_br(dif)} p.p."


def decisoes_esperadas(medianas: dict[str, float], selic_hoje: float, ignorar: set[str]) -> dict[str, dict]:
    """Decisão esperada em cada reunião futura, contada a partir da reunião anterior."""
    saida, anterior = {}, selic_hoje
    for r in sorted((r for r in medianas if r not in ignorar), key=chave_reuniao):
        m = medianas[r]
        saida[r] = {"mediana": m, "dif": round(m - anterior, 2)}
        anterior = m
    return saida


def sinal_copom(agenda: list[dict], medianas: dict[str, float], selic_hoje: float,
                hoje: date, ignorar: set[str]) -> dict | None:
    dec = decisoes_esperadas(medianas, selic_hoje, ignorar)
    prox = next((a for a in agenda if a["tipo"] == "copom" and a["data"] >= hoje.isoformat()
                 and a["reuniao"] in dec), None)
    if prox is None:
        return None
    dias = (date.fromisoformat(prox["data"]) - hoje).days
    d = dec[prox["reuniao"]]
    destino = f"com a Selic em {fmt_br(d['mediana'])}%" if abs(d["dif"]) < EPS else f"com a Selic indo a {fmt_br(d['mediana'])}%"
    return {"nivel": "destaque" if dias <= DIAS_DESTAQUE_COPOM else "info", "tipo": "copom", "data": prox["data"],
            "texto": f"Copom {quando(dias)} ({dm(prox['data'])}): mercado espera **{verbo(d['dif'])}**, {destino}."}


def _movimento(d: float) -> str:
    if abs(d) < EPS:
        return "nenhuma mudança"
    return f"{fmt_br(abs(d))} p.p. de {'cortes' if d < 0 else 'altas'}"


def sinal_trajetoria(medianas: dict[str, float], selic_hoje: float, hoje: date, ignorar: set[str]) -> dict | None:
    futuras = {r: m for r, m in medianas.items() if r not in ignorar}
    if not futuras:
        return None
    ultima = max(futuras, key=chave_reuniao)
    do_ano_seguinte = [r for r in futuras if chave_reuniao(r)[0] == hoje.year + 1]
    fim = max(do_ano_seguinte, key=chave_reuniao) if do_ano_seguinte else None
    alvo, rotulo = (fim, f"o fim de {hoje.year + 1}") if fim else (ultima, ultima)
    texto = (f"Mercado espera **{_movimento(futuras[alvo] - selic_hoje)}** até {rotulo} "
             f"({fmt_br(selic_hoje)}% → {fmt_br(futuras[alvo])}%)")
    if fim and ultima != fim:
        texto += f" e {_movimento(futuras[ultima] - selic_hoje)} até {ultima} ({fmt_br(futuras[ultima])}%)"
    return {"nivel": "info", "tipo": "selic", "texto": texto + "."}
