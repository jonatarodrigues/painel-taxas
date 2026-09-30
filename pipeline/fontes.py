"""Download e parsing das fontes públicas: BCB SGS, FRED, Yahoo Finance e IPEA."""
from __future__ import annotations

import io
import re
import time
from datetime import date
from urllib.parse import quote

import pandas as pd
import requests

from pipeline.series import Serie

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; painel-taxas/1.0)"}
TIMEOUT = 30
TENTATIVAS = 3
ANO_INICIAL = 1980
YAHOO_PERIOD1 = -2208988800  # 1900-01-01: pega o histórico completo (S&P começa em 1927)


class RespostaVazia(Exception):
    """A fonte respondeu, mas sem dados utilizáveis."""


class RespostaInvalida(requests.RequestException):
    """Status 200 com corpo que não é JSON (o firewall do BCB faz isso de vez em quando)."""


def _get(url: str, params: dict | None = None, timeout: int = TIMEOUT, json: bool = False) -> requests.Response | None:
    """GET com tentativas. Retorna None em 404 (o BCB usa 404 para janela sem dados).

    Com json=True, um corpo que não é JSON também conta como falha e é repetido.
    """
    erro: Exception | None = None
    for i in range(TENTATIVAS):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            if json:
                try:
                    r.json()
                except ValueError:
                    raise RespostaInvalida(f"resposta não é JSON: {_resumo(r.text)}") from None
            return r
        except requests.RequestException as e:
            erro = e
            if i < TENTATIVAS - 1:
                time.sleep(2 * (i + 1))
    assert erro is not None
    raise erro


def _resumo(texto: str) -> str:
    """Texto visível de uma página de erro, curto o bastante para o aviso do painel."""
    visivel = " ".join(re.sub(r"<[^>]*>", " ", texto).split())
    return visivel[:80] or "(vazio)"


def _limpar(s: pd.Series) -> pd.Series:
    s = s.dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index().astype(float)
    s.index = pd.DatetimeIndex(s.index, name="data")
    return s


def _vazia() -> pd.Series:
    return pd.Series(dtype=float, index=pd.DatetimeIndex([], name="data"))


# ---------------- BCB SGS ----------------
def parse_bcb(registros: list[dict]) -> pd.Series:
    if not registros:
        return _vazia()
    df = pd.DataFrame(registros)
    idx = pd.to_datetime(df["data"], format="%d/%m/%Y")
    valores = pd.to_numeric(df["valor"], errors="coerce")
    return _limpar(pd.Series(valores.to_numpy(), index=pd.DatetimeIndex(idx)))


def bcb(codigo: str, freq: str, hoje: date | None = None) -> pd.Series:
    hoje = hoje or date.today()
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
    if freq == "m":
        r = _get(url, {"formato": "json"}, timeout=60, json=True)
        s = parse_bcb(r.json() if r is not None else [])
    else:
        partes = []
        inicio = date(ANO_INICIAL, 1, 1)
        while inicio <= hoje:
            fim = min(date(inicio.year + 9, 12, 31), hoje)
            r = _get(url, {"formato": "json",
                           "dataInicial": inicio.strftime("%d/%m/%Y"),
                           "dataFinal": fim.strftime("%d/%m/%Y")}, timeout=60, json=True)
            if r is not None:
                partes.append(parse_bcb(r.json()))
            inicio = date(fim.year + 1, 1, 1)
        s = _limpar(pd.concat(partes)) if partes else _vazia()
    if s.empty:
        return s
    # A série 432 (Selic meta) vem preenchida até a próxima reunião do Copom.
    return s[s.index <= pd.Timestamp(hoje)]


# ---------------- FRED ----------------
def parse_fred(texto: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(texto), na_values=["."])
    if df.shape[1] < 2:
        return _vazia()
    datas = pd.to_datetime(df.iloc[:, 0])
    valores = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    return _limpar(pd.Series(valores.to_numpy(), index=pd.DatetimeIndex(datas)))


def fred(codigo: str) -> pd.Series:
    r = _get("https://fred.stlouisfed.org/graph/fredgraph.csv", {"id": codigo})
    return parse_fred(r.text) if r is not None else _vazia()


# ---------------- Yahoo Finance ----------------
def parse_yahoo(payload: dict) -> pd.Series:
    try:
        res = payload["chart"]["result"][0]
        ts = res["timestamp"]
        close = res["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        return _vazia()
    idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert(None).normalize()
    return _limpar(pd.Series(close, index=idx, dtype=float))


def yahoo(ticker: str) -> pd.Series:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker, safe='')}"
    r = _get(url, {"period1": YAHOO_PERIOD1, "period2": int(time.time()), "interval": "1d"}, json=True)
    return parse_yahoo(r.json()) if r is not None else _vazia()


# ---------------- IPEA ----------------
def parse_ipea(payload: dict) -> pd.Series:
    valores = payload.get("value") or []
    if not valores:
        return _vazia()
    df = pd.DataFrame(valores)
    # VALDATA vem como "1994-04-29T00:00:00-03:00"; o dia civil é o dos 10 primeiros caracteres.
    idx = pd.to_datetime(df["VALDATA"].astype(str).str.slice(0, 10), format="%Y-%m-%d")
    vals = pd.to_numeric(df["VALVALOR"], errors="coerce")
    return _limpar(pd.Series(vals.to_numpy(), index=pd.DatetimeIndex(idx)))


def ipea(codigo: str) -> pd.Series:
    url = f"http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{codigo}')"
    r = _get(url, json=True)
    return parse_ipea(r.json()) if r is not None else _vazia()


# ---------------- despacho ----------------
def baixar(serie: Serie, hoje: date | None = None) -> pd.Series:
    if serie.fonte == "bcb":
        return bcb(serie.codigo, serie.freq, hoje)
    if serie.fonte == "fred":
        return fred(serie.codigo)
    if serie.fonte == "yahoo":
        return yahoo(serie.codigo)
    if serie.fonte == "ipea":
        return ipea(serie.codigo)
    raise ValueError(f"fonte desconhecida: {serie.fonte}")
