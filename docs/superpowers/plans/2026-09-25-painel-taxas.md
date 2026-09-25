# Painel de Taxas de Mercado — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Painel web local que acompanha ~29 taxas e indicadores (juros, inflação, câmbio, exterior, bolsa, macro Brasil) com histórico máximo, eventos que explicam os movimentos, e um grafo de rede de correlações.

**Architecture:** Um pipeline Python (`atualizar.py` + pacote `pipeline/`) baixa as séries de BCB, FRED, Yahoo Finance e IPEA, guarda cache CSV por série, alinha tudo em base diária e mensal, calcula matrizes de correlação em quatro janelas e grava `dados.json` e `dados.js`. Uma página estática (`painel.html` + `painel.css` + `painel.js`) lê esse arquivo e desenha KPIs, séries com faixa de eventos, grafo "cérebro", heatmap e linha do tempo com Apache ECharts.

**Tech Stack:** Python 3.12, pandas 3, numpy, requests, pytest 8; HTML/CSS/JS sem build, Apache ECharts 5.5 via jsdelivr, Google Fonts (Inter).

**Spec:** `docs/superpowers/specs/2026-09-25-painel-taxas-design.md`

## Global Constraints

- Python 3.12; pandas >= 2.2 (instalado: 3.0.5); requests; numpy; pytest >= 8.
- Nenhuma chave de API. Fontes: BCB SGS, FRED CSV público, Yahoo Finance `v8/finance/chart` (com `User-Agent` de navegador), IPEA OData.
- BCB: séries diárias baixadas em janelas de 10 anos; `404` = janela vazia, não erro; série 432 cortada em "hoje".
- Correlação: Pearson sobre base mensal; mínimo 24 meses por par; janelas `tudo`, `10a` (120 meses), `5a` (60), `3a` (36) — a janela curta passou de 24 para 36 meses durante a execução (ruling registrado no ledger); arestas exportadas com `|r| >= 0.15`.
- Transformações: `diff` (variação em p.p.), `logret` (retorno log, ignora valores <= 0), `nivel`.
- Painel: sem build; tema escuro padrão; **um único eixo Y** (modos Base 100 / Nível); paleta de grupos exatamente a da spec §6; positivo azul / negativo vermelho; nomes e textos inseridos no DOM só via `textContent`.
- Todos os textos voltados ao usuário em português do Brasil. Identificadores de código em português sem acento (`para_mensal`, `renderCerebro`).
- Tamanho de `dados.json` abaixo de 16 MB.
- Scripts externos só do jsdelivr, sempre com `integrity="sha384-…"` e `crossorigin="anonymous"` (hash do ECharts 5.5.1 já calculado na Task 10; ao trocar a versão, recalcule com `openssl dgst -sha384 -binary arquivo | openssl base64 -A`).
- Windows: `atualizar.py` reconfigura stdout para UTF-8 antes de imprimir.

## Review Focus

1. **Selic meta com datas futuras** (série 432 vem preenchida até a próxima reunião do Copom): o pipeline deve cortar em hoje. Teste em Task 2 (`test_bcb_corta_datas_futuras`).
2. **BCB responde 404 para janelas sem dados** (Selic meta antes de 1999): deve virar janela vazia e as janelas seguintes ainda serem baixadas. Teste em Task 2 (`test_bcb_janelas_e_404`).
3. **Petróleo negativo em abril/2020**: `logret` deve ignorar valores não positivos em vez de gerar NaN. Teste em Task 4 (`test_logret_ignora_nao_positivos`).
4. **Série curta demais** (menos de 24 meses): sai da correlação sem erro, mas continua nos gráficos. Teste em Task 5 (`test_serie_curta_excluida`) e Task 7 (`test_montar_mantem_serie_curta`).
5. **`dados.json` sem NaN nem `Infinity`**: `json.dumps(allow_nan=False)` deve passar com séries reais que têm buracos. Teste em Task 7 (`test_gravar_sem_nan`).

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `requirements.txt`, `.gitignore`, `README.md` | dependências, arquivos gerados fora do git, instruções de uso |
| `pipeline/series.py` | catálogo das séries (id, nome, grupo, fonte, código, unidade, freq, transformação) e derivadas |
| `pipeline/fontes.py` | download e parsing de BCB, FRED, Yahoo, IPEA; `baixar(serie)` |
| `pipeline/cache.py` | cache CSV por série e `obter(serie, cache, offline)` com fallback |
| `pipeline/transformar.py` | diária/mensal, acumulado 12m, transformações, derivadas |
| `pipeline/correlacao.py` | matrizes por janela, contagens e arestas |
| `pipeline/ciclos.py` | eventos automáticos de virada de ciclo da Selic |
| `pipeline/exportar.py` | monta e grava `dados.json` / `dados.js` |
| `atualizar.py` | orquestra e imprime o resumo |
| `eventos.json` | base curada de eventos |
| `painel.html`, `painel.css`, `painel.js` | o painel |
| `tests/…` | pytest por módulo, fixtures sem rede |

---

### Task 1: Esqueleto do projeto, git e catálogo de séries

**Files:**
- Create: `requirements.txt`, `.gitignore`, `pipeline/__init__.py`, `pipeline/series.py`, `tests/__init__.py`, `tests/test_series.py`

**Interfaces:**
- Produces: `Serie` (dataclass congelada com campos `id, nome, grupo, fonte, codigo, unidade, freq, transformacao`), `SERIES: list[Serie]`, `DERIVADAS: list[Serie]`, `POR_ID: dict[str, Serie]`, `GRUPOS: dict[str, str]`.

- [ ] **Step 1: Iniciar o repositório e arquivos de base**

```bash
cd "<pasta do projeto>"
git init -b main
```

`.gitignore`:
```
__pycache__/
.pytest_cache/
cache/
dados.json
dados.js
.remember/
.sonar/
```

`requirements.txt`:
```
pandas>=2.2
numpy>=1.26
requests>=2.31
pytest>=8
```

Crie `pipeline/__init__.py` e `tests/__init__.py` vazios.

- [ ] **Step 2: Escrever o teste do catálogo**

`tests/test_series.py`:
```python
from pipeline.series import DERIVADAS, GRUPOS, POR_ID, SERIES


def test_ids_unicos():
    ids = [s.id for s in SERIES + DERIVADAS]
    assert len(ids) == len(set(ids))


def test_campos_validos():
    for s in SERIES + DERIVADAS:
        assert s.grupo in GRUPOS
        assert s.fonte in {"bcb", "fred", "yahoo", "ipea", "derivada"}
        assert s.freq in {"d", "m"}
        assert s.transformacao in {"diff", "logret", "nivel"}


def test_derivadas_referenciam_series_existentes():
    for d in DERIVADAS:
        for base in d.codigo.split("-"):
            assert base in POR_ID, base


def test_catalogo_tem_as_series_da_spec():
    for id in ["selic_meta", "cdi", "ipca", "usd_brl", "fed_funds", "ibovespa", "sp500", "embi"]:
        assert id in POR_ID
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `python -m pytest tests/test_series.py -q`
Expected: erro `ModuleNotFoundError: No module named 'pipeline.series'`.

- [ ] **Step 4: Escrever `pipeline/series.py`**

```python
"""Catálogo das séries do painel."""
from dataclasses import dataclass

GRUPOS = {
    "juros": "Juros Brasil",
    "inflacao": "Inflação Brasil",
    "cambio": "Câmbio",
    "bolsa": "Bolsa e commodities",
    "macro": "Macro Brasil",
    "exterior": "Exterior",
}


@dataclass(frozen=True)
class Serie:
    id: str
    nome: str
    grupo: str
    fonte: str          # bcb | fred | yahoo | ipea | derivada
    codigo: str         # código na fonte; nas derivadas, ids-base separados por "-"
    unidade: str
    freq: str           # d (diária) | m (mensal)
    transformacao: str  # diff | logret | nivel (para a correlação)


SERIES = [
    Serie("selic_meta", "Selic meta", "juros", "bcb", "432", "% a.a.", "d", "diff"),
    Serie("selic_efetiva", "Selic efetiva", "juros", "bcb", "1178", "% a.a.", "d", "diff"),
    Serie("cdi", "CDI", "juros", "bcb", "4389", "% a.a.", "d", "diff"),
    Serie("ipca", "IPCA mensal", "inflacao", "bcb", "433", "% a.m.", "m", "nivel"),
    Serie("ipca15", "IPCA-15 mensal", "inflacao", "bcb", "7478", "% a.m.", "m", "nivel"),
    Serie("igpm", "IGP-M mensal", "inflacao", "bcb", "189", "% a.m.", "m", "nivel"),
    Serie("inpc", "INPC mensal", "inflacao", "bcb", "188", "% a.m.", "m", "nivel"),
    Serie("usd_brl", "Dólar (USD/BRL)", "cambio", "bcb", "1", "R$", "d", "logret"),
    Serie("eur_brl", "Euro (EUR/BRL)", "cambio", "bcb", "21619", "R$", "d", "logret"),
    Serie("ibc_br", "IBC-Br", "macro", "bcb", "24363", "índice", "m", "logret"),
    Serie("desemprego", "Desemprego (PNAD)", "macro", "bcb", "24369", "%", "m", "diff"),
    Serie("divida_pib", "Dívida bruta / PIB", "macro", "bcb", "13762", "% PIB", "m", "diff"),
    Serie("primario_pib", "Resultado primário 12m / PIB", "macro", "bcb", "5793", "% PIB", "m", "diff"),
    Serie("embi", "Risco-país (EMBI+)", "macro", "ipea", "JPM366_EMBI366", "pontos", "d", "diff"),
    Serie("fed_funds", "Fed Funds efetiva", "exterior", "fred", "DFF", "% a.a.", "d", "diff"),
    Serie("treasury_2y", "Treasury 2 anos", "exterior", "fred", "DGS2", "% a.a.", "d", "diff"),
    Serie("treasury_10y", "Treasury 10 anos", "exterior", "fred", "DGS10", "% a.a.", "d", "diff"),
    Serie("cpi_eua", "CPI EUA", "exterior", "fred", "CPIAUCSL", "índice", "m", "logret"),
    Serie("dxy", "Índice dólar (DXY)", "exterior", "fred", "DTWEXBGS", "índice", "d", "logret"),
    Serie("vix", "VIX", "exterior", "fred", "VIXCLS", "pontos", "d", "diff"),
    Serie("petroleo", "Petróleo WTI", "bolsa", "fred", "DCOILWTICO", "USD", "d", "logret"),
    Serie("ibovespa", "Ibovespa", "bolsa", "yahoo", "^BVSP", "pontos", "d", "logret"),
    Serie("sp500", "S&P 500", "bolsa", "yahoo", "^GSPC", "pontos", "d", "logret"),
    Serie("ouro", "Ouro", "bolsa", "yahoo", "GC=F", "USD/oz", "d", "logret"),
]

DERIVADAS = [
    Serie("ipca_12m", "IPCA 12 meses", "inflacao", "derivada", "ipca", "% 12m", "m", "diff"),
    Serie("igpm_12m", "IGP-M 12 meses", "inflacao", "derivada", "igpm", "% 12m", "m", "diff"),
    Serie("juro_real", "Juro real (Selic − IPCA 12m)", "juros", "derivada", "selic_meta-ipca_12m", "p.p.", "m", "diff"),
    Serie("dif_selic_fed", "Diferencial Selic − Fed Funds", "juros", "derivada", "selic_meta-fed_funds", "p.p.", "m", "diff"),
    Serie("curva_eua", "Inclinação curva EUA (10a − 2a)", "exterior", "derivada", "treasury_10y-treasury_2y", "p.p.", "m", "diff"),
]

POR_ID = {s.id: s for s in SERIES + DERIVADAS}
```

- [ ] **Step 5: Rodar e ver passar**

Run: `python -m pytest tests/test_series.py -q`
Expected: `4 passed`.

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements.txt pipeline tests
git commit -m "feat: catálogo de séries e esqueleto do pipeline"
```

---

### Task 2: Fontes de dados (BCB, FRED, Yahoo, IPEA)

**Files:**
- Create: `pipeline/fontes.py`, `tests/test_fontes.py`, `tests/fixtures/bcb_432.json`, `tests/fixtures/fred_dff.csv`, `tests/fixtures/yahoo_gspc.json`, `tests/fixtures/ipea_embi.json`

**Interfaces:**
- Consumes: `Serie` de `pipeline.series`.
- Produces: `parse_bcb(list[dict]) -> pd.Series`, `parse_fred(str) -> pd.Series`, `parse_yahoo(dict) -> pd.Series`, `parse_ipea(dict) -> pd.Series`, `bcb(codigo, freq, hoje=None)`, `fred(codigo)`, `yahoo(ticker)`, `ipea(codigo)`, `baixar(serie, hoje=None) -> pd.Series`, exceção `RespostaVazia`. Toda série retornada tem `DatetimeIndex` chamado `data`, ordenada, sem duplicatas, `float`.

- [ ] **Step 1: Criar as fixtures**

`tests/fixtures/bcb_432.json`:
```json
[{"data":"01/03/2021","valor":"2.00"},{"data":"17/03/2021","valor":"2.75"},{"data":"18/03/2021","valor":"2.75"},{"data":"18/03/2021","valor":"2.75"},{"data":"19/03/2021","valor":"x"}]
```

`tests/fixtures/fred_dff.csv`:
```
observation_date,DFF
1954-07-01,1.13
1954-07-02,.
1954-07-05,1.25
```

`tests/fixtures/yahoo_gspc.json`:
```json
{"chart":{"result":[{"meta":{"symbol":"^GSPC"},"timestamp":[-1325583000,1758461400,1758547800],"indicators":{"quote":[{"close":[17.66,null,7764.70]}]}}],"error":null}}
```

`tests/fixtures/ipea_embi.json`:
```json
{"@odata.context":"x","value":[{"SERCODIGO":"JPM366_EMBI366","VALDATA":"1994-04-29T00:00:00-03:00","VALVALOR":1120.0},{"SERCODIGO":"JPM366_EMBI366","VALDATA":"1994-05-02T00:00:00-03:00","VALVALOR":null}]}
```

- [ ] **Step 2: Escrever os testes**

