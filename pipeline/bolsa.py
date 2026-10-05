"""Aba Bolsa: carteiras da B3 (Ibovespa e IFIX), retornos por período, setores e amplitude."""
from __future__ import annotations

import base64
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, NamedTuple

import pandas as pd

from pipeline import fontes
from pipeline.cache import Cache

PERIODOS = ("dia", "semana", "mes", "ano", "m12")
INDICES = {  # chave -> (código na B3, nome, símbolo do índice no Yahoo)
    "ibov": ("IBOV", "Ibovespa", "^BVSP"),
    "ifix": ("IFIX", "IFIX", "XFIX11.SA"),
}
OUTROS = "Outros"
LIMIAR_SEM_DADO = 0.20
TIPOS_FII = ("Logística", "Lajes", "Shoppings", "Renda urbana", "Agro", "Papel", "Híbrido", "Fundo de fundos", OUTROS)
B3_URL = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/"
MAX_PAGINAS = 10
DOWNLOADS_SIMULTANEOS = 5


# ---------------- carteira da B3 ----------------
def numero_br(texto) -> float | None:
    """'1.460.506.056' -> 1460506056.0; '2,792' -> 2.792; vazio ou inválido -> None."""
    if texto is None:
        return None
    t = str(texto).strip().replace(".", "").replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


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
    """O mais recente entre o último pregão do índice e a data mais frequente dos últimos pregões dos ativos."""
    candidatas = []
    if indice is not None and not indice.dropna().empty:
        candidatas.append(indice.dropna().index[-1])
    ultimos = [s.dropna().index[-1] for s in series if s is not None and not s.dropna().empty]
    if ultimos:
        candidatas.append(pd.Series(ultimos).mode().max())
    return max(candidatas) if candidatas else None


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
                 indice: pd.Series | None, tipos: dict[str, str] | None, avisos: list[str],
                 indice_desatualizado: bool = False) -> dict | None:
    """Uma visão (ibov ou ifix) pronta para o painel. None quando não há índice nem preços."""
    nome = INDICES[chave][1]
    itens = carteira["ativos"] if carteira else []
    ref = data_referencia(indice, [precos.get(a["ticker"], Preco(None)).serie for a in itens])
    if ref is None:
        return None
    if carteira is None:
        avisos.append(f"{nome}: carteira indisponível (B3 fora do ar e sem cache).")
    if indice_desatualizado:
        avisos.append(f"{nome}: índice do cache (Yahoo indisponível).")
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
        "indice": {"ret": retornos(indice, ref), "simbolo": INDICES[chave][2],
                   "desatualizado": bool(indice_desatualizado)},
        "amplitude": amplitude(ativos),
        "setores": agregar_setores(ativos),
        "ativos": ativos,
    }


# ---------------- rede e cache ----------------
def url_carteira(indice_b3: str, pagina: int = 1) -> str:
    p = {"language": "pt-br", "pageNumber": pagina, "pageSize": 200, "index": indice_b3, "segment": "2"}
    return B3_URL + base64.b64encode(json.dumps(p, separators=(",", ":")).encode()).decode()


def baixar_carteira(indice_b3: str) -> dict | None:
    header, resultados, pagina = None, [], 1
    while True:
        r = fontes._get(url_carteira(indice_b3, pagina), json=True)
        if r is None:
            return None
        p = r.json()
        header = header or p.get("header")
        resultados += p.get("results") or []
        total = (p.get("page") or {}).get("totalPages") or 1
        if pagina >= min(total, MAX_PAGINAS):
            break
        pagina += 1
    return parse_carteira_b3({"header": header, "results": resultados})