`tests/test_fontes.py`:
```python
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pipeline import fontes
from pipeline.series import POR_ID

FIX = Path(__file__).parent / "fixtures"


def test_parse_bcb_ordena_deduplica_e_descarta_invalidos():
    s = fontes.parse_bcb(json.loads((FIX / "bcb_432.json").read_text(encoding="utf-8")))
    assert list(s.index) == [pd.Timestamp("2021-03-01"), pd.Timestamp("2021-03-17"), pd.Timestamp("2021-03-18")]
    assert s.iloc[-1] == 2.75
    assert s.index.name == "data"


def test_parse_bcb_vazio():
    assert fontes.parse_bcb([]).empty


def test_parse_fred_trata_ponto_como_nulo():
    s = fontes.parse_fred((FIX / "fred_dff.csv").read_text())
    assert len(s) == 2
    assert s[pd.Timestamp("1954-07-05")] == 1.25


def test_parse_yahoo_datas_antes_de_1970_e_nulos():
    s = fontes.parse_yahoo(json.loads((FIX / "yahoo_gspc.json").read_text()))
    assert s.index[0] == pd.Timestamp("1927-12-30")
    assert len(s) == 2  # o null foi descartado


def test_parse_yahoo_payload_sem_resultado():
    assert fontes.parse_yahoo({"chart": {"result": None}}).empty


def test_parse_ipea_usa_dia_civil_local():
    s = fontes.parse_ipea(json.loads((FIX / "ipea_embi.json").read_text()))
    assert list(s.index) == [pd.Timestamp("1994-04-29")]
    assert s.iloc[0] == 1120.0


class RespostaFalsa:
    def __init__(self, payload):
        self._payload = payload
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        return self._payload


def test_bcb_janelas_e_404(monkeypatch):
    chamadas = []

    def get_falso(url, params=None):
        chamadas.append(params)
        if params["dataInicial"].endswith("1980"):
            return None  # BCB responde 404 quando a janela não tem dados
        return RespostaFalsa([{"data": params["dataInicial"], "valor": "10"}])

    monkeypatch.setattr(fontes, "_get", get_falso)
    s = fontes.bcb("432", "d", hoje=date(2001, 6, 30))
    assert [c["dataInicial"] for c in chamadas] == ["01/01/1980", "01/01/1990", "01/01/2000"]
    assert [c["dataFinal"] for c in chamadas] == ["31/12/1989", "31/12/1999", "30/06/2001"]
    assert len(s) == 2


def test_bcb_corta_datas_futuras(monkeypatch):
    def get_falso(url, params=None):
        return RespostaFalsa([{"data": "24/09/2026", "valor": "15"}, {"data": "04/11/2026", "valor": "15"}])

    monkeypatch.setattr(fontes, "_get", get_falso)
    s = fontes.bcb("432", "d", hoje=date(2026, 9, 25))
    assert list(s.index) == [pd.Timestamp("2026-09-24")]


def test_bcb_mensal_sem_janela(monkeypatch):
    chamadas = []

    def get_falso(url, params=None):
        chamadas.append(params)
        return RespostaFalsa([{"data": "01/01/1980", "valor": "6.62"}])

    monkeypatch.setattr(fontes, "_get", get_falso)
    s = fontes.bcb("433", "m", hoje=date(2026, 9, 25))
    assert chamadas == [{"formato": "json"}]
    assert s.iloc[0] == 6.62


def test_baixar_despacha_por_fonte(monkeypatch):
    vistos = []
    monkeypatch.setattr(fontes, "bcb", lambda codigo, freq, hoje=None: vistos.append(("bcb", codigo)) or pd.Series(dtype=float))
    monkeypatch.setattr(fontes, "fred", lambda codigo: vistos.append(("fred", codigo)) or pd.Series(dtype=float))
    monkeypatch.setattr(fontes, "yahoo", lambda t: vistos.append(("yahoo", t)) or pd.Series(dtype=float))
    monkeypatch.setattr(fontes, "ipea", lambda c: vistos.append(("ipea", c)) or pd.Series(dtype=float))
    for id in ["selic_meta", "fed_funds", "sp500", "embi"]:
        fontes.baixar(POR_ID[id])
    assert vistos == [("bcb", "432"), ("fred", "DFF"), ("yahoo", "^GSPC"), ("ipea", "JPM366_EMBI366")]


def test_baixar_fonte_desconhecida():
    from pipeline.series import Serie
    with pytest.raises(ValueError):
        fontes.baixar(Serie("x", "x", "juros", "ftp", "1", "u", "d", "diff"))
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `python -m pytest tests/test_fontes.py -q`
Expected: `ModuleNotFoundError: No module named 'pipeline.fontes'`.

- [ ] **Step 4: Escrever `pipeline/fontes.py`**

```python
"""Download e parsing das fontes públicas: BCB SGS, FRED, Yahoo Finance e IPEA."""
from __future__ import annotations

import io
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


def _get(url: str, params: dict | None = None) -> requests.Response | None:
    """GET com tentativas. Retorna None em 404 (o BCB usa 404 para janela sem dados)."""
    erro: Exception | None = None
    for i in range(TENTATIVAS):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            erro = e
            time.sleep(2 * (i + 1))
    assert erro is not None
    raise erro


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
        r = _get(url, {"formato": "json"})
        s = parse_bcb(r.json() if r is not None else [])
    else:
        partes = []
        inicio = date(ANO_INICIAL, 1, 1)
        while inicio <= hoje:
            fim = min(date(inicio.year + 9, 12, 31), hoje)
            r = _get(url, {"formato": "json",
                           "dataInicial": inicio.strftime("%d/%m/%Y"),
                           "dataFinal": fim.strftime("%d/%m/%Y")})
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
    r = _get(url, {"period1": YAHOO_PERIOD1, "period2": int(time.time()), "interval": "1d"})
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
    r = _get(url)
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
```

- [ ] **Step 5: Rodar e ver passar**

Run: `python -m pytest tests/test_fontes.py -q`
Expected: `11 passed`.

- [ ] **Step 6: Teste de fumaça com rede (manual, uma vez)**

Run:
```bash
python -c "from pipeline import fontes; from pipeline.series import POR_ID; [print(i, len(s:=fontes.baixar(POR_ID[i])), s.index.min().date(), s.index.max().date()) for i in ['selic_meta','ipca','fed_funds','sp500','embi']]"
```
Expected: cinco linhas com contagens > 0; `selic_meta` termina em hoje ou antes; `sp500` começa em 1927-12-30.

- [ ] **Step 7: Commit**

```bash
git add pipeline/fontes.py tests/test_fontes.py tests/fixtures
git commit -m "feat: download e parsing das fontes BCB, FRED, Yahoo e IPEA"
```

---

### Task 3: Cache por série e `obter` com fallback

**Files:**
- Create: `pipeline/cache.py`, `tests/test_cache.py`

**Interfaces:**
- Consumes: `fontes.baixar`, `fontes.RespostaVazia`, `Serie`.
- Produces: `Cache(pasta)` com `gravar(id, s)`, `ler(id) -> pd.Series | None`, `modificado_em(id) -> datetime | None`; `obter(serie, cache, offline=False, baixar=fontes.baixar) -> tuple[pd.Series | None, str, str | None]` onde status ∈ {`ok`, `desatualizada`, `ausente`}.

- [ ] **Step 1: Escrever os testes**

`tests/test_cache.py`:
```python
import pandas as pd

from pipeline.cache import Cache, obter
from pipeline.series import POR_ID

SELIC = POR_ID["selic_meta"]


def serie_exemplo():
    idx = pd.DatetimeIndex(pd.to_datetime(["2024-01-02", "2024-01-03"]), name="data")
    return pd.Series([11.75, 11.75], index=idx)


def test_gravar_e_ler_round_trip(tmp_path):
    c = Cache(tmp_path)
    c.gravar("x", serie_exemplo())
    lida = c.ler("x")
    assert isinstance(lida.index, pd.DatetimeIndex)
    assert list(lida.index) == list(serie_exemplo().index)
    assert lida.tolist() == [11.75, 11.75]


def test_ler_inexistente(tmp_path):
    assert Cache(tmp_path).ler("nada") is None
    assert Cache(tmp_path).modificado_em("nada") is None


def test_obter_ok_grava_cache(tmp_path):
    c = Cache(tmp_path)
    s, status, aviso = obter(SELIC, c, baixar=lambda serie: serie_exemplo())
    assert status == "ok" and aviso is None and len(s) == 2
    assert c.ler("selic_meta") is not None


def test_obter_falha_usa_cache(tmp_path):
    c = Cache(tmp_path)
    c.gravar("selic_meta", serie_exemplo())

    def quebrado(serie):
        raise ConnectionError("sem rede")

    s, status, aviso = obter(SELIC, c, baixar=quebrado)
    assert status == "desatualizada" and len(s) == 2
    assert "sem rede" in aviso and "usando cache" in aviso


def test_obter_resposta_vazia_conta_como_falha(tmp_path):
    c = Cache(tmp_path)
    s, status, aviso = obter(SELIC, c, baixar=lambda serie: pd.Series(dtype=float))
    assert s is None and status == "ausente" and "sem cache" in aviso