def _ler_json(arquivo: Path) -> dict:
    try:
        d = json.loads(arquivo.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def obter_carteira(chave: str, arquivo: Path, offline: bool,
                   baixar: Callable[[str], dict | None] | None = None) -> tuple[dict | None, bool]:
    """(carteira, veio_do_cache). Baixa da B3; em falha ou offline, usa a última gravada."""
    baixar = baixar or baixar_carteira
    salvas = _ler_json(arquivo)
    if not offline:
        try:
            c = baixar(INDICES[chave][0])
        except Exception:  # rede ou formato: cai no cache
            c = None
        if c:
            salvas[chave] = c
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(json.dumps(salvas, ensure_ascii=False), encoding="utf-8")
            return c, False
    c = salvas.get(chave)
    return (c, True) if c else (None, False)


def _id_cache(simbolo: str) -> str:
    return simbolo.replace("^", "idx_")


def obter_precos(simbolos: list[str], cache: Cache, offline: bool,
                 baixar: Callable[[str], tuple[pd.Series, bool]] | None = None) -> dict[str, Preco]:
    """Preços por símbolo do Yahoo; em falha ou offline, o CSV do cache (marcado desatualizado)."""
    baixar = baixar or fontes.yahoo_ajustado

    def um(simbolo: str) -> tuple[str, Preco]:
        if not offline:
            try:
                s, com_proventos = baixar(simbolo)
                if s is not None and not s.empty:
                    cache.gravar(_id_cache(simbolo), s)
                    return simbolo, Preco(s, False, not com_proventos)
            except Exception:  # rede ou parsing: cai no cache
                pass
        try:
            s = cache.ler(_id_cache(simbolo))
        except Exception:  # CSV corrompido: trata como sem cache
            s = None
        return simbolo, Preco(s, s is not None, False)

    with ThreadPoolExecutor(max_workers=DOWNLOADS_SIMULTANEOS) as ex:
        return dict(ex.map(um, simbolos))


def carregar_fiis(arquivo: Path, avisos: list[str]) -> dict[str, str]:
    """Ticker -> tipo. Tipo fora de `_tipos` vira Outros com aviso; arquivo ruim vira {} com aviso."""
    try:
        bruto = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    except FileNotFoundError:
        avisos.append("fiis.json ausente: todos os FIIs ficam em Outros.")
        return {}
    except (OSError, ValueError) as e:
        avisos.append(f"fiis.json inválido ({e}): todos os FIIs ficam em Outros.")
        return {}
    if not isinstance(bruto, dict):
        avisos.append("fiis.json inválido (esperado um objeto): todos os FIIs ficam em Outros.")
        return {}
    validos = set(bruto.get("_tipos") or []) & set(TIPOS_FII)
    tipos, ruins = {}, []
    for ticker, tipo in bruto.items():
        if ticker.startswith("_"):
            continue
        if tipo in validos:
            tipos[ticker] = tipo
        else:
            tipos[ticker] = OUTROS
            ruins.append(ticker)
    if ruins:
        n = len(ruins)
        avisos.append(f"fiis.json: tipo desconhecido em {', '.join(sorted(ruins))} (fica{'' if n == 1 else 'm'} em Outros).")
    return tipos


def obter(pasta: Path, offline: bool, avisos: list[str], baixar_carteira_=None, baixar_preco=None) -> dict | None:
    """Bloco `bolsa` do dados.json. Os avisos vão para o bloco e para a lista geral."""
    pasta = Path(pasta)
    cache = Cache(pasta / "cache" / "bolsa")
    meus: list[str] = []
    tipos = carregar_fiis(pasta / "fiis.json", meus)
    visoes = {}
    for chave, (_, nome, simbolo_indice) in INDICES.items():
        carteira, do_cache = obter_carteira(chave, pasta / "cache" / "carteiras.json", offline, baixar_carteira_)
        if do_cache and not offline:
            data = pd.Timestamp(carteira["data"]).strftime("%d/%m/%Y")
            meus.append(f"{nome}: carteira da B3 indisponível; usando a de {data}.")
        tickers = [a["ticker"] for a in (carteira or {}).get("ativos", [])]
        precos = obter_precos([simbolo_indice] + [t + ".SA" for t in tickers], cache, offline, baixar_preco)
        preco_indice = precos.pop(simbolo_indice)
        indice = preco_indice.serie
        por_ticker = {s.removesuffix(".SA"): p for s, p in precos.items()}
        visoes[chave] = montar_visao(chave, carteira, do_cache, por_ticker, indice,
                                     tipos if chave == "ifix" else None, meus,
                                     indice_desatualizado=preco_indice.desatualizado)
    if all(v is None for v in visoes.values()):
        meus.append("Bolsa: sem carteiras e sem preços; a aba fica vazia nesta atualização.")
        avisos.extend(meus)
        return None
    avisos.extend(meus)
    return {**visoes, "avisos": meus}