def test_obter_offline(tmp_path):
    c = Cache(tmp_path)
    assert obter(SELIC, c, offline=True)[1] == "ausente"
    c.gravar("selic_meta", serie_exemplo())
    s, status, aviso = obter(SELIC, c, offline=True, baixar=lambda serie: 1 / 0)
    assert status == "desatualizada" and len(s) == 2
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_cache.py -q`
Expected: `ModuleNotFoundError: No module named 'pipeline.cache'`.

- [ ] **Step 3: Escrever `pipeline/cache.py`**

```python
"""Cache CSV por série e obtenção com fallback."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from pipeline import fontes
from pipeline.series import Serie


class Cache:
    def __init__(self, pasta: Path | str):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)

    def caminho(self, id: str) -> Path:
        return self.pasta / f"{id}.csv"

    def gravar(self, id: str, s: pd.Series) -> None:
        s.rename("valor").rename_axis("data").to_csv(self.caminho(id), date_format="%Y-%m-%d")

    def ler(self, id: str) -> pd.Series | None:
        p = self.caminho(id)
        if not p.exists():
            return None
        df = pd.read_csv(p, parse_dates=["data"], index_col="data")
        s = df["valor"].astype(float)
        s.index = pd.DatetimeIndex(s.index, name="data")
        return s

    def modificado_em(self, id: str) -> datetime | None:
        p = self.caminho(id)
        return datetime.fromtimestamp(p.stat().st_mtime) if p.exists() else None


Resultado = tuple[pd.Series | None, str, str | None]


def obter(serie: Serie, cache: Cache, offline: bool = False,
          baixar: Callable[[Serie], pd.Series] = fontes.baixar) -> Resultado:
    """Retorna (serie, status, aviso). status: ok | desatualizada | ausente."""
    if offline:
        s = cache.ler(serie.id)
        if s is None:
            return None, "ausente", f"{serie.nome}: sem cache (modo offline)"
        return s, "desatualizada", None
    try:
        s = baixar(serie)
        if s is None or s.empty:
            raise fontes.RespostaVazia("resposta vazia")
        cache.gravar(serie.id, s)
        return s, "ok", None
    except Exception as e:  # rede, parsing ou vazio: qualquer falha cai no cache
        s = cache.ler(serie.id)
        if s is not None:
            quando = cache.modificado_em(serie.id)
            return s, "desatualizada", f"{serie.nome}: falha ao baixar ({e}); usando cache de {quando:%Y-%m-%d}"
        return None, "ausente", f"{serie.nome}: falha ao baixar ({e}) e sem cache"
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_cache.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/cache.py tests/test_cache.py
git commit -m "feat: cache CSV por série com fallback offline"
```

---

### Task 4: Transformações (diária, mensal, 12 meses, derivadas)

**Files:**
- Create: `pipeline/transformar.py`, `tests/test_transformar.py`

**Interfaces:**
- Produces: `para_diaria(s, limite_ffill=5) -> pd.Series` (índice de dias úteis), `para_mensal(s, freq) -> pd.Series` (índice `PeriodIndex('M')`), `acumulado_12m(pct_mensal)`, `transformar(mensal, tipo)`, `derivadas(mensais: dict[str, pd.Series]) -> dict[str, pd.Series]` com chaves `ipca_12m`, `igpm_12m`, `juro_real`, `dif_selic_fed`, `curva_eua` quando as bases existem.

- [ ] **Step 1: Escrever os testes**

`tests/test_transformar.py`:
```python
import numpy as np
import pandas as pd
import pytest

from pipeline import transformar as T


def diaria(valores, datas):
    return pd.Series(valores, index=pd.DatetimeIndex(pd.to_datetime(datas), name="data"), dtype=float)


def test_para_diaria_preenche_buraco_curto_e_nao_longo():
    s = diaria([1, 2, 3], ["2024-01-02", "2024-01-04", "2024-01-31"])
    d = T.para_diaria(s, limite_ffill=5)
    assert d[pd.Timestamp("2024-01-03")] == 1          # buraco de 1 dia: preenchido
    assert pd.Timestamp("2024-01-12") not in d.index  # buraco de 18 dias úteis: não
    assert pd.Timestamp("2024-01-06") not in d.index  # sábado nunca entra


def test_para_mensal_diaria_pega_ultimo_do_mes():
    s = diaria([10, 11, 20], ["2024-01-02", "2024-01-31", "2024-02-15"])
    m = T.para_mensal(s, "d")
    assert isinstance(m.index, pd.PeriodIndex)
    assert m[pd.Period("2024-01", "M")] == 11
    assert m[pd.Period("2024-02", "M")] == 20


def test_para_mensal_mensal_mantem_valor():
    s = diaria([0.5, 0.4], ["2024-01-01", "2024-02-01"])
    m = T.para_mensal(s, "m")
    assert list(m.index.astype(str)) == ["2024-01", "2024-02"]


def test_para_mensal_vazia():
    assert T.para_mensal(pd.Series(dtype=float), "d").empty


def test_acumulado_12m():
    idx = pd.period_range("2023-01", periods=13, freq="M")
    s = pd.Series([1.0] * 13, index=idx)
    a = T.acumulado_12m(s)
    assert len(a) == 2
    assert a.iloc[0] == pytest.approx((1.01 ** 12 - 1) * 100)


def test_transformar_diff_e_nivel():
    idx = pd.period_range("2024-01", periods=3, freq="M")
    s = pd.Series([10.0, 10.5, 10.25], index=idx)
    assert list(T.transformar(s, "diff").round(4)) == [0.5, -0.25]
    assert list(T.transformar(s, "nivel")) == [10.0, 10.5, 10.25]


def test_logret_ignora_nao_positivos():
    idx = pd.period_range("2020-02", periods=4, freq="M")
    s = pd.Series([50.0, -37.0, 20.0, 40.0], index=idx)  # WTI ficou negativo em abril/2020
    r = T.transformar(s, "logret")
    assert not r.isna().any()
    assert r.iloc[-1] == pytest.approx(np.log(2))


def test_transformar_tipo_desconhecido():
    with pytest.raises(ValueError):
        T.transformar(pd.Series(dtype=float), "raiz")


def test_derivadas():
    idx = pd.period_range("2023-01", periods=13, freq="M")
    mensais = {
        "ipca": pd.Series([0.5] * 13, index=idx),
        "selic_meta": pd.Series([13.75] * 13, index=idx),
        "fed_funds": pd.Series([5.0] * 13, index=idx),
        "treasury_10y": pd.Series([4.0] * 13, index=idx),
        "treasury_2y": pd.Series([4.5] * 13, index=idx),
    }
    d = T.derivadas(mensais)
    assert set(d) == {"ipca_12m", "juro_real", "dif_selic_fed", "curva_eua"}  # sem igpm -> sem igpm_12m
    assert d["dif_selic_fed"].iloc[-1] == pytest.approx(8.75)
    assert d["curva_eua"].iloc[-1] == pytest.approx(-0.5)
    assert d["juro_real"].iloc[-1] == pytest.approx(13.75 - d["ipca_12m"].iloc[-1])
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_transformar.py -q`
Expected: `ModuleNotFoundError: No module named 'pipeline.transformar'`.

- [ ] **Step 3: Escrever `pipeline/transformar.py`**

```python
"""Alinhamento temporal e transformações para correlação."""
from __future__ import annotations

import numpy as np
import pandas as pd

LIMITE_FFILL = 5


def para_diaria(s: pd.Series, limite_ffill: int = LIMITE_FFILL) -> pd.Series:
    """Reindexa em dias úteis, preenchendo buracos de até `limite_ffill` dias úteis."""
    if s.empty:
        return pd.Series(dtype=float)
    uteis = pd.bdate_range(s.index.min(), s.index.max())
    cheia = s.reindex(s.index.union(uteis)).ffill(limit=limite_ffill)
    return cheia.reindex(uteis).dropna()


def para_mensal(s: pd.Series, freq: str) -> pd.Series:
    """Índice PeriodIndex('M'). Diária: último valor do mês. Mensal: o valor do mês."""
    if s.empty:
        return pd.Series(dtype=float)
    m = s.resample("ME").last().dropna() if freq == "d" else s.dropna().copy()
    m.index = pd.DatetimeIndex(m.index).to_period("M")
    return m[~m.index.duplicated(keep="last")].sort_index()


def acumulado_12m(pct_mensal: pd.Series) -> pd.Series:
    fator = (1 + pct_mensal / 100).rolling(12).apply(np.prod, raw=True)
    return ((fator - 1) * 100).dropna()


def transformar(mensal: pd.Series, tipo: str) -> pd.Series:
    if tipo == "diff":
        return mensal.diff().dropna()
    if tipo == "logret":
        positivos = mensal[mensal > 0]  # WTI negativo em 2020 quebraria o log
        return np.log(positivos).diff().dropna()
    if tipo == "nivel":
        return mensal.dropna()
    raise ValueError(f"transformação desconhecida: {tipo}")


def derivadas(mensais: dict[str, pd.Series]) -> dict[str, pd.Series]:
    def tem(*ids: str) -> bool:
        return all(i in mensais and not mensais[i].empty for i in ids)

    out: dict[str, pd.Series] = {}
    if tem("ipca"):
        out["ipca_12m"] = acumulado_12m(mensais["ipca"])
    if tem("igpm"):
        out["igpm_12m"] = acumulado_12m(mensais["igpm"])
    if "ipca_12m" in out and tem("selic_meta"):
        out["juro_real"] = (mensais["selic_meta"] - out["ipca_12m"]).dropna()
    if tem("selic_meta", "fed_funds"):
        out["dif_selic_fed"] = (mensais["selic_meta"] - mensais["fed_funds"]).dropna()
    if tem("treasury_10y", "treasury_2y"):
        out["curva_eua"] = (mensais["treasury_10y"] - mensais["treasury_2y"]).dropna()
    return out
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_transformar.py -q`
Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/transformar.py tests/test_transformar.py
git commit -m "feat: alinhamento diário/mensal, acumulado 12m e séries derivadas"
```

---

### Task 5: Correlação por janela e arestas

**Files:**
- Create: `pipeline/correlacao.py`, `tests/test_correlacao.py`

**Interfaces:**
- Produces: `JANELAS`, `MIN_MESES = 24`, `CORTE_ARESTA = 0.15`, `matriz(transformadas, meses) -> {"ids": [...], "matriz": [[float|None]], "n": [[int]]}`, `arestas(m, corte) -> list[{"a","b","r","n"}]`, `calcular(transformadas) -> {"correlacao": {janela: m}, "arestas": {janela: [...]}}`.

- [ ] **Step 1: Escrever os testes**

`tests/test_correlacao.py`:
```python
import numpy as np
import pandas as pd

from pipeline import correlacao as C


def mensal(valores, inicio="2000-01"):
    return pd.Series(valores, index=pd.period_range(inicio, periods=len(valores), freq="M"), dtype=float)


def test_matriz_simetrica_com_diagonal_um():
    rng = np.random.default_rng(0)
    x = rng.normal(size=60)
    t = {"a": mensal(x), "b": mensal(x * 2 + rng.normal(scale=0.1, size=60)), "c": mensal(rng.normal(size=60))}
    m = C.matriz(t, None)
    assert m["ids"] == ["a", "b", "c"]
    assert m["matriz"][0][0] == 1.0
    assert m["matriz"][0][1] == m["matriz"][1][0] > 0.95
    assert m["n"][0][1] == 60


def test_sobreposicao_curta_da_nulo():
    t = {"a": mensal(np.arange(40.0)), "b": mensal(np.arange(40.0), inicio="2002-06")}  # 11 meses em comum
    m = C.matriz(t, None)
    assert m["matriz"][0][1] is None
    assert m["n"][0][1] == 11


def test_serie_curta_excluida():
    t = {"a": mensal(np.arange(40.0)), "curta": mensal(np.arange(10.0))}
    assert C.matriz(t, None)["ids"] == ["a"]


def test_janela_recorta_pelos_ultimos_meses():
    t = {"a": mensal(np.arange(200.0)), "b": mensal(np.arange(200.0) ** 2)}
    assert C.matriz(t, 24)["n"][0][1] == 24
    assert C.matriz(t, None)["n"][0][1] == 200


def test_arestas_respeitam_corte_e_ordenam():
    m = {"ids": ["a", "b", "c"], "matriz": [[1, 0.5, 0.1], [0.5, 1, -0.8], [0.1, -0.8, 1]], "n": [[9, 9, 9]] * 3}
    ar = C.arestas(m, corte=0.15)
    assert [(e["a"], e["b"], e["r"]) for e in ar] == [("b", "c", -0.8), ("a", "b", 0.5)]


def test_calcular_tem_todas_as_janelas():
    t = {"a": mensal(np.random.default_rng(1).normal(size=150)), "b": mensal(np.random.default_rng(2).normal(size=150))}
    out = C.calcular(t)
    assert set(out["correlacao"]) == set(out["arestas"]) == {"tudo", "10a", "5a", "3a"}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_correlacao.py -q`
Expected: `ModuleNotFoundError: No module named 'pipeline.correlacao'`.

- [ ] **Step 3: Escrever `pipeline/correlacao.py`**

```python
"""Matrizes de correlação por janela e arestas do grafo."""
from __future__ import annotations

import pandas as pd

JANELAS: dict[str, int | None] = {"tudo": None, "10a": 120, "5a": 60, "3a": 36}
MIN_MESES = 24
CORTE_ARESTA = 0.15


def recortar(df: pd.DataFrame, meses: int | None) -> pd.DataFrame:
    if meses is None or df.empty:
        return df
    ultimo = df.index.max()
    return df[df.index > ultimo - meses]


def matriz(transformadas: dict[str, pd.Series], meses: int | None) -> dict:
    df = pd.DataFrame(transformadas).sort_index()
    df = recortar(df, meses)
    df = df.loc[:, df.notna().sum() >= MIN_MESES]
    ids = list(df.columns)
    r = df.corr(min_periods=MIN_MESES)
    presente = df.notna().astype(int)
    n = presente.T @ presente
    k = len(ids)
    mat = [[None if pd.isna(r.iat[i, j]) else round(float(r.iat[i, j]), 4) for j in range(k)] for i in range(k)]
    cont = [[int(n.iat[i, j]) for j in range(k)] for i in range(k)]
    return {"ids": ids, "matriz": mat, "n": cont}


def arestas(m: dict, corte: float = CORTE_ARESTA) -> list[dict]:
    ids, mat, n = m["ids"], m["matriz"], m["n"]
    out = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            r = mat[i][j]
            if r is not None and abs(r) >= corte:
                out.append({"a": ids[i], "b": ids[j], "r": r, "n": n[i][j]})
    return sorted(out, key=lambda e: -abs(e["r"]))


def calcular(transformadas: dict[str, pd.Series]) -> dict:
    correl, ars = {}, {}
    for nome, meses in JANELAS.items():
        m = matriz(transformadas, meses)
        correl[nome] = m
        ars[nome] = arestas(m)
    return {"correlacao": correl, "arestas": ars}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_correlacao.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/correlacao.py tests/test_correlacao.py
git commit -m "feat: correlação de Pearson por janela e arestas do grafo"
```

---

### Task 6: Eventos automáticos de ciclo da Selic

**Files:**
- Create: `pipeline/ciclos.py`, `tests/test_ciclos.py`

**Interfaces:**
- Produces: `ciclos_copom(selic_meta: pd.Series) -> list[dict]` com eventos `{"data", "titulo", "categoria": "copom", "descricao", "series", "auto": True}`.

- [ ] **Step 1: Escrever os testes**

`tests/test_ciclos.py`:
```python
import pandas as pd

from pipeline.ciclos import ciclos_copom


def selic(pares):
    datas, valores = zip(*pares)
    return pd.Series(valores, index=pd.DatetimeIndex(pd.to_datetime(datas), name="data"), dtype=float)


def test_uma_virada_por_mudanca_de_direcao():
    s = selic([("2021-01-01", 2.0), ("2021-03-17", 2.75), ("2021-05-05", 3.5), ("2022-08-03", 13.75),
               ("2023-08-02", 13.25), ("2024-05-08", 10.5), ("2024-09-18", 10.75)])
    ev = ciclos_copom(s)
    assert [e["data"] for e in ev] == ["2021-03-17", "2023-08-02", "2024-09-18"]
    assert ev[0]["titulo"] == "Copom inicia ciclo de alta: 2,00% → 2,75%"
    assert ev[1]["titulo"].startswith("Copom inicia ciclo de baixa")
    assert all(e["categoria"] == "copom" and e["auto"] is True for e in ev)


def test_dias_repetidos_nao_geram_evento():
    s = selic([("2021-01-01", 2.0), ("2021-01-04", 2.0), ("2021-01-05", 2.0)])
    assert ciclos_copom(s) == []


def test_vazia():
    assert ciclos_copom(pd.Series(dtype=float)) == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_ciclos.py -q`
Expected: `ModuleNotFoundError: No module named 'pipeline.ciclos'`.

- [ ] **Step 3: Escrever `pipeline/ciclos.py`**

```python
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_ciclos.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/ciclos.py tests/test_ciclos.py
git commit -m "feat: eventos automáticos de virada de ciclo da Selic"
```

---

### Task 7: Exportação do `dados.json` / `dados.js`

**Files:**
- Create: `pipeline/exportar.py`, `tests/test_exportar.py`

**Interfaces:**
- Consumes: `Serie`, saídas de `transformar` e `correlacao.calcular`.
- Produces: `resumo_serie(serie, diaria, mensal, status) -> dict`, `montar(metas, diarias, mensais, status, avisos, correl, eventos, gerado_em=None) -> dict`, `gravar(dados, pasta)` que escreve `dados.json` e `dados.js`.

- [ ] **Step 1: Escrever os testes**

`tests/test_exportar.py`:
```python
import json

import numpy as np
import pandas as pd

from pipeline import correlacao, exportar, transformar
from pipeline.series import POR_ID


def diaria(n, inicio="2020-01-01", base=100.0):
    idx = pd.bdate_range(inicio, periods=n, name="data")
    return pd.Series(base + np.arange(n, dtype=float), index=idx)


def montar_exemplo():
    brutas = {"usd_brl": diaria(700, base=4.0), "selic_meta": diaria(700, base=10.0), "cdi": diaria(30, base=10.0)}
    diarias = {k: transformar.para_diaria(v) for k, v in brutas.items()}
    mensais = {k: transformar.para_mensal(v, "d") for k, v in brutas.items()}
    mensais["usd_brl"].iloc[3] = np.nan  # buraco de propósito
    transformadas = {k: transformar.transformar(m, POR_ID[k].transformacao) for k, m in mensais.items()}
    correl = correlacao.calcular(transformadas)
    metas = {k: POR_ID[k] for k in brutas}
    eventos = [{"data": "2020-03-11", "titulo": "t", "categoria": "crise", "descricao": "d", "series": ["usd_brl"]}]
    return exportar.montar(metas, diarias, mensais, {k: "ok" for k in brutas}, ["aviso x"], correl, eventos)


def test_montar_formato():
    d = montar_exemplo()
    assert set(d) == {"gerado_em", "series", "correlacao", "arestas", "eventos", "avisos"}
    usd = d["series"]["usd_brl"]
    assert usd["var_tipo"] == "pct" and d["series"]["selic_meta"]["var_tipo"] == "pp"
    assert usd["diario"][0][0] == "2020-01-01" and len(usd["diario"][0]) == 2
    assert usd["mensal"][0][0] == "2020-01"
    assert usd["inicio"] == "2020-01-01" and usd["fim"] == usd["diario"][-1][0]
    assert usd["ultimo"] == usd["mensal"][-1][1]
    assert usd["var_1m"] is not None and usd["var_12m"] is not None
    assert "n" in d["correlacao"]["tudo"]


def test_montar_mantem_serie_curta():
    d = montar_exemplo()
    assert "cdi" in d["series"]                         # fica nos gráficos
    assert "cdi" not in d["correlacao"]["tudo"]["ids"]  # mas sai da correlação
    assert d["series"]["cdi"]["var_12m"] is None


def test_gravar_sem_nan(tmp_path):
    d = montar_exemplo()
    exportar.gravar(d, tmp_path)
    texto = (tmp_path / "dados.json").read_text(encoding="utf-8")
    assert "NaN" not in texto and "Infinity" not in texto
    assert json.loads(texto)["avisos"] == ["aviso x"]
    js = (tmp_path / "dados.js").read_text(encoding="utf-8")
    assert js.startswith("window.DADOS = {") and js.rstrip().endswith("};")


def test_variacao_percentual_e_pontos():
    m = pd.Series([100.0, 110.0], index=pd.period_range("2024-01", periods=2, freq="M"))
    assert exportar._variacao(m, 1, pct=True) == 10.0
    assert exportar._variacao(m, 1, pct=False) == 10.0
    assert exportar._variacao(m, 12, pct=True) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_exportar.py -q`
Expected: `ModuleNotFoundError: No module named 'pipeline.exportar'`.

- [ ] **Step 3: Escrever `pipeline/exportar.py`**

```python
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
    m = m.dropna()
    if len(m) <= defasagem:
        return None
    atual, antes = float(m.iloc[-1]), float(m.iloc[-1 - defasagem])
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
    return {
        "nome": serie.nome,
        "grupo": serie.grupo,
        "unidade": serie.unidade,
        "fonte": "derivada" if serie.fonte == "derivada" else f"{serie.fonte.upper()} {serie.codigo}",
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_exportar.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/exportar.py tests/test_exportar.py
git commit -m "feat: exportação de dados.json e dados.js"
```

---

### Task 8: Base curada de eventos

**Files:**
- Create: `eventos.json`, `tests/test_eventos.py`

**Interfaces:**
- Produces: `eventos.json`, lista de objetos `{"data","titulo","categoria","descricao","series"}` com `series` referenciando ids de `POR_ID`.

- [ ] **Step 1: Escrever o teste de integridade**

`tests/test_eventos.py`:
```python
import json
import re
from pathlib import Path

from pipeline.series import POR_ID

CATEGORIAS = {"copom", "fomc", "crise", "politica", "fiscal", "externo", "plano"}


def test_eventos_json_integro():
    eventos = json.loads((Path(__file__).parent.parent / "eventos.json").read_text(encoding="utf-8"))
    assert len(eventos) >= 60
    datas = []
    for e in eventos:
        assert set(e) == {"data", "titulo", "categoria", "descricao", "series"}, e["titulo"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["data"]), e["data"]
        assert e["categoria"] in CATEGORIAS, e["titulo"]
        assert 10 <= len(e["descricao"]) <= 400, e["titulo"]
        assert e["series"] and all(s in POR_ID for s in e["series"]), e["titulo"]
        datas.append(e["data"])
    assert datas == sorted(datas), "eventos devem estar em ordem cronológica"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_eventos.py -q`
Expected: `FileNotFoundError: eventos.json`.

- [ ] **Step 3: Escrever `eventos.json`**

```json
[
{"data":"1986-02-28","titulo":"Plano Cruzado","categoria":"plano","descricao":"Congelamento de preços e salários e troca do cruzeiro pelo cruzado. A inflação cai de 15% ao mês para perto de zero, mas volta a explodir no fim do ano.","series":["ipca","igpm","inpc"]},
{"data":"1987-02-20","titulo":"Moratória da dívida externa","categoria":"crise","descricao":"O governo Sarney suspende o pagamento de juros aos bancos credores. O país fica isolado do crédito externo até a renegociação de 1994.","series":["ipca","usd_brl"]},
{"data":"1987-06-12","titulo":"Plano Bresser","categoria":"plano","descricao":"Novo congelamento de preços e desvalorização cambial. A inflação volta a acelerar em poucos meses.","series":["ipca","inpc"]},
{"data":"1989-01-15","titulo":"Plano Verão","categoria":"plano","descricao":"Cruzado novo, congelamento e corte de três zeros. Fracassa e o país entra em hiperinflação: IPCA de 82% em março de 1990.","series":["ipca","inpc","igpm"]},
{"data":"1990-03-16","titulo":"Plano Collor","categoria":"plano","descricao":"Confisco de cerca de 80% dos depósitos e aplicações por 18 meses. Choque recessivo: a inflação cai de 82% para 9% ao mês e volta a subir.","series":["ipca","inpc","igpm"]},
{"data":"1991-01-31","titulo":"Plano Collor II","categoria":"plano","descricao":"Congelamento de preços e fim do overnight. Último plano heterodoxo antes do Real.","series":["ipca","inpc"]},
{"data":"1992-09-29","titulo":"Câmara aprova o impeachment de Collor","categoria":"politica","descricao":"Collor é afastado e renuncia em dezembro. Itamar Franco assume e, em maio de 1993, nomeia FHC para a Fazenda.","series":["ipca","usd_brl"]},
{"data":"1994-03-01","titulo":"URV entra em vigor","categoria":"plano","descricao":"A Unidade Real de Valor indexa a economia a um único padrão por quatro meses, preparando a troca de moeda.","series":["ipca","inpc"]},
{"data":"1994-07-01","titulo":"Plano Real","categoria":"plano","descricao":"Nova moeda com âncora cambial e juros altos. O IPCA cai de 47% em junho para 1,5% em setembro. Início do histórico consistente da maioria das séries.","series":["ipca","inpc","igpm","usd_brl","selic_efetiva"]},
{"data":"1994-12-20","titulo":"Crise do México (Tequila)","categoria":"externo","descricao":"A desvalorização do peso mexicano contamina os emergentes. O Brasil perde reservas e adota bandas cambiais em março de 1995.","series":["usd_brl","selic_efetiva","ibovespa","embi"]},
{"data":"1995-03-06","titulo":"Bandas cambiais","categoria":"plano","descricao":"O BC passa a administrar o câmbio em bandas com minidesvalorizações mensais. O regime dura até janeiro de 1999.","series":["usd_brl","selic_efetiva"]},
{"data":"1997-07-02","titulo":"Crise asiática","categoria":"externo","descricao":"A Tailândia abandona a paridade do baht e o contágio derruba bolsas emergentes. Em outubro o BC dobra os juros para 43% ao ano para defender o real.","series":["ibovespa","usd_brl","selic_efetiva","sp500","embi"]},
{"data":"1998-08-17","titulo":"Moratória russa","categoria":"externo","descricao":"A Rússia dá calote na dívida interna e desvaloriza o rublo. Fuga de capitais do Brasil de cerca de US$ 30 bilhões; juros vão a 49%.","series":["selic_efetiva","ibovespa","usd_brl","embi"]},
{"data":"1998-11-13","titulo":"Acordo com o FMI de US$ 41,5 bilhões","categoria":"fiscal","descricao":"Pacote de ajuste fiscal e financiamento externo tenta segurar a âncora cambial após a crise russa.","series":["embi","usd_brl","selic_efetiva"]},
{"data":"1999-01-15","titulo":"Câmbio passa a flutuar","categoria":"plano","descricao":"Depois de alargar a banda em 13/01, o BC deixa o real flutuar. O dólar sai de R$ 1,21 para R$ 2,16 em seis semanas e a inflação sobe menos do que se temia.","series":["usd_brl","ipca","igpm","embi","ibovespa"]},
{"data":"1999-03-04","titulo":"Armínio Fraga assume o BC e Selic vai a 45%","categoria":"plano","descricao":"O Copom passa a fixar a meta da Selic; a série 432 começa nesta data. Os juros caem rapidamente ao longo do ano.","series":["selic_meta","usd_brl","embi"]},
{"data":"1999-06-21","titulo":"Regime de metas de inflação","categoria":"plano","descricao":"O Decreto 3.088 institui as metas de inflação, com o IPCA como índice oficial e o BC responsável por persegui-las.","series":["ipca","selic_meta"]},
{"data":"2000-05-04","titulo":"Lei de Responsabilidade Fiscal","categoria":"fiscal","descricao":"A LRF impõe limites de gasto com pessoal e endividamento a União, estados e municípios.","series":["primario_pib","embi"]},
{"data":"2001-06-01","titulo":"Racionamento de energia","categoria":"crise","descricao":"O governo impõe corte de 20% no consumo de eletricidade até fevereiro de 2002. A atividade desacelera e o dólar sobe.","series":["ibovespa","ipca","usd_brl"]},
{"data":"2001-09-11","titulo":"Atentados de 11 de setembro","categoria":"externo","descricao":"Bolsas americanas fecham por quase uma semana e o Fed corta os juros para 1,75% até dezembro. No Brasil o dólar chega a R$ 2,80.","series":["sp500","usd_brl","fed_funds","ibovespa","embi"]},
{"data":"2001-12-23","titulo":"Calote da Argentina","categoria":"externo","descricao":"A Argentina declara a maior moratória soberana até então e abandona a conversibilidade do peso semanas depois.","series":["embi","usd_brl","ibovespa"]},
{"data":"2002-06-22","titulo":"Carta ao Povo Brasileiro","categoria":"politica","descricao":"Lula, líder nas pesquisas, promete respeitar contratos. Mesmo assim o risco-país passa de 2.000 pontos e o dólar chega a R$ 3,99 em outubro.","series":["embi","usd_brl","ibovespa","selic_meta"]},
{"data":"2002-10-27","titulo":"Lula eleito presidente","categoria":"politica","descricao":"Vitória no segundo turno. O Copom sobe a Selic para 25% em novembro e o risco-país recua ao longo de 2003 com Palocci na Fazenda e Meirelles no BC.","series":["embi","usd_brl","selic_meta","ibovespa"]},
{"data":"2005-12-13","titulo":"Brasil quita a dívida com o FMI","categoria":"fiscal","descricao":"Pagamento antecipado de US$ 15,5 bilhões, dois anos antes do prazo, sinaliza folga externa.","series":["embi","usd_brl"]},
{"data":"2007-08-09","titulo":"Início da crise do subprime","categoria":"externo","descricao":"O BNP Paribas congela três fundos lastreados em hipotecas americanas e o mercado interbancário trava. O Fed começa a cortar juros em setembro.","series":["sp500","vix","fed_funds"]},
{"data":"2008-04-30","titulo":"Brasil recebe grau de investimento","categoria":"fiscal","descricao":"A S&P eleva o país a BBB-. O dólar cai a R$ 1,56 em agosto e o Ibovespa bate 73 mil pontos em maio.","series":["usd_brl","ibovespa","embi"]},
{"data":"2008-09-15","titulo":"Quebra do Lehman Brothers","categoria":"crise","descricao":"Fase aguda da crise financeira global. O dólar salta de R$ 1,60 para R$ 2,40 em dez semanas, o VIX chega a 80 e o BC vende reservas para conter o câmbio.","series":["usd_brl","ibovespa","sp500","embi","vix","petroleo"]},
{"data":"2008-12-16","titulo":"Fed zera os juros","categoria":"fomc","descricao":"O Fed Funds cai para 0–0,25% e começa a compra de ativos em larga escala (QE1). O juro zero dura sete anos.","series":["fed_funds","treasury_10y","sp500","dxy"]},
{"data":"2009-03-09","titulo":"Fundo da bolsa americana","categoria":"externo","descricao":"O S&P 500 fecha em 676 pontos e inicia o mais longo mercado de alta da história.","series":["sp500","ibovespa","vix"]},
{"data":"2010-05-02","titulo":"Resgate da Grécia","categoria":"externo","descricao":"Primeiro pacote da crise da dívida europeia. O contágio alcança Portugal, Irlanda, Espanha e Itália nos dois anos seguintes.","series":["sp500","vix","eur_brl"]},
{"data":"2010-11-03","titulo":"QE2","categoria":"fomc","descricao":"O Fed anuncia mais US$ 600 bilhões em compras de Treasuries. O dólar enfraquece e o real valoriza até R$ 1,55 em 2011.","series":["fed_funds","treasury_10y","usd_brl","dxy"]},
{"data":"2011-08-05","titulo":"S&P rebaixa os Estados Unidos","categoria":"externo","descricao":"Perda do AAA americano. Semanas depois o Copom surpreende cortando a Selic de 12,5% para 12%, o início de um ciclo que a levaria a 7,25%.","series":["sp500","vix","treasury_10y","selic_meta"]},
{"data":"2012-07-26","titulo":"\"Whatever it takes\" de Draghi","categoria":"externo","descricao":"O BCE promete fazer o que for preciso para salvar o euro. Fim da fase aguda da crise europeia.","series":["eur_brl","vix","sp500"]},
{"data":"2013-05-22","titulo":"Taper tantrum","categoria":"fomc","descricao":"Bernanke sinaliza redução das compras de ativos. O Treasury de 10 anos sobe de 1,6% para 3% e o dólar no Brasil vai de R$ 2,00 para R$ 2,40.","series":["treasury_10y","usd_brl","embi","ibovespa"]},
{"data":"2013-06-17","titulo":"Protestos de junho","categoria":"politica","descricao":"Manifestações em massa em todo o país. A popularidade do governo despenca e a agenda fiscal trava.","series":["ibovespa","usd_brl"]},
{"data":"2014-10-26","titulo":"Reeleição de Dilma","categoria":"politica","descricao":"Vitória apertada. Três dias depois o Copom sobe a Selic de surpresa e em novembro Joaquim Levy é anunciado para a Fazenda.","series":["usd_brl","ibovespa","selic_meta","embi"]},
{"data":"2014-11-27","titulo":"OPEP mantém produção e o petróleo desaba","categoria":"externo","descricao":"O WTI cai de US$ 100 para US$ 45 em seis meses, pressionando a Petrobras, o câmbio e as contas externas.","series":["petroleo","ibovespa","usd_brl"]},
{"data":"2015-08-11","titulo":"China desvaloriza o yuan","categoria":"externo","descricao":"Choque em commodities e moedas emergentes. O dólar passa de R$ 3,50 e o Ibovespa cai abaixo de 45 mil pontos.","series":["usd_brl","ibovespa","petroleo","vix"]},
{"data":"2015-09-09","titulo":"Brasil perde o grau de investimento","categoria":"fiscal","descricao":"A S&P rebaixa o país para BB+ após a revisão da meta fiscal para déficit. O dólar bate R$ 4,19 em 24/09.","series":["usd_brl","embi","ibovespa","selic_meta"]},
{"data":"2015-12-16","titulo":"Fed faz a primeira alta desde 2006","categoria":"fomc","descricao":"Início da normalização: o Fed Funds sai de zero pela primeira vez em sete anos.","series":["fed_funds","treasury_2y","dxy"]},
{"data":"2016-04-17","titulo":"Câmara aprova o impeachment de Dilma","categoria":"politica","descricao":"Temer assume interinamente em 12/05 e nomeia Meirelles para a Fazenda. O Ibovespa sobe cerca de 40% no ano.","series":["ibovespa","usd_brl","embi"]},
{"data":"2016-06-23","titulo":"Brexit","categoria":"externo","descricao":"O Reino Unido vota pela saída da União Europeia. A libra despenca e o VIX dispara por alguns dias.","series":["vix","sp500","eur_brl"]},
{"data":"2016-11-08","titulo":"Trump eleito","categoria":"externo","descricao":"Treasuries e dólar sobem com expectativa de estímulo fiscal e inflação; moedas emergentes sofrem.","series":["treasury_10y","dxy","usd_brl"]},
{"data":"2016-12-15","titulo":"Teto de gastos (EC 95)","categoria":"fiscal","descricao":"A emenda congela o gasto primário real por 20 anos e abre espaço para o ciclo de cortes da Selic de 14,25% para 6,5%.","series":["selic_meta","embi","divida_pib"]},
{"data":"2017-05-17","titulo":"Joesley Day","categoria":"politica","descricao":"A delação da JBS atinge Temer. No dia seguinte o Ibovespa cai 8,8% com circuit breaker e o dólar sobe 8%.","series":["ibovespa","usd_brl","embi"]},
{"data":"2018-02-05","titulo":"\"Volmageddon\"","categoria":"externo","descricao":"O VIX dobra em um único pregão e fundos vendidos em volatilidade quebram.","series":["vix","sp500"]},
{"data":"2018-05-21","titulo":"Greve dos caminhoneiros","categoria":"crise","descricao":"Dez dias de paralisação com desabastecimento. O IPCA de junho sobe 1,26% e o PIB do ano é revisado para baixo.","series":["ipca","usd_brl","ibovespa"]},
{"data":"2018-10-28","titulo":"Bolsonaro eleito","categoria":"politica","descricao":"O Ibovespa renova máximas com a expectativa da reforma da Previdência e o dólar recua de R$ 4,20 para R$ 3,70.","series":["ibovespa","usd_brl","embi"]},
{"data":"2019-07-31","titulo":"Fed inicia cortes preventivos","categoria":"fomc","descricao":"Primeiro corte desde 2008. No mesmo dia o Copom reduz a Selic para 6%.","series":["fed_funds","treasury_10y","selic_meta"]},
{"data":"2019-11-12","titulo":"Reforma da Previdência promulgada","categoria":"fiscal","descricao":"Economia estimada de R$ 800 bilhões em dez anos. A Selic chega a 4,5% em dezembro.","series":["embi","divida_pib","ibovespa","selic_meta"]},
{"data":"2020-03-11","titulo":"OMS declara pandemia de Covid-19","categoria":"crise","descricao":"Circuit breakers seguidos na B3. O Ibovespa cai de 119 mil para 63 mil pontos em um mês, o dólar passa de R$ 5,00 e o VIX bate 82.","series":["ibovespa","sp500","usd_brl","vix","petroleo","embi"]},
{"data":"2020-03-15","titulo":"Fed zera juros e lança QE ilimitado","categoria":"fomc","descricao":"Corte emergencial de 100 pontos para 0–0,25% e compras de ativos sem limite. Dias depois o Copom corta a Selic para 3,75%.","series":["fed_funds","treasury_10y","sp500","dxy"]},
{"data":"2020-04-20","titulo":"Petróleo WTI fecha negativo","categoria":"externo","descricao":"O contrato de maio encerra a −US$ 37 por falta de espaço para estocar. Único preço negativo da história da série.","series":["petroleo"]},
{"data":"2020-08-05","titulo":"Selic em 2%, mínima histórica","categoria":"copom","descricao":"Último corte do ciclo da pandemia. A taxa fica em 2% até março de 2021, com juro real negativo.","series":["selic_meta","cdi","juro_real","usd_brl"]},
{"data":"2020-11-09","titulo":"Anúncio da vacina da Pfizer","categoria":"externo","descricao":"Eficácia de 90% dispara a rotação para ativos cíclicos e emergentes. O Ibovespa sobe 15% em novembro.","series":["sp500","ibovespa","usd_brl","vix"]},
{"data":"2021-10-21","titulo":"Furo do teto de gastos","categoria":"fiscal","descricao":"O governo anuncia o Auxílio Brasil fora do teto. Juros futuros disparam, o dólar vai a R$ 5,70 e o Copom acelera a alta para 150 pontos.","series":["usd_brl","selic_meta","ibovespa","embi"]},
{"data":"2022-02-24","titulo":"Invasão da Ucrânia","categoria":"externo","descricao":"O petróleo passa de US$ 120 e há choque em alimentos e energia. A inflação global acelera e os bancos centrais apertam mais.","series":["petroleo","ipca","cpi_eua","vix","ouro"]},
{"data":"2022-03-16","titulo":"Fed inicia o ciclo de alta","categoria":"fomc","descricao":"Primeira alta desde 2018. Em 16 meses o Fed Funds sobe de zero para 5,25%, o aperto mais rápido desde 1981.","series":["fed_funds","treasury_2y","dxy","sp500"]},
{"data":"2022-06-10","titulo":"Inflação americana em 8,6%","categoria":"externo","descricao":"Maior CPI desde 1981. O Fed responde com alta de 75 pontos, a primeira desse tamanho desde 1994.","series":["cpi_eua","fed_funds","treasury_2y","sp500"]},
{"data":"2022-10-30","titulo":"Lula eleito para o terceiro mandato","categoria":"politica","descricao":"Segundo turno apertado. Em dezembro a PEC da Transição amplia gastos em cerca de R$ 145 bilhões e o mercado precifica risco fiscal.","series":["usd_brl","ibovespa","embi","selic_meta"]},
{"data":"2023-01-08","titulo":"Ataques aos Três Poderes","categoria":"politica","descricao":"Invasão das sedes dos Poderes em Brasília. Os mercados reagem com cautela e recuperam-se na semana seguinte.","series":["ibovespa","usd_brl"]},
{"data":"2023-03-10","titulo":"Quebra do Silicon Valley Bank","categoria":"externo","descricao":"Maior falência bancária desde 2008. O Fed cria linha emergencial e o Credit Suisse é absorvido pelo UBS dias depois.","series":["vix","treasury_2y","sp500","fed_funds"]},
{"data":"2023-08-30","titulo":"Novo arcabouço fiscal sancionado","categoria":"fiscal","descricao":"Substitui o teto de gastos por uma regra de crescimento real da despesa limitado a 70% do crescimento da receita.","series":["divida_pib","embi","selic_meta"]},
{"data":"2024-05-08","titulo":"Copom racha e corta 25 pontos","categoria":"copom","descricao":"Decisão dividida por 5 a 4 entre diretores indicados por governos diferentes; Selic a 10,5%. O ruído sobre a autonomia do BC pressiona o câmbio.","series":["selic_meta","usd_brl","embi"]},
{"data":"2024-09-18","titulo":"Fed inicia cortes com 50 pontos","categoria":"fomc","descricao":"Primeiro corte desde 2020. No mesmo dia o Copom volta a subir a Selic, para 10,75%, na direção oposta.","series":["fed_funds","selic_meta","dxy","treasury_2y"]},
{"data":"2024-11-28","titulo":"Pacote fiscal decepciona e dólar bate R$ 6","categoria":"fiscal","descricao":"O anúncio de corte de gastos vem junto com isenção de IR. O dólar chega a R$ 6,27 em 18/12 e o Copom sobe 100 pontos com indicação de mais duas altas iguais.","series":["usd_brl","selic_meta","ibovespa","embi"]},
{"data":"2025-01-20","titulo":"Posse de Trump","categoria":"externo","descricao":"A agenda tarifária e fiscal eleva a incerteza global. O dólar, que abriu o ano em máximas, recua ao longo do semestre.","series":["dxy","usd_brl","treasury_10y","ouro"]},
{"data":"2025-04-02","titulo":"\"Dia da Libertação\": tarifaço dos EUA","categoria":"externo","descricao":"Tarifas recíprocas contra quase todos os países. O S&P 500 cai 12% em quatro pregões, o VIX passa de 50 e parte das tarifas é suspensa em 9/04.","series":["sp500","vix","dxy","petroleo","ibovespa"]},
{"data":"2025-06-18","titulo":"Selic chega a 15%, maior desde 2006","categoria":"copom","descricao":"O Copom encerra o ciclo de alta iniciado em setembro de 2024 e sinaliza pausa prolongada.","series":["selic_meta","cdi","juro_real","usd_brl"]},
{"data":"2025-07-09","titulo":"Trump anuncia tarifa de 50% sobre o Brasil","categoria":"externo","descricao":"Anúncio com motivação política. O dólar sobe a R$ 5,60 e a tarifa entra em vigor em 6/08 com uma longa lista de exceções.","series":["usd_brl","ibovespa","embi"]},
{"data":"2025-09-17","titulo":"Fed retoma os cortes","categoria":"fomc","descricao":"Primeiro corte de 2025, para 4,00–4,25%, com o mercado de trabalho americano enfraquecendo.","series":["fed_funds","treasury_2y","dxy","usd_brl"]}
]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_eventos.py -q`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add eventos.json tests/test_eventos.py
git commit -m "feat: base curada de eventos macro (1986–2025)"
```

---

### Task 9: Orquestrador `atualizar.py` e primeira geração real

**Files:**
- Create: `atualizar.py`, `tests/test_atualizar.py`

**Interfaces:**
- Consumes: tudo de `pipeline/`.
- Produces: `main(argv=None) -> int`; `dados.json`, `dados.js`, `cache/*.csv` na pasta de saída.

- [ ] **Step 1: Escrever o teste de integração (sem rede)**

`tests/test_atualizar.py`:
```python
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

import atualizar
from pipeline import cache as cache_mod
from pipeline.series import SERIES

RAIZ = Path(__file__).parent.parent


def serie_fake(serie):
    if serie.freq == "d":
        idx = pd.bdate_range("2018-01-01", periods=1600, name="data")
    else:
        idx = pd.date_range("2018-01-01", periods=80, freq="MS", name="data")
    rng = np.random.default_rng(sum(map(ord, serie.id)))  # semente determinística por série
    base = 100 + np.cumsum(rng.normal(size=len(idx)))
    return pd.Series(base, index=idx)


def test_main_gera_arquivos(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod.fontes, "baixar", serie_fake)
    shutil.copy(RAIZ / "eventos.json", tmp_path / "eventos.json")
    assert atualizar.main(["--pasta", str(tmp_path)]) == 0
    d = json.loads((tmp_path / "dados.json").read_text(encoding="utf-8"))
    assert len(d["series"]) >= len(SERIES)          # baixadas + derivadas
    assert "ipca_12m" in d["series"] and "juro_real" in d["series"]
    assert any(e.get("auto") for e in d["eventos"])  # ciclos da Selic detectados
    assert (tmp_path / "dados.js").exists() and (tmp_path / "cache" / "selic_meta.csv").exists()


def test_offline_usa_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod.fontes, "baixar", serie_fake)
    shutil.copy(RAIZ / "eventos.json", tmp_path / "eventos.json")
    atualizar.main(["--pasta", str(tmp_path)])
    monkeypatch.setattr(cache_mod.fontes, "baixar", lambda s: 1 / 0)
    assert atualizar.main(["--pasta", str(tmp_path), "--offline"]) == 0
```

Observação: `obter` recebe `baixar` como parâmetro com default `fontes.baixar` avaliado na importação; por isso `atualizar.py` deve chamar `obter(serie, cache, offline=..., baixar=fontes.baixar)` explicitamente, lendo o atributo no momento da chamada, para que o monkeypatch funcione.

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_atualizar.py -q`
Expected: `ModuleNotFoundError: No module named 'atualizar'`.

- [ ] **Step 3: Escrever `atualizar.py`**

```python
"""Baixa as séries, recalcula correlações e grava dados.json / dados.js.

Uso:
    python atualizar.py            # baixa tudo (usa cache se alguma fonte falhar)
    python atualizar.py --offline  # recalcula só a partir do cache
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline import correlacao, exportar, fontes, transformar
from pipeline.cache import Cache, obter
from pipeline.ciclos import ciclos_copom
from pipeline.series import DERIVADAS, POR_ID, SERIES

RAIZ = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Atualiza os dados do painel de taxas.")
    ap.add_argument("--offline", action="store_true", help="recalcula só a partir do cache, sem rede")
    ap.add_argument("--pasta", default=str(RAIZ), help="pasta de saída (padrão: pasta do script)")
    args = ap.parse_args(argv)
    pasta = Path(args.pasta)
    cache = Cache(pasta / "cache")

    brutas, status, avisos = {}, {}, []
    for serie in SERIES:
        s, st, aviso = obter(serie, cache, offline=args.offline, baixar=fontes.baixar)
        status[serie.id] = st
        if aviso:
            avisos.append(aviso)
        if s is not None and not s.empty:
            brutas[serie.id] = s
            periodo = f"{s.index.min():%Y-%m-%d} -> {s.index.max():%Y-%m-%d} ({len(s)} pts)"
        else:
            periodo = "-"
        print(f"[{st:13}] {serie.nome:34} {periodo}")

    diarias = {id: transformar.para_diaria(s) for id, s in brutas.items() if POR_ID[id].freq == "d"}
    mensais = {id: transformar.para_mensal(s, POR_ID[id].freq) for id, s in brutas.items()}
    for id, s in transformar.derivadas(mensais).items():
        mensais[id] = s
        status[id] = "ok"
    transformadas = {id: transformar.transformar(m, POR_ID[id].transformacao)
                     for id, m in mensais.items() if not m.empty}
    correl = correlacao.calcular(transformadas)

    arq_eventos = pasta / "eventos.json"
    eventos = json.loads(arq_eventos.read_text(encoding="utf-8")) if arq_eventos.exists() else []
    if "selic_meta" in brutas:
        eventos = eventos + ciclos_copom(brutas["selic_meta"])

    metas = {s.id: s for s in SERIES + DERIVADAS}
    dados = exportar.montar(metas, diarias, mensais, status, avisos, correl, eventos)
    exportar.gravar(dados, pasta)

    n_arestas = sum(len(a) for a in dados["arestas"].values())
    print(f"\n{len(dados['series'])} séries, {len(dados['eventos'])} eventos, {n_arestas} arestas. "
          f"Avisos: {len(avisos)}")
    for a in avisos:
        print("  !", a)
    print(f"Gravado em {pasta / 'dados.json'}")
    return 0 if any(st == "ok" for st in status.values()) else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
```

- [ ] **Step 4: Rodar os testes**

Run: `python -m pytest -q`
Expected: todos os testes passam (`44 passed` aproximadamente).

- [ ] **Step 5: Gerar os dados reais**

Run: `python atualizar.py`
Expected: 24 linhas `[ok           ] ...` (ou `desatualizada`/`ausente` com aviso explicado), resumo final com ~29 séries, ~110 eventos (70 curados + ~40 automáticos), centenas de arestas, e `dados.json` na pasta. Confira o tamanho: `python -c "import os; print(os.path.getsize('dados.json')/1e6, 'MB')"` deve ficar abaixo de 16 MB (esperado: 3 a 6 MB).

Se alguma fonte falhar sem cache, o status é `ausente` e a série simplesmente não aparece; anote o aviso e siga.

- [ ] **Step 6: Commit**

```bash
git add atualizar.py tests/test_atualizar.py
git commit -m "feat: orquestrador atualizar.py com resumo e modo offline"
```

---

### Task 10: Painel — estrutura, tema, carregamento e KPIs

**Files:**
- Create: `painel.html`, `painel.css`, `painel.js`

**Interfaces:**
- Consumes: `dados.json` / `dados.js` no formato da spec §4.
- Produces: em `painel.js`, o estado global `estado`, utilitários (`el`, `fmt`, `fmtSinal`, `fmtData`, `cssVar`, `corGrupo`, `corSlot`, `pontos`, `valorEm`, `impacto`, `unidadeVar`, `casasDe`, `classeVar`), base ECharts (`grafico`, `textoBase`, `eixoBase`, `tooltipBase`), `renderKpis`, `ativarAba`, `renderAba` com um mapa `RENDER` onde as Tasks 11–14 registram `renderSeries`, `renderCerebro`, `renderHeat`, `renderTimeline`. Nesta task, as quatro funções existem como stubs que escrevem "em construção" no container.

- [ ] **Step 1: Escrever `painel.html`**

```html
<!DOCTYPE html>
<html lang="pt-BR" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Painel de Taxas</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="painel.css">
</head>
<body>
<header class="topo">
  <div class="topo-titulo">
    <h1>Painel de Taxas</h1>
    <span id="atualizado" class="muted"></span>
  </div>
  <div class="topo-acoes">
    <button id="btn-avisos" class="chip chip-aviso" type="button" hidden>⚠ <span id="n-avisos"></span> avisos</button>
    <button id="btn-tema" class="btn" type="button" aria-label="Alternar tema"></button>
  </div>
</header>
<div id="avisos" class="avisos" hidden></div>
<div id="erro" class="erro" role="alert" hidden></div>

<section id="kpis" class="kpis" aria-label="Indicadores principais"></section>

<nav class="abas" role="tablist" aria-label="Seções do painel">
  <button role="tab" type="button" data-aba="series" aria-selected="true">Séries</button>
  <button role="tab" type="button" data-aba="cerebro" aria-selected="false">Cérebro</button>
  <button role="tab" type="button" data-aba="correlacoes" aria-selected="false">Correlações</button>
  <button role="tab" type="button" data-aba="timeline" aria-selected="false">Linha do tempo</button>
</nav>

<main>
  <section id="aba-series" class="aba ativa" role="tabpanel">
    <div class="controles">
      <details class="seletor">
        <summary id="sel-resumo">Séries</summary>
        <div id="sel-lista" class="sel-lista"></div>
      </details>
      <div class="segmentos" role="group" aria-label="Período">
        <button type="button" class="seg" data-periodo="1a">1a</button>
        <button type="button" class="seg" data-periodo="5a">5a</button>
        <button type="button" class="seg" data-periodo="10a" aria-pressed="true">10a</button>
        <button type="button" class="seg" data-periodo="20a">20a</button>
        <button type="button" class="seg" data-periodo="tudo">Tudo</button>
      </div>
      <div class="segmentos" role="group" aria-label="Modo">
        <button type="button" class="seg" data-modo="base100" aria-pressed="true">Base 100</button>
        <button type="button" class="seg" data-modo="nivel" id="modo-nivel">Nível</button>
      </div>
      <span id="aviso-modo" class="hint" hidden>Unidades diferentes: só Base 100</span>
      <div id="chips-cat" class="chips" aria-label="Categorias de eventos"></div>
    </div>
    <div class="card">
      <div id="chart-series" class="chart" style="height:560px"></div>
      <p class="legenda-faixa muted">Faixa inferior: eventos por categoria. Passe o mouse para ler, clique para ver o impacto em 30 e 90 dias.</p>
    </div>
    <div id="evento-detalhe" class="card evento-detalhe" hidden></div>
  </section>

  <section id="aba-cerebro" class="aba" role="tabpanel" hidden>
    <div class="controles">
      <div class="segmentos" role="group" aria-label="Janela" data-janela-grupo="cerebro"></div>
      <label class="slider">|r| mínimo <input id="corte" type="range" min="0.15" max="0.9" step="0.05" value="0.3"> <output id="corte-valor">0,30</output></label>
      <div id="chips-grupo" class="chips" aria-label="Grupos"></div>
      <span id="n-arestas" class="hint"></span>
    </div>
    <div class="cerebro-grade">
      <div class="card"><div id="chart-cerebro" class="chart" style="height:640px"></div>
        <p class="legenda-faixa muted">Nó maior = mais conectado. Aresta azul = correlação positiva, vermelha = negativa; espessura = força. Arraste para reorganizar, role para dar zoom, clique num nó para ver a lista.</p></div>
      <aside id="painel-no" class="card painel-no"></aside>
    </div>
  </section>

  <section id="aba-correlacoes" class="aba" role="tabpanel" hidden>
    <div class="controles">
      <div class="segmentos" role="group" aria-label="Janela" data-janela-grupo="heat"></div>
      <span class="hint">Célula vazia: menos de 24 meses em comum.</span>
    </div>
    <div class="card"><div id="chart-heat" class="chart" style="height:900px"></div></div>
  </section>

  <section id="aba-timeline" class="aba" role="tabpanel" hidden>
    <div class="controles">
      <input id="busca" class="busca" type="search" placeholder="Buscar evento…" aria-label="Buscar evento">
      <div id="chips-timeline" class="chips" aria-label="Categorias"></div>
      <span id="n-eventos" class="hint"></span>
    </div>
    <div id="lista-eventos" class="lista-eventos"></div>
  </section>
</main>

<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js" integrity="sha384-Mx5lkUEQPM1pOJCwFtUICyX45KNojXbkWdYhkKUKsbv391mavbfoAmONbzkgYPzR" crossorigin="anonymous"></script>
<script src="dados.js"></script>
<script src="painel.js"></script>
</body>
</html>
```

- [ ] **Step 2: Escrever `painel.css`**

```css
:root {
  color-scheme: light;
  --bg: #f4f5f8; --card: #ffffff; --text: #0b0b0b; --text-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,.10); --border-solid: #e1e0d9;
  --g-juros: #2a78d6; --g-inflacao: #eb6834; --g-cambio: #1baf7a; --g-bolsa: #eda100; --g-macro: #e87ba4; --g-exterior: #008300;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100; --s5: #e87ba4; --s6: #008300; --s7: #4a3aa7; --s8: #e34948;
  --pos: #2a78d6; --neg: #e34948; --mid: #f0efec;
  --c-copom: #2a78d6; --c-fomc: #4a3aa7; --c-crise: #e34948; --c-politica: #e87ba4; --c-fiscal: #eda100; --c-externo: #1baf7a; --c-plano: #eb6834;
  --sombra: 0 1px 2px rgba(0,0,0,.06), 0 8px 24px rgba(0,0,0,.06);
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0f1117; --card: #1a1d27; --text: #e6e8ef; --text-2: #c3c2b7; --muted: #898781;
  --grid: #2c2f3a; --axis: #383b47; --border: rgba(255,255,255,.10); --border-solid: #2c2f3a;
  --g-juros: #3987e5; --g-inflacao: #d95926; --g-cambio: #199e70; --g-bolsa: #c98500; --g-macro: #d55181; --g-exterior: #008300;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --s6: #008300; --s7: #9085e9; --s8: #e66767;
  --pos: #3987e5; --neg: #e66767; --mid: #383835;
  --c-copom: #3987e5; --c-fomc: #9085e9; --c-crise: #e66767; --c-politica: #d55181; --c-fiscal: #c98500; --c-externo: #199e70; --c-plano: #d95926;
  --sombra: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
}

* { box-sizing: border-box; }
html, body { margin: 0; }
body { background: var(--bg); color: var(--text); font: 14px/1.45 Inter, system-ui, -apple-system, "Segoe UI", sans-serif; padding: 0 16px 48px; }
h1 { font-size: 20px; margin: 0; font-weight: 700; letter-spacing: -.01em; }
h3 { font-size: 15px; margin: 6px 0 4px; }
p { margin: 6px 0; }
.muted { color: var(--muted); }
.hint { color: var(--muted); font-size: 12px; align-self: center; }

.topo { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 18px 0 12px; flex-wrap: wrap; }
.topo-titulo { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
.topo-acoes { display: flex; gap: 8px; align-items: center; }
.btn, .chip, .seg { font: inherit; color: var(--text); background: var(--card); border: 1px solid var(--border-solid); border-radius: 999px; padding: 6px 12px; cursor: pointer; }
.btn:hover, .chip:hover, .seg:hover { border-color: var(--muted); }
.chip { font-size: 12px; padding: 4px 10px; display: inline-flex; align-items: center; gap: 6px; }
.chip .ponto { width: 9px; height: 9px; border-radius: 50%; background: var(--cor); display: inline-block; }
.chip[aria-pressed="false"] { opacity: .45; }
.chip-aviso { border-color: #fab219; }
.chip.cat { --cor: var(--muted); border-color: transparent; background: color-mix(in srgb, var(--cor) 18%, transparent); color: var(--text); }
.avisos { background: var(--card); border: 1px solid #fab219; border-radius: 10px; padding: 10px 14px; margin-bottom: 12px; font-size: 13px; }
.avisos div + div { margin-top: 4px; }
.erro { background: var(--card); border: 1px solid var(--neg); border-radius: 10px; padding: 14px; margin: 12px 0; }

.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 16px; }
.kpi { background: var(--card); border-radius: 12px; padding: 12px 14px 8px; box-shadow: var(--sombra); border-top: 3px solid var(--cor); }
.kpi-nome { font-size: 12px; color: var(--text-2); }
.kpi-valor { font-size: 24px; font-weight: 600; line-height: 1.2; margin-top: 2px; }
.kpi-unid { font-size: 12px; font-weight: 400; color: var(--muted); }
.kpi-vars { display: flex; gap: 10px; font-size: 12px; margin-top: 4px; font-variant-numeric: tabular-nums; }
.kpi-spark { height: 38px; margin-top: 6px; }
.kpi-data { font-size: 11px; }
.var-pos { color: var(--pos); } .var-neg { color: var(--neg); }

.abas { display: flex; gap: 4px; border-bottom: 1px solid var(--border-solid); margin-bottom: 14px; overflow-x: auto; }
.abas [role="tab"] { font: inherit; font-weight: 500; color: var(--text-2); background: none; border: 0; border-bottom: 2px solid transparent; padding: 10px 14px; cursor: pointer; white-space: nowrap; }
.abas [role="tab"][aria-selected="true"] { color: var(--text); border-bottom-color: var(--text); }
.aba[hidden] { display: none; }

.controles { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 12px; }
.segmentos { display: inline-flex; background: var(--card); border: 1px solid var(--border-solid); border-radius: 999px; padding: 2px; }
.segmentos .seg { border: 0; background: none; padding: 5px 12px; font-size: 13px; color: var(--text-2); }
.segmentos .seg[aria-pressed="true"] { background: var(--text); color: var(--card); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.slider { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-2); }
.slider input { width: 140px; accent-color: var(--pos); }
.busca { font: inherit; color: var(--text); background: var(--card); border: 1px solid var(--border-solid); border-radius: 999px; padding: 6px 14px; min-width: 240px; }

.seletor { position: relative; }
.seletor summary { list-style: none; cursor: pointer; font: inherit; color: var(--text); background: var(--card); border: 1px solid var(--border-solid); border-radius: 999px; padding: 6px 14px; }
.seletor summary::-webkit-details-marker { display: none; }
.sel-lista { position: absolute; z-index: 20; top: calc(100% + 6px); left: 0; background: var(--card); border: 1px solid var(--border-solid); border-radius: 12px; box-shadow: var(--sombra); padding: 10px 14px; display: grid; grid-template-columns: repeat(2, minmax(200px, 1fr)); gap: 4px 20px; max-height: 60vh; overflow: auto; min-width: 460px; }
.sel-grupo { grid-column: 1 / -1; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-top: 8px; }
.sel-lista label { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 2px 0; cursor: pointer; }
.sel-lista .ponto { width: 8px; height: 8px; border-radius: 50%; background: var(--cor); flex: none; }

.card { background: var(--card); border-radius: 12px; padding: 12px; box-shadow: var(--sombra); margin-bottom: 12px; }
.chart { width: 100%; }
.legenda-faixa { font-size: 12px; margin: 6px 4px 0; }

.cerebro-grade { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 12px; }
.painel-no { max-height: 700px; overflow: auto; }
.painel-no h3 { margin-top: 0; }
.corr-linha { display: grid; grid-template-columns: 1fr 64px; gap: 8px; align-items: center; font-size: 12px; padding: 4px 0; border-bottom: 1px solid var(--border); }
.corr-nome { display: flex; align-items: center; gap: 6px; min-width: 0; }
.corr-nome span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.corr-barra { height: 6px; border-radius: 3px; background: var(--grid); position: relative; }
.corr-barra i { position: absolute; top: 0; bottom: 0; border-radius: 3px; }
.corr-valor { font-variant-numeric: tabular-nums; text-align: right; }

.evento-detalhe h3 { margin-top: 0; }
.evento-cab { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 12px; color: var(--muted); }
.lista-eventos { display: grid; gap: 10px; }
.evento { background: var(--card); border-radius: 12px; padding: 12px 14px; box-shadow: var(--sombra); }
.impactos { border-collapse: collapse; font-size: 12px; margin-top: 8px; font-variant-numeric: tabular-nums; }
.impactos th, .impactos td { text-align: left; padding: 3px 12px 3px 0; border-bottom: 1px solid var(--border); }
.impactos th { color: var(--muted); font-weight: 500; }

.tt { max-width: 340px; }
.tt-titulo { font-weight: 600; margin-bottom: 4px; }
.tt-linha { display: flex; align-items: center; gap: 8px; padding: 1px 0; }
.tt-chave { width: 14px; height: 2px; border-radius: 1px; flex: none; }
.tt-nome { color: var(--muted); }
.tt-desc { color: var(--text-2); white-space: normal; margin-top: 2px; }

@media (max-width: 900px) {
  .cerebro-grade { grid-template-columns: 1fr; }
  .sel-lista { grid-template-columns: 1fr; min-width: 280px; }
}
```

- [ ] **Step 3: Escrever `painel.js` (base + KPIs + stubs das abas)**

```js
/* Painel de Taxas — sem build. ECharts via CDN; dados em dados.json (http) ou dados.js (file://). */
(function () {
  'use strict';

  // ---------- constantes ----------
  const GRUPOS = { juros: 'Juros Brasil', inflacao: 'Inflação Brasil', cambio: 'Câmbio', bolsa: 'Bolsa e commodities', macro: 'Macro Brasil', exterior: 'Exterior' };
  const ORDEM_GRUPOS = Object.keys(GRUPOS);
  const CATEGORIAS = { copom: 'Copom', fomc: 'Fed', crise: 'Crise', politica: 'Política', fiscal: 'Fiscal', externo: 'Externo', plano: 'Plano econômico' };
  const ORDEM_CAT = Object.keys(CATEGORIAS);
  const KPI_IDS = ['selic_meta', 'cdi', 'ipca_12m', 'usd_brl', 'fed_funds', 'ibovespa'];
  const JANELAS = { tudo: 'Tudo', '10a': '10 anos', '5a': '5 anos', '3a': '3 anos' };
  const PERIODOS = { '1a': 1, '5a': 5, '10a': 10, '20a': 20, tudo: null };
  const MAX_SERIES = 8;

  let D = null;
  const charts = {};
  const estado = {
    aba: 'series',
    selecionadas: ['selic_meta', 'ipca_12m', 'usd_brl'],
    modo: 'base100',
    periodo: '10a',
    categorias: new Set(ORDEM_CAT),
    janela: 'tudo',
    corte: 0.3,
    gruposCerebro: new Set(ORDEM_GRUPOS),
    noSelecionado: null,
    janelaHeat: 'tudo',
    filtroCat: new Set(ORDEM_CAT),
    busca: '',
  };
  const RENDER = {};

  // ---------- utilidades ----------
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => Array.from(raiz.querySelectorAll(sel));
  const cssVar = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  const corGrupo = (g) => cssVar('--g-' + g) || '#888888';
  const corSlot = (i) => cssVar('--s' + ((i % MAX_SERIES) + 1));
  const corCat = (c) => cssVar('--c-' + c) || cssVar('--muted');

  function el(tag, attrs = {}, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === false || v == null) continue;
      if (k === 'class') e.className = v;
      else if (k === 'text') e.textContent = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const f of filhos) if (f != null) e.append(f);
    return e;
  }
  const fmt = (v, casas = 2) => (v == null || Number.isNaN(v)) ? '—' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  const fmtSinal = (v, casas = 2) => v == null ? '—' : (v > 0 ? '+' : '') + fmt(v, casas);
  const fmtData = (iso) => { if (!iso) return '—'; const [a, m, d] = iso.split('-'); return d ? `${d}/${m}/${a}` : `${m}/${a}`; };
  const casasDe = (id) => { const u = (D.series[id] && D.series[id].unidade) || ''; return /pontos|índice/.test(u) ? 0 : (u === 'R$' ? 3 : 2); };
  const unidadeVar = (id) => D.series[id].var_tipo === 'pct' ? '%' : ' p.p.';
  const classeVar = (v) => v == null ? 'muted' : (v > 0 ? 'var-pos' : v < 0 ? 'var-neg' : '');
  const fmtVar = (id, v) => v == null ? '—' : fmtSinal(v) + unidadeVar(id);
  const addDias = (iso, dias) => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + dias); return d.toISOString().slice(0, 10); };
  const anosAtras = (iso, anos) => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCFullYear(d.getUTCFullYear() - anos); return d.toISOString().slice(0, 10); };

  function pontos(id) {
    const s = D.series[id];
    if (!s) return [];
    return s.diario.length ? s.diario : s.mensal.map(([m, v]) => [m + '-01', v]);
  }
  function valorEm(id, iso) {
    const arr = pontos(id);
    let lo = 0, hi = arr.length - 1, res = null;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (arr[mid][0] <= iso) { res = arr[mid][1]; lo = mid + 1; } else hi = mid - 1;
    }
    return res;
  }
  function impacto(id, iso, dias) {
    const s = D.series[id];
    const arr = pontos(id);
    if (!s || !arr.length) return null;
    const fim = addDias(iso, dias);
    if (iso < arr[0][0] || fim > arr[arr.length - 1][0]) return null;
    const v0 = valorEm(id, iso), v1 = valorEm(id, fim);
    if (v0 == null || v1 == null) return null;
    return s.var_tipo === 'pct' ? (v0 ? (v1 / v0 - 1) * 100 : null) : v1 - v0;
  }

  // ---------- base ECharts ----------
  function grafico(idEl) {
    const dom = document.getElementById(idEl);
    if (charts[idEl]) charts[idEl].dispose();
    charts[idEl] = echarts.init(dom, null, { renderer: 'canvas' });
    return charts[idEl];
  }
  const textoBase = () => ({ color: cssVar('--text-2'), fontFamily: 'Inter, system-ui, sans-serif' });
  const eixoBase = () => ({ axisLine: { lineStyle: { color: cssVar('--axis') } }, axisTick: { show: false }, axisLabel: { color: cssVar('--muted'), fontSize: 11 }, splitLine: { lineStyle: { color: cssVar('--grid') } } });
  const tooltipBase = () => ({ backgroundColor: cssVar('--card'), borderColor: cssVar('--border-solid'), borderWidth: 1, textStyle: { color: cssVar('--text'), fontSize: 12 }, extraCssText: 'box-shadow:0 8px 24px rgba(0,0,0,.25);border-radius:8px;' });

  // ---------- KPIs ----------
  function renderKpis() {
    const box = $('#kpis');
    box.replaceChildren();
    for (const id of KPI_IDS) {
      const s = D.series[id];
      if (!s) continue;
      box.append(el('article', { class: 'kpi', style: `--cor:${corGrupo(s.grupo)}` },
        el('div', { class: 'kpi-nome', text: s.nome }),
        el('div', { class: 'kpi-valor', text: fmt(s.ultimo, casasDe(id)) }, el('span', { class: 'kpi-unid', text: ' ' + s.unidade })),
        el('div', { class: 'kpi-vars' },
          el('span', { class: classeVar(s.var_1m), text: '1m ' + fmtVar(id, s.var_1m) }),
          el('span', { class: classeVar(s.var_12m), text: '12m ' + fmtVar(id, s.var_12m) })),
        el('div', { class: 'kpi-spark', id: 'spark-' + id }),
        el('div', { class: 'kpi-data muted', text: 'até ' + fmtData(s.fim) })));
      const dados = s.mensal.slice(-24).map((p) => p[1]);
      grafico('spark-' + id).setOption({
        animation: false,
        grid: { left: 0, right: 0, top: 4, bottom: 4 },
        xAxis: { type: 'category', show: false, data: dados.map((_, k) => k) },
        yAxis: { type: 'value', show: false, min: 'dataMin', max: 'dataMax' },
        series: [{ type: 'line', data: dados, showSymbol: false, lineStyle: { width: 1.5, color: corGrupo(s.grupo) }, areaStyle: { color: corGrupo(s.grupo), opacity: 0.12 } }],
      });
    }
  }

  // ---------- abas ----------
  function ativarAba(nome) {
    estado.aba = nome;
    $$('[role=tab]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.aba === nome)));
    $$('.aba').forEach((s) => { const ativa = s.id === 'aba-' + nome; s.hidden = !ativa; s.classList.toggle('ativa', ativa); });
    renderAba();
  }
  function renderAba() { if (RENDER[estado.aba]) RENDER[estado.aba](); }

  // stubs substituídos nas Tasks 11–14
  const emConstrucao = (idEl) => () => { const d = document.getElementById(idEl); if (d) d.textContent = 'em construção'; };
  RENDER.series = emConstrucao('chart-series');
  RENDER.cerebro = emConstrucao('chart-cerebro');
  RENDER.correlacoes = emConstrucao('chart-heat');
  RENDER.timeline = emConstrucao('lista-eventos');

  // ---------- tema ----------
  function aplicarTema(t) {
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('tema', t); } catch (e) { /* armazenamento indisponível */ }
    $('#btn-tema').textContent = t === 'dark' ? '☀ Claro' : '☾ Escuro';
    if (D) { renderKpis(); renderAba(); }
  }

  // ---------- carregamento ----------
  async function carregar() {
    if (/^https?:$/.test(location.protocol)) {
      try {
        const r = await fetch('dados.json', { cache: 'no-store' });
        if (r.ok) return await r.json();
      } catch (e) { /* cai no fallback */ }
    }
    if (window.DADOS) return window.DADOS;
    throw new Error('Não encontrei dados.json nem dados.js. Rode "python atualizar.py" nesta pasta e recarregue.');
  }
  function validar(d) {
    for (const k of ['series', 'correlacao', 'arestas', 'eventos']) {
      if (!d || typeof d[k] !== 'object' || d[k] === null) throw new Error(`dados.json inválido: falta a chave "${k}"`);
    }
  }

  function montarControlesBase() {
    $$('[role=tab]').forEach((b) => b.addEventListener('click', () => ativarAba(b.dataset.aba)));
    if (D.avisos && D.avisos.length) {
      const b = $('#btn-avisos'), box = $('#avisos');
      b.hidden = false;
      $('#n-avisos').textContent = D.avisos.length;
      box.replaceChildren(...D.avisos.map((a) => el('div', { text: a })));
      b.addEventListener('click', () => { box.hidden = !box.hidden; });
    }
    $('#atualizado').textContent = 'Atualizado em ' + fmtData(D.gerado_em.slice(0, 10)) + ' às ' + D.gerado_em.slice(11, 16);
  }

  async function init() {
    let tema = 'dark';
    try { tema = localStorage.getItem('tema') || 'dark'; } catch (e) { /* ok */ }
    aplicarTema(tema);
    $('#btn-tema').addEventListener('click', () => aplicarTema(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
    try { D = await carregar(); validar(D); } catch (e) { const box = $('#erro'); box.hidden = false; box.textContent = e.message; return; }
    montarControlesBase();
    if (typeof montarControles === 'function') montarControles();
    renderKpis();
    ativarAba('series');
    window.addEventListener('resize', () => Object.values(charts).forEach((c) => c.resize()));
  }

  // Ponto de extensão das Tasks 11–14: cada uma define funções aqui e registra em RENDER.
  let montarControles = null;
  // @@ABAS@@

  init();
})();
```

O marcador `// @@ABAS@@` é onde as Tasks 11–14 inserem seu código (antes de `init()`); a Task 11 também substitui `let montarControles = null;` por uma função real.

- [ ] **Step 4: Verificar sintaxe e abrir**

Run: `node --check painel.js && python -m http.server 8765`
Abra `http://localhost:8765/painel.html`. Expected: cabeçalho com data de atualização, 6 cartões KPI com valor, variações 1m/12m e sparkline, quatro abas com "em construção", botão de tema alternando claro/escuro e mantendo a escolha após recarregar. Abra também `painel.html` por duplo clique (file://): deve renderizar igual usando `dados.js`.

- [ ] **Step 5: Commit**

```bash
git add painel.html painel.css painel.js
git commit -m "feat(painel): estrutura, tema, carregamento e cartões KPI"
```

---

### Task 11: Painel — aba Séries (um eixo, Base 100/Nível, faixa de eventos)

**Files:**
- Modify: `painel.js` (substituir `let montarControles = null;` e inserir código no marcador `// @@ABAS@@`)

**Interfaces:**
- Consumes: utilitários e base da Task 10.
- Produces: `montarControles()` (constrói seletor de séries, períodos, modo, chips de categoria; registra listeners das abas seguintes via `montarControlesCerebro`, `montarControlesHeat`, `montarControlesTimeline` se existirem), `renderSeries()`, `tooltipSeries(params)`, `mostrarEvento(evento)`, helper `chips(container, opcoes, set, cor, aoMudar)`, helper `segmentosJanela(container, chave, aoMudar)`.

- [ ] **Step 1: Substituir `let montarControles = null;` por**

```js
  function chips(container, opcoes, conjunto, cor, aoMudar) {
    container.replaceChildren(...Object.entries(opcoes).map(([chave, rotulo]) => {
      const b = el('button', { type: 'button', class: 'chip', style: `--cor:${cor(chave)}`, 'aria-pressed': String(conjunto.has(chave)) }, el('span', { class: 'ponto' }), rotulo);
      b.addEventListener('click', () => {
        if (conjunto.has(chave)) conjunto.delete(chave); else conjunto.add(chave);
        b.setAttribute('aria-pressed', String(conjunto.has(chave)));
        aoMudar();
      });
      return b;
    }));
  }
  function segmentosJanela(container, chave, aoMudar) {
    container.replaceChildren(...Object.entries(JANELAS).map(([j, rotulo]) => {
      const b = el('button', { type: 'button', class: 'seg', 'aria-pressed': String(estado[chave] === j), text: rotulo });
      b.addEventListener('click', () => { estado[chave] = j; $$('.seg', container).forEach((x) => x.setAttribute('aria-pressed', String(x === b))); aoMudar(); });
      return b;
    }));
  }
  function montarControles() {
    // seletor de séries agrupado
    const lista = $('#sel-lista');
    for (const g of ORDEM_GRUPOS) {
      const ids = Object.keys(D.series).filter((id) => D.series[id].grupo === g);
      if (!ids.length) continue;
      lista.append(el('div', { class: 'sel-grupo', text: GRUPOS[g] }));
      for (const id of ids) {
        const cb = el('input', { type: 'checkbox', value: id });
        cb.checked = estado.selecionadas.includes(id);
        cb.addEventListener('change', () => {
          if (cb.checked) {
            if (estado.selecionadas.length >= MAX_SERIES) { cb.checked = false; $('#sel-resumo').textContent = `Máximo de ${MAX_SERIES} séries`; return; }
            estado.selecionadas.push(id);
          } else estado.selecionadas = estado.selecionadas.filter((x) => x !== id);
          atualizarResumoSel();
          renderSeries();
        });
        lista.append(el('label', { style: `--cor:${corGrupo(g)}` }, cb, el('span', { class: 'ponto' }), D.series[id].nome));
      }
    }
    atualizarResumoSel();
    document.addEventListener('click', (ev) => { const det = $('.seletor'); if (det.open && !det.contains(ev.target)) det.open = false; });
    $$('[data-periodo]').forEach((b) => b.addEventListener('click', () => { estado.periodo = b.dataset.periodo; $$('[data-periodo]').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); renderSeries(); }));
    $$('[data-modo]').forEach((b) => b.addEventListener('click', () => { if (b.disabled) return; estado.modo = b.dataset.modo; renderSeries(); }));
    chips($('#chips-cat'), CATEGORIAS, estado.categorias, corCat, renderSeries);
    if (typeof montarControlesCerebro === 'function') montarControlesCerebro();
    if (typeof montarControlesHeat === 'function') montarControlesHeat();
    if (typeof montarControlesTimeline === 'function') montarControlesTimeline();
  }
  function atualizarResumoSel() { $('#sel-resumo').textContent = `Séries (${estado.selecionadas.length}) ▾`; }
```

- [ ] **Step 2: Inserir no marcador `// @@ABAS@@`**

```js
  // ---------- aba Séries ----------
  function renderSeries() {
    const ids = estado.selecionadas.filter((id) => D.series[id]);
    const unidades = new Set(ids.map((id) => D.series[id].unidade));
    const misto = unidades.size > 1;
    const modo = misto ? 'base100' : estado.modo;
    $('#modo-nivel').disabled = misto;
    $('#aviso-modo').hidden = !misto;
    $$('[data-modo]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.modo === modo)));

    const ultimo = ids.reduce((m, id) => (D.series[id].fim > m ? D.series[id].fim : m), '0000-00-00');
    const anos = PERIODOS[estado.periodo];
    const inicio = anos ? anosAtras(ultimo, anos) : '0000-00-00';

    const series = ids.map((id, i) => {
      const s = D.series[id];
      let dados = pontos(id).filter((p) => p[0] >= inicio);
      if (modo === 'base100' && dados.length) { const b = dados[0][1]; dados = b ? dados.map(([d, v]) => [d, (v / b) * 100]) : []; }
      return { id, name: s.nome, type: 'line', showSymbol: false, symbolSize: 8, sampling: 'lttb', data: dados, lineStyle: { width: 2, color: corSlot(i) }, itemStyle: { color: corSlot(i) }, emphasis: { focus: 'series' } };
    });
    const eventos = D.eventos.filter((e) => estado.categorias.has(e.categoria) && e.data >= inicio && e.data <= ultimo);
    series.push({
      name: 'Eventos', type: 'scatter', xAxisIndex: 1, yAxisIndex: 1, symbolSize: 10,
      data: eventos.map((e) => ({ value: [e.data, ORDEM_CAT.indexOf(e.categoria)], evento: e, itemStyle: { color: corCat(e.categoria), borderColor: cssVar('--card'), borderWidth: 2 } })),
    });

    const c = grafico('chart-series');
    c.setOption({
      textStyle: textoBase(), animation: false,
      legend: { data: ids.map((id) => D.series[id].nome), top: 0, textStyle: { color: cssVar('--text-2') }, icon: 'path://M0,5 L20,5 L20,7 L0,7 Z', itemWidth: 18 },
      grid: [{ left: 60, right: 24, top: 44, height: '58%' }, { left: 60, right: 24, top: '76%', height: 44 }],
      axisPointer: { link: [{ xAxisIndex: 'all' }], lineStyle: { color: cssVar('--muted') } },
      tooltip: Object.assign(tooltipBase(), { trigger: 'axis', formatter: tooltipSeries }),
      xAxis: [
        Object.assign({ type: 'time' }, eixoBase(), { splitLine: { show: false } }),
        Object.assign({ type: 'time', gridIndex: 1 }, eixoBase(), { axisLabel: { show: false }, splitLine: { show: false }, axisLine: { show: false } }),
      ],
      yAxis: [
        Object.assign({ type: 'value', scale: true, name: modo === 'base100' ? 'Base 100' : [...unidades][0] || '', nameTextStyle: { color: cssVar('--muted'), align: 'left' } }, eixoBase(), { axisLine: { show: false } }),
        { type: 'value', gridIndex: 1, min: -1, max: ORDEM_CAT.length, show: false },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1] },
        { type: 'slider', xAxisIndex: [0, 1], bottom: 6, height: 22, borderColor: 'transparent', backgroundColor: cssVar('--bg'), fillerColor: 'rgba(120,120,140,.18)', handleStyle: { color: cssVar('--muted') }, textStyle: { color: cssVar('--muted') }, dataBackground: { lineStyle: { color: cssVar('--muted') }, areaStyle: { color: cssVar('--grid') } } },
      ],
      series,
    }, true);
    c.on('click', (p) => { if (p.seriesType === 'scatter' && p.data && p.data.evento) mostrarEvento(p.data.evento); });
  }

  function tooltipSeries(params) {
    const lista = Array.isArray(params) ? params : [params];
    const caixa = el('div', { class: 'tt' });
    const linhas = lista.filter((p) => p.seriesType === 'line');
    if (linhas.length) {
      caixa.append(el('div', { class: 'tt-titulo', text: fmtData(String(linhas[0].value[0]).slice(0, 10)) }));
      for (const p of linhas) {
        const id = p.seriesId;
        caixa.append(el('div', { class: 'tt-linha' }, el('span', { class: 'tt-chave', style: `background:${p.color}` }), el('strong', { text: fmt(p.value[1], id && D.series[id] ? casasDe(id) : 2) }), el('span', { class: 'tt-nome', text: p.seriesName })));
      }
    }
    for (const p of lista.filter((q) => q.seriesType === 'scatter' && q.data && q.data.evento)) {
      const e = p.data.evento;
      caixa.append(el('div', { class: 'tt-evento' }, el('div', { class: 'tt-titulo', text: `${fmtData(e.data)} · ${e.titulo}` }), el('div', { class: 'tt-desc', text: e.descricao })));
    }
    return caixa;
  }

  function tabelaImpactos(e) {
    const corpo = el('tbody');
    for (const id of e.series) {
      if (!D.series[id]) continue;
      const i30 = impacto(id, e.data, 30), i90 = impacto(id, e.data, 90);
      corpo.append(el('tr', {}, el('td', { text: D.series[id].nome }), el('td', { class: classeVar(i30), text: fmtVar(id, i30) }), el('td', { class: classeVar(i90), text: fmtVar(id, i90) })));
    }
    return el('table', { class: 'impactos' }, el('thead', {}, el('tr', {}, el('th', { text: 'Série' }), el('th', { text: '30 dias' }), el('th', { text: '90 dias' }))), corpo);
  }
  function cabecalhoEvento(e) {
    return el('div', { class: 'evento-cab' },
      el('time', { datetime: e.data, text: fmtData(e.data) }),
      el('span', { class: 'chip cat', style: `--cor:${corCat(e.categoria)}`, text: CATEGORIAS[e.categoria] || e.categoria }),
      e.auto ? el('span', { class: 'chip', text: 'detectado na série' }) : null);
  }
  function mostrarEvento(e) {
    const box = $('#evento-detalhe');
    box.hidden = false;
    box.replaceChildren(cabecalhoEvento(e), el('h3', { text: e.titulo }), el('p', { text: e.descricao }), tabelaImpactos(e));
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  RENDER.series = renderSeries;
```

- [ ] **Step 3: Verificar**

Run: `node --check painel.js` e recarregue `http://localhost:8765/painel.html`.
Expected: gráfico com Selic, IPCA 12m e dólar em Base 100 nos últimos 10 anos; botão Nível desabilitado com o aviso "Unidades diferentes"; ao deixar só Selic e CDI, Nível habilita e mostra % a.a.; faixa inferior com pontos coloridos; passar o mouse na faixa mostra o evento; clicar abre o cartão com a tabela 30/90 dias; desligar um chip de categoria remove os pontos; períodos 1a…Tudo funcionam; troca de tema mantém tudo legível; seletor limita a 8 séries.

- [ ] **Step 4: Commit**

```bash
git add painel.js
git commit -m "feat(painel): aba Séries com eixo único, Base 100 e faixa de eventos"
```

---

### Task 12: Painel — aba Cérebro (grafo de correlações)

**Files:**
- Modify: `painel.js` (inserir no marcador `// @@ABAS@@`, após o código da Task 11)

**Interfaces:**
- Produces: `montarControlesCerebro()`, `renderCerebro()`, `tooltipCerebro(p)`, `renderPainelNo()`.

- [ ] **Step 1: Inserir o código**

```js
  // ---------- aba Cérebro ----------
  function montarControlesCerebro() {
    segmentosJanela($('[data-janela-grupo=cerebro]'), 'janela', renderCerebro);
    const slider = $('#corte');
    slider.addEventListener('input', () => { estado.corte = Number(slider.value); $('#corte-valor').textContent = fmt(estado.corte, 2); renderCerebro(); });
    chips($('#chips-grupo'), GRUPOS, estado.gruposCerebro, corGrupo, renderCerebro);
  }

  function renderCerebro() {
    const visivel = (id) => D.series[id] && estado.gruposCerebro.has(D.series[id].grupo);
    const ar = (D.arestas[estado.janela] || []).filter((a) => Math.abs(a.r) >= estado.corte && visivel(a.a) && visivel(a.b));
    const peso = {};
    for (const a of ar) { peso[a.a] = (peso[a.a] || 0) + Math.abs(a.r); peso[a.b] = (peso[a.b] || 0) + Math.abs(a.r); }
    const ids = ((D.correlacao[estado.janela] || {}).ids || []).filter(visivel);
    const maxPeso = Math.max(0.01, ...Object.values(peso));
    const nodes = ids.map((id) => ({
      id, name: D.series[id].nome, category: ORDEM_GRUPOS.indexOf(D.series[id].grupo), value: peso[id] || 0,
      symbolSize: 12 + 36 * ((peso[id] || 0) / maxPeso), itemStyle: { opacity: peso[id] ? 1 : 0.35 },
    }));
    const links = ar.map((a) => ({ source: a.a, target: a.b, value: a.r, n: a.n, lineStyle: { width: 1 + 6 * Math.abs(a.r), color: a.r > 0 ? cssVar('--pos') : cssVar('--neg'), opacity: 0.7, curveness: 0.12 } }));
    const c = grafico('chart-cerebro');
    c.setOption({
      textStyle: textoBase(),
      tooltip: Object.assign(tooltipBase(), { formatter: tooltipCerebro }),
      legend: { data: ORDEM_GRUPOS.map((g) => GRUPOS[g]), top: 0, textStyle: { color: cssVar('--text-2') } },
      series: [{
        type: 'graph', layout: 'force', roam: true, draggable: true, data: nodes, links,
        categories: ORDEM_GRUPOS.map((g) => ({ name: GRUPOS[g], itemStyle: { color: corGrupo(g) } })),
        label: { show: true, position: 'right', color: cssVar('--text'), fontSize: 11 },
        force: { repulsion: 340, gravity: 0.1, edgeLength: [50, 220], friction: 0.15 },
        emphasis: { focus: 'adjacency', lineStyle: { opacity: 1 } },
        lineStyle: { opacity: 0.7 }, edgeSymbol: ['none', 'none'],
      }],
    }, true);
    c.on('click', (p) => { if (p.dataType === 'node') { estado.noSelecionado = p.data.id; renderPainelNo(); } });
    $('#n-arestas').textContent = `${ar.length} conexões · ${nodes.length} variáveis · janela ${JANELAS[estado.janela].toLowerCase()}`;
    renderPainelNo();
  }

  function tooltipCerebro(p) {
    const caixa = el('div', { class: 'tt' });
    if (p.dataType === 'edge') {
      caixa.append(el('div', { class: 'tt-titulo', text: `${D.series[p.data.source].nome} ↔ ${D.series[p.data.target].nome}` }),
        el('div', {}, el('strong', { text: 'r = ' + fmt(p.data.value, 2) }), el('span', { class: 'tt-nome', text: ` · ${p.data.n} meses` })));
    } else {
      const s = D.series[p.data.id];
      caixa.append(el('div', { class: 'tt-titulo', text: s.nome }), el('div', { class: 'tt-nome', text: `${GRUPOS[s.grupo]} · ${s.unidade} · desde ${fmtData(s.inicio)}` }),
        el('div', { text: `Conectividade ${fmt(p.data.value, 2)}` }));
    }
    return caixa;
  }

  function renderPainelNo() {
    const box = $('#painel-no');
    const m = D.correlacao[estado.janela];
    const id = estado.noSelecionado;
    if (!id || !m || !m.ids.includes(id)) { box.replaceChildren(el('h3', { text: 'Correlações' }), el('p', { class: 'muted', text: 'Clique num nó para ver com quem ele se correlaciona nesta janela.' })); return; }
    const i = m.ids.indexOf(id);
    const linhas = m.ids.map((outro, j) => ({ outro, r: m.matriz[i][j], n: m.n[i][j] })).filter((x) => x.outro !== id && x.r != null).sort((a, b) => Math.abs(b.r) - Math.abs(a.r));
    box.replaceChildren(
      el('h3', { text: D.series[id].nome }),
      el('p', { class: 'muted', text: `${linhas.length} pares com pelo menos 24 meses em comum · janela ${JANELAS[estado.janela].toLowerCase()}` }),
      ...linhas.map((x) => {
        const barra = el('div', { class: 'corr-barra' });
        const pct = Math.abs(x.r) * 50;
        barra.append(el('i', { style: `left:${x.r < 0 ? 50 - pct : 50}%;width:${pct}%;background:${x.r > 0 ? cssVar('--pos') : cssVar('--neg')}` }));
        return el('div', { class: 'corr-linha', title: `${x.n} meses` },
          el('div', { class: 'corr-nome' }, el('span', { class: 'ponto', style: `width:8px;height:8px;border-radius:50%;background:${corGrupo(D.series[x.outro].grupo)};flex:none` }), el('span', { text: D.series[x.outro].nome }), barra),
          el('div', { class: 'corr-valor ' + classeVar(x.r), text: fmtSinal(x.r, 2) }));
      }));
  }
  RENDER.cerebro = renderCerebro;
```

- [ ] **Step 2: Verificar**

Run: `node --check painel.js`, recarregue e clique na aba Cérebro.
Expected: grafo com ~29 nós coloridos por grupo, arestas azuis e vermelhas, nós de juros (Selic, CDI, Selic efetiva) claramente agrupados; slider muda a densidade e o texto de contagem; trocar a janela para 2 anos muda as conexões; desligar um grupo remove seus nós; clicar num nó preenche o painel lateral com barras ordenadas; a legenda do ECharts esconde/mostra grupos.

- [ ] **Step 3: Commit**

```bash
git add painel.js
git commit -m "feat(painel): aba Cérebro com grafo de força e painel do nó"
```

---

### Task 13: Painel — aba Correlações (heatmap)

**Files:**
- Modify: `painel.js` (inserir no marcador `// @@ABAS@@`, após a Task 12)

**Interfaces:**
- Produces: `montarControlesHeat()`, `renderHeat()`.

- [ ] **Step 1: Inserir o código**

```js
  // ---------- aba Correlações ----------
  function montarControlesHeat() { segmentosJanela($('[data-janela-grupo=heat]'), 'janelaHeat', renderHeat); }

  function renderHeat() {
    const m = D.correlacao[estado.janelaHeat];
    const dom = document.getElementById('chart-heat');
    if (!m || !m.ids.length) { dom.textContent = 'Sem dados para esta janela.'; return; }
    const ordem = m.ids.map((_, i) => i).sort((a, b) => ORDEM_GRUPOS.indexOf(D.series[m.ids[a]].grupo) - ORDEM_GRUPOS.indexOf(D.series[m.ids[b]].grupo) || a - b);
    const ids = ordem.map((i) => m.ids[i]);
    const nomes = ids.map((id) => D.series[id].nome);
    const data = [];
    ordem.forEach((oi, x) => ordem.forEach((oj, y) => {
      const r = m.matriz[oi][oj];
      if (r != null) data.push({ value: [x, y, r], n: m.n[oi][oj], label: { color: Math.abs(r) > 0.55 ? '#ffffff' : cssVar('--text') } });
    }));
    const tam = ids.length;
    dom.style.height = Math.max(520, Math.min(980, tam * 28 + 200)) + 'px';
    const c = grafico('chart-heat');
    c.setOption({
      textStyle: textoBase(), animation: false,
      tooltip: Object.assign(tooltipBase(), {
        position: 'top',
        formatter: (p) => el('div', { class: 'tt' }, el('div', { class: 'tt-titulo', text: `${nomes[p.value[0]]} × ${nomes[p.value[1]]}` }), el('div', {}, el('strong', { text: 'r = ' + fmt(p.value[2], 2) }), el('span', { class: 'tt-nome', text: ` · ${p.data.n} meses` }))),
      }),
      grid: { left: 190, right: 24, top: 12, bottom: 170 },
      xAxis: Object.assign({ type: 'category', data: nomes }, eixoBase(), { splitLine: { show: false }, axisLabel: { rotate: 55, fontSize: 10, color: cssVar('--muted') } }),
      yAxis: Object.assign({ type: 'category', data: nomes, inverse: true }, eixoBase(), { splitLine: { show: false }, axisLabel: { fontSize: 10, color: cssVar('--muted') } }),
      visualMap: { min: -1, max: 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 4, itemWidth: 12, itemHeight: 180, textStyle: { color: cssVar('--muted') }, inRange: { color: [cssVar('--neg'), cssVar('--mid'), cssVar('--pos')] } },
      series: [{ type: 'heatmap', data, label: { show: tam <= 24, fontSize: 9, formatter: (p) => p.value[2].toFixed(2) }, itemStyle: { borderColor: cssVar('--card'), borderWidth: 2 }, emphasis: { itemStyle: { borderColor: cssVar('--text') } } }],
    }, true);
  }
  RENDER.correlacoes = renderHeat;
```

- [ ] **Step 2: Verificar**

Run: `node --check painel.js`, recarregue, aba Correlações.
Expected: matriz quadrada ordenada por grupo, diagonal azul forte, células vazias onde há menos de 24 meses em comum (ex.: EUR/BRL × séries antigas na janela `tudo` não ficam vazias, mas `desemprego` × pares curtos podem ficar), tooltip com r e n, rótulos legíveis nos dois temas, barra divergente azul/cinza/vermelho.

- [ ] **Step 3: Commit**

```bash
git add painel.js
git commit -m "feat(painel): aba Correlações com heatmap divergente"
```

---

### Task 14: Painel — aba Linha do tempo

**Files:**
- Modify: `painel.js` (inserir no marcador `// @@ABAS@@`, após a Task 13)

**Interfaces:**
- Produces: `montarControlesTimeline()`, `renderTimeline()`, `cardEvento(e)`. Reusa `cabecalhoEvento` e `tabelaImpactos` da Task 11.

- [ ] **Step 1: Inserir o código**

```js
  // ---------- aba Linha do tempo ----------
  function montarControlesTimeline() {
    chips($('#chips-timeline'), CATEGORIAS, estado.filtroCat, corCat, renderTimeline);
    const busca = $('#busca');
    let timer = null;
    busca.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { estado.busca = busca.value; renderTimeline(); }, 150); });
  }

  function renderTimeline() {
    const lista = $('#lista-eventos');
    const q = estado.busca.trim().toLowerCase();
    const evs = D.eventos
      .filter((e) => estado.filtroCat.has(e.categoria) && (!q || (e.titulo + ' ' + e.descricao).toLowerCase().includes(q)))
      .slice().sort((a, b) => b.data.localeCompare(a.data));
    $('#n-eventos').textContent = `${evs.length} eventos`;
    lista.replaceChildren(...evs.map(cardEvento));
    if (!evs.length) lista.append(el('p', { class: 'muted', text: 'Nenhum evento com esses filtros.' }));
  }

  function cardEvento(e) {
    return el('article', { class: 'evento' }, cabecalhoEvento(e), el('h3', { text: e.titulo }), el('p', { text: e.descricao }), tabelaImpactos(e));
  }
  RENDER.timeline = renderTimeline;
```

- [ ] **Step 2: Verificar**

Run: `node --check painel.js`, recarregue, aba Linha do tempo.
Expected: ~110 cards do mais recente ao mais antigo; eventos automáticos com a etiqueta "detectado na série"; busca por "Lehman" filtra para um card; desligar "Copom" esconde os automáticos; tabela 30/90 dias com sinais coloridos e "—" quando não há dado (ex.: eventos de 1986 para séries que começam depois).

- [ ] **Step 3: Commit**

```bash
git add painel.js
git commit -m "feat(painel): aba Linha do tempo com busca e impacto 30/90 dias"
```

---

### Task 15: README, revisão final e verificação completa

**Files:**
- Create: `README.md`
- Modify: `painel.js` (remover o marcador `// @@ABAS@@` e o stub `emConstrucao` se ainda existirem)

- [ ] **Step 1: Escrever `README.md`**

```markdown
# Painel de Taxas de Mercado

Painel local para acompanhar juros, inflação, câmbio, exterior e bolsa com
histórico máximo, eventos que explicam os movimentos e um grafo de
correlações.

## Uso

```bash
pip install -r requirements.txt
python atualizar.py          # baixa tudo e gera dados.json / dados.js
python -m http.server 8765   # opcional
```

Abra `painel.html` (duplo clique funciona) ou `http://localhost:8765/painel.html`.

- `python atualizar.py --offline` recalcula só do cache (`cache/`).
- Fontes: BCB SGS, FRED, Yahoo Finance e IPEA. Nenhuma chave necessária.
- `eventos.json` é a base curada de eventos; edite à vontade (data ISO,
  categoria entre `copom, fomc, crise, politica, fiscal, externo, plano`, e
  ids de séries de `pipeline/series.py`). Os ciclos do Copom são detectados
  automaticamente na série da Selic meta.
- Para adicionar uma série, inclua uma linha em `pipeline/series.py`.

## Testes

```bash
python -m pytest -q
```

## Como a correlação é calculada

Base mensal; juros e taxas entram como variação em pontos percentuais,
preços e índices como retorno logarítmico, inflação mensal como nível.
Pearson com no mínimo 24 meses por par, em quatro janelas (tudo, 10, 5 e
2 anos). Detalhes em `docs/superpowers/specs/2026-09-25-painel-taxas-design.md`.
```

- [ ] **Step 2: Limpar marcadores e rodar tudo**

Remova de `painel.js` a linha `// @@ABAS@@` e as cinco linhas do bloco `// stubs substituídos nas Tasks 11–14` (a constante `emConstrucao` e as quatro atribuições `RENDER.x = emConstrucao(...)`), já que as abas reais registram `RENDER` mais abaixo.

Run:
```bash
node --check painel.js
python -m pytest -q
python atualizar.py --offline
```
Expected: sintaxe ok, todos os testes passando, geração offline concluída sem erro.

- [ ] **Step 3: Verificação visual final (checklist)**

Abra o painel via http e via file:// e confira:
- [ ] KPIs com valores plausíveis (Selic meta próxima do valor atual do BCB, dólar com 3 casas, Ibovespa sem casas).
- [ ] Séries: Base 100 padrão, Nível habilitado só com unidades iguais, faixa de eventos, cartão de impacto ao clicar.
- [ ] Cérebro: grafo legível, slider e janela funcionando, painel do nó.
- [ ] Correlações: heatmap com legenda divergente, tooltip com n.
- [ ] Linha do tempo: busca, filtros, etiqueta de eventos automáticos.
- [ ] Tema claro e escuro, ambos legíveis; preferência persiste.
- [ ] Largura de 380 px (DevTools): sem rolagem horizontal, controles quebram linha, grafo e heatmap ainda abrem.
- [ ] Console do navegador sem erros.

- [ ] **Step 4: Commit final**

```bash
git add README.md painel.js
git commit -m "docs: README e limpeza final do painel"
```
