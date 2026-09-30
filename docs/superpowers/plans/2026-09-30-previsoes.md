# Aba Previsões: plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar este plano tarefa por tarefa. Os passos usam checkbox (`- [ ]`) para acompanhamento.

**Objetivo:** criar a aba "Previsões" do painel, com o consenso do Boletim Focus, sinais calculados e agenda de Copom, FOMC e IPCA.

**Arquitetura:** o `atualizar.py` passa a baixar o Focus (API Olinda do BCB) com cache em `cache/focus.json`, ler o `agenda.json` curado e calcular os sinais em Python puro (`pipeline/sinais.py`). O resultado vai para o bloco `previsoes` do `dados.json`/`dados.js`. O `painel.js` só desenha: cartões de sinal, gráfico de trajetória (ECharts) e tabela da agenda.

**Tecnologias:** Python 3.10+, pandas, requests, pytest; HTML/CSS/JS sem build e ECharts 5.5.1 via CDN (já usado).

**Spec:** `docs/superpowers/specs/2026-09-30-previsoes-design.md`

## Restrições globais

- Python 3.10 ou superior. Nenhuma dependência nova, nem em Python nem em JS.
- Fonte das previsões: `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata`, sempre com `baseCalculo eq 0`.
- No `$filter`, espaços viram `%20`, nunca `+` (o Olinda responde 400 com `+`).
- Toda chamada HTTP passa por `fontes._get(..., json=True)`.
- Indicadores anuais: exatamente `IPCA`, `Câmbio`, `PIB Total` e `Selic`; ano atual até o atual + 3; últimas 13 semanas.
- Limites de revisão: IPCA ±0,20 p.p.; PIB ±0,20 p.p.; Selic ±0,25 p.p.; Câmbio ±R$ 0,10. Sequência mínima: 3 semanas; janela do acumulado: 4 semanas.
- Copom vira destaque com 7 dias ou menos; a agenda gera sinal para eventos em até 14 dias; o juro real vira destaque com percentil ≥ 90 ou ≤ 10, contra a série `juro_real` desde 2000-01.
- Os sinais nunca dizem "compre" ou "venda". Números no formato brasileiro (vírgula decimal). Única marcação: `**negrito**`.
- Cor do destaque: `#fab219`. Cores da agenda: Copom `--c-copom`, FOMC `--c-fomc`, IPCA `--c-plano`.
- Os arquivos do repositório usam quebra de linha **LF**. No Windows, não reescreva arquivos com `Path.write_text` (grava CRLF). Use a ferramenta de edição ou `write_bytes`. Confira com `git diff --stat` antes de cada commit: o diff deve ter só as linhas alteradas.
- Commits terminam com a linha `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Foco da revisão

Situações que a spec implica e que um usuário vai encontrar. Cada uma tem teste na tarefa indicada.

1. **O Focus ainda traz uma reunião do Copom que já aconteceu** (pesquisa de sexta, Copom na quarta seguinte): a decisão esperada das reuniões futuras é contada a partir da Selic atual, e a reunião passada sai do gráfico e dos avisos. Teste nas Tarefas 3 e 6.
2. **`agenda.json` ausente ou sem Copom:** o gráfico da Selic usa a projeção anual (um ponto por 31/12) e o painel não enche o topo de avisos por reunião. Teste na Tarefa 6.
3. **`cache/focus.json` corrompido e rede fora:** aviso claro, aba sem projeções, sem exceção. Teste na Tarefa 1.
4. **Dia da reunião:** o sinal diz "Copom hoje", continua aparecendo e é destaque. Teste na Tarefa 3.
5. **Série base ausente** (`selic_meta`, `usd_brl` ou `fed_funds` sem dados): os sinais que dependem dela somem e o resto continua. Teste na Tarefa 6.

## Mapa de arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `pipeline/focus.py` | criar | URL OData, consultas, série semanal, cache |
| `pipeline/agenda.py` | criar | Leitura e validação do `agenda.json` |
| `agenda.json` | criar | Datas curadas de Copom, FOMC e IPCA |
| `pipeline/sinais.py` | criar | Formatação pt-BR e as seis regras de sinal, puras |
| `pipeline/exportar.py` | modificar | `previsoes()` monta o bloco; `montar()` ganha a chave `previsoes` |
| `atualizar.py` | modificar | Orquestra Focus, agenda e previsões |
| `painel.html` / `painel.css` / `painel.js` | modificar | Aba, cartões, gráfico e agenda |
| `README.md` | modificar | Seção sobre a aba e o `agenda.json` |
| `tests/test_focus.py`, `tests/test_agenda.py`, `tests/test_sinais.py`, `tests/test_previsoes.py` | criar | Testes |
| `tests/fixtures/focus_bruto.json` | criar | Resposta real do Focus gravada |
| `tests/test_exportar.py`, `tests/test_atualizar.py` | modificar | Chave nova e Focus substituído nos testes |

---

### Tarefa 1: módulo `pipeline/focus.py`

**Arquivos:**
- Criar: `pipeline/focus.py`
- Criar: `tests/test_focus.py`
- Criar: `tests/fixtures/focus_bruto.json` (gravado no Passo 5)

**Interfaces:**
- Usa: `fontes._get(url, params=None, timeout=..., json=False) -> Response | None` e `fontes.RespostaVazia`.
- Fornece:
  - `url_odata(entidade: str, opcoes: dict) -> str`
  - `consultar(entidade: str, **opcoes) -> list[dict]`
  - `baixar(hoje: date) -> dict`, que devolve `{"data_pesquisa": str, "selic": list[dict], "anuais": list[dict], "infl12": dict | None}`
  - `semanal(anuais: list[dict]) -> dict[str, dict[str, list[dict]]]`, que devolve `{indicador: {ano: [{"semana", "Mediana", "Minimo", "Maximo", "numeroRespondentes"}]}}` em ordem de semana
  - `obter(arquivo: Path, offline: bool, hoje: date, baixar: Callable[[date], dict]) -> tuple[dict | None, str | None]`

- [ ] **Passo 1: escrever os testes que falham**

`tests/test_focus.py`:

```python
import json
from datetime import date
from pathlib import Path

import pytest

from pipeline import focus, fontes

FIX = Path(__file__).parent / "fixtures" / "focus_bruto.json"


def test_url_odata_codifica_espaco_como_%20():
    url = focus.url_odata("ExpectativasMercadoAnuais", {"filter": "Indicador eq 'IPCA' and baseCalculo eq 0", "top": 5})
    assert url.startswith(focus.BASE + "/ExpectativasMercadoAnuais?$format=json&")
    assert "$filter=Indicador%20eq%20%27IPCA%27%20and%20baseCalculo%20eq%200" in url
    assert "$top=5" in url
    assert "+" not in url


class Resposta:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_consultar_devolve_value_e_lista_vazia_em_404(monkeypatch):
    chamadas = []

    def get_falso(url, params=None, timeout=None, json=False):
        chamadas.append((url, json))
        return Resposta({"value": [{"a": 1}]}) if "Selic" in url else None

    monkeypatch.setattr(fontes, "_get", get_falso)
    assert focus.consultar("ExpectativasMercadoSelic", top=1) == [{"a": 1}]
    assert focus.consultar("ExpectativasMercadoAnuais", top=1) == []
    assert all(j is True for _, j in chamadas)


def linha_selic(data, reuniao, mediana):
    return {"Data": data, "Reuniao": reuniao, "Mediana": mediana, "Minimo": mediana - 0.5,
            "Maximo": mediana + 0.5, "numeroRespondentes": 100, "baseCalculo": 0}


def test_baixar_fica_so_com_a_pesquisa_mais_recente_da_selic(monkeypatch):
    vistos = {}

    def consultar_falso(entidade, **op):
        vistos[entidade] = op
        if entidade == "ExpectativasMercadoSelic":
            return [linha_selic("2026-09-25", "R7/2026", 13.5), linha_selic("2026-09-25", "R8/2026", 13.5),
                    linha_selic("2026-09-18", "R7/2026", 13.75)]
        if entidade == "ExpectativasMercadoInflacao12Meses":
            return [{"Data": "2026-09-25", "Mediana": 4.65}]
        return [{"Indicador": "IPCA"}]

    monkeypatch.setattr(focus, "consultar", consultar_falso)
    b = focus.baixar(date(2026, 9, 30))
    assert b["data_pesquisa"] == "2026-09-25"
    assert [r["Reuniao"] for r in b["selic"]] == ["R7/2026", "R8/2026"]
    assert b["infl12"]["Mediana"] == 4.65
    filtro = vistos["ExpectativasMercadoAnuais"]["filter"]
    assert "Data ge '2026-07-01'" in filtro                     # 13 semanas antes de 30/09
    assert "DataReferencia ge '2026'" in filtro and "DataReferencia le '2029'" in filtro
    assert all(f"Indicador eq '{i}'" in filtro for i in focus.INDICADORES)


def test_baixar_sem_selic_levanta_resposta_vazia(monkeypatch):
    monkeypatch.setattr(focus, "consultar", lambda entidade, **op: [])
    with pytest.raises(fontes.RespostaVazia):
        focus.baixar(date(2026, 9, 30))


def test_semanal_pega_a_ultima_linha_de_cada_semana():
    anuais = [
        {"Indicador": "IPCA", "Data": "2026-09-14", "DataReferencia": "2026", "Mediana": 4.9, "Minimo": 4, "Maximo": 6, "numeroRespondentes": 90},
        {"Indicador": "IPCA", "Data": "2026-09-18", "DataReferencia": "2026", "Mediana": 4.95, "Minimo": 4, "Maximo": 6, "numeroRespondentes": 144},
        {"Indicador": "IPCA", "Data": "2026-09-25", "DataReferencia": "2026", "Mediana": 4.99, "Minimo": 4.2, "Maximo": 5.9, "numeroRespondentes": 144},
    ]
    s = focus.semanal(anuais)
    assert list(s) == ["IPCA"]
    assert s["IPCA"]["2026"] == [
        {"semana": "2026-09-18", "Mediana": 4.95, "Minimo": 4.0, "Maximo": 6.0, "numeroRespondentes": 144},
        {"semana": "2026-09-25", "Mediana": 4.99, "Minimo": 4.2, "Maximo": 5.9, "numeroRespondentes": 144},
    ]
    json.dumps(s)  # tipos numpy não podem vazar para o JSON
    assert focus.semanal([]) == {}


def test_semanal_na_resposta_real_gravada():
    bruto = json.loads(FIX.read_text(encoding="utf-8"))
    s = focus.semanal(bruto["anuais"])
    assert set(s) == set(focus.INDICADORES)
    for ind, anos in s.items():
        assert "2026" in anos and "2027" in anos, ind
        for linhas in anos.values():
            semanas = [l["semana"] for l in linhas]
            assert semanas == sorted(semanas) and len(set(semanas)) == len(semanas)
            assert all(date.fromisoformat(d).weekday() == 4 for d in semanas)  # sexta-feira


def test_obter_grava_cache_e_usa_na_falha(tmp_path):
    arq = tmp_path / "cache" / "focus.json"
    bruto = {"data_pesquisa": "2026-09-25", "selic": [], "anuais": [], "infl12": None}
    assert focus.obter(arq, False, date(2026, 9, 30), lambda h: bruto) == (bruto, None)

    def falha(h):
        raise ConnectionError("rede fora")

    b, aviso = focus.obter(arq, False, date(2026, 10, 1), falha)
    assert b == bruto
    assert aviso == "Focus: falha ao baixar (rede fora); usando cache de 2026-09-30"


def test_obter_offline_le_cache_sem_chamar_a_rede(tmp_path):
    arq = tmp_path / "focus.json"
    arq.write_text(json.dumps({"baixado_em": "2026-09-30", "bruto": {"selic": [1]}}), encoding="utf-8")
    b, aviso = focus.obter(arq, True, date(2026, 10, 1), lambda h: 1 / 0)
    assert b == {"selic": [1]}
    assert aviso == "Focus: lido do cache de 2026-09-30 (offline)"
    assert "modo offline" not in aviso  # o atualizar.py agrupa avisos com esse texto como séries


def test_obter_sem_cache_e_cache_corrompido(tmp_path):
    arq = tmp_path / "focus.json"
    b, aviso = focus.obter(arq, False, date(2026, 9, 30), lambda h: 1 / 0)
    assert b is None and aviso.startswith("Focus: falha ao baixar (division by zero) e sem cache")
    arq.write_text("{quebrado", encoding="utf-8")
    b, aviso = focus.obter(arq, False, date(2026, 9, 30), lambda h: 1 / 0)
    assert b is None and "cache ilegível" in aviso
```

- [ ] **Passo 2: rodar e ver falhar**

Comando: `python -m pytest tests/test_focus.py -q`
Esperado: erro de coleta, com `ImportError: cannot import name 'focus'`.

- [ ] **Passo 3: implementar `pipeline/focus.py`**

```python
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
    return {"data_pesquisa": data, "selic": selic, "anuais": anuais, "infl12": infl[0] if infl else None}


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
```

- [ ] **Passo 4: rodar os testes que não dependem do fixture**

Comando: `python -m pytest tests/test_focus.py -q -k "not resposta_real"`
Esperado: 8 passed.

- [ ] **Passo 5: gravar o fixture real**

Comando (precisa de internet):

```bash
python -c "import json; from datetime import date; from pipeline import focus; b = focus.baixar(date(2026, 9, 30)); open('tests/fixtures/focus_bruto.json', 'w', encoding='utf-8', newline='\n').write(json.dumps(b, ensure_ascii=False, indent=1))"
```

Esperado: arquivo com `data_pesquisa` igual a `"2026-09-25"` ou posterior, algumas dezenas de linhas em `selic` e centenas em `anuais`.

- [ ] **Passo 6: rodar a suíte inteira**

Comando: `python -m pytest -q`
Esperado: todos passam (57 anteriores + 9 novos).

- [ ] **Passo 7: commit**

```bash
git add pipeline/focus.py tests/test_focus.py tests/fixtures/focus_bruto.json
git commit -m "feat(focus): consultas ao Boletim Focus com série semanal e cache" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarefa 2: agenda curada (`pipeline/agenda.py` e `agenda.json`)

**Arquivos:**
- Criar: `pipeline/agenda.py`
- Criar: `agenda.json`
- Criar: `tests/test_agenda.py`

**Interfaces:**
- Fornece: `carregar(arquivo: Path, avisos: list[str]) -> list[dict]`, que devolve as entradas válidas em ordem de data. Cada entrada tem `data` (ISO), `tipo` (`copom` | `fomc` | `ipca`) e `titulo`, além de `reuniao` (`"R7/2026"`) quando o tipo é `copom`. Constantes `TIPOS` e `RE_REUNIAO`.

- [ ] **Passo 1: escrever os testes que falham**

`tests/test_agenda.py`:

```python
import json
from collections import Counter
from pathlib import Path

from pipeline import agenda

RAIZ = Path(__file__).parent.parent


def gravar(tmp_path, conteudo):
    arq = tmp_path / "agenda.json"
    arq.write_text(conteudo if isinstance(conteudo, str) else json.dumps(conteudo), encoding="utf-8")
    return arq


def test_carregar_valida_e_ordena(tmp_path):
    arq = gravar(tmp_path, [
        {"data": "2026-12-09", "tipo": "copom", "titulo": "Copom", "reuniao": "R8/2026"},
        {"data": "2026-10-28", "tipo": "fomc", "titulo": "FOMC"},
        {"data": "2026-11-04", "tipo": "copom", "titulo": "Copom"},               # sem reuniao
        {"data": "2026-02-30", "tipo": "ipca", "titulo": "IPCA de janeiro"},     # data inexistente
        {"data": "2026-11-10", "tipo": "ptax", "titulo": "?"},                   # tipo desconhecido
        {"data": "2026-11-11", "tipo": "copom", "titulo": "Copom", "reuniao": "R9/2026"},
        {"data": "2026-11-12", "tipo": "ipca", "titulo": "  "},
        "texto solto",
    ])
    avisos = []
    r = agenda.carregar(arq, avisos)
    assert [e["data"] for e in r] == ["2026-10-28", "2026-12-09"]
    assert avisos == ["agenda.json: 6 entrada(s) ignorada(s) por formato inválido"]


def test_carregar_arquivo_ausente_quebrado_ou_nao_lista(tmp_path):
    avisos = []
    assert agenda.carregar(tmp_path / "agenda.json", avisos) == []
    assert agenda.carregar(gravar(tmp_path, "{quebrado"), avisos) == []
    assert agenda.carregar(gravar(tmp_path, {"data": "2026-10-28"}), avisos) == []
    assert avisos[0] == "agenda.json não encontrado; aba Previsões sem agenda"
    assert avisos[1].startswith("agenda.json inválido (") and avisos[1].endswith("); aba Previsões sem agenda")
    assert avisos[2] == "agenda.json inválido (esperava uma lista); aba Previsões sem agenda"


def test_agenda_json_do_repositorio_integra():
    brutos = json.loads((RAIZ / "agenda.json").read_text(encoding="utf-8"))
    avisos = []
    validos = agenda.carregar(RAIZ / "agenda.json", avisos)
    assert avisos == [] and len(validos) == len(brutos)
    assert [e["data"] for e in brutos] == sorted(e["data"] for e in brutos), "agenda.json em ordem de data"
    reunioes = [e["reuniao"] for e in brutos if e["tipo"] == "copom"]
    assert len(reunioes) == len(set(reunioes))
    por_ano = Counter(r.split("/")[1] for r in reunioes)
    assert por_ano["2026"] == 8 and por_ano["2027"] == 8
    fomc = Counter(e["data"][:4] for e in brutos if e["tipo"] == "fomc")
    assert fomc["2026"] == 8 and fomc["2027"] == 8
```

- [ ] **Passo 2: rodar e ver falhar**

Comando: `python -m pytest tests/test_agenda.py -q`
Esperado: erro de coleta, com `ImportError: cannot import name 'agenda'`.

- [ ] **Passo 3: implementar `pipeline/agenda.py`**

```python
"""Agenda curada (agenda.json): reuniões do Copom e do FOMC e divulgações do IPCA."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

TIPOS = {"copom", "fomc", "ipca"}
RE_REUNIAO = re.compile(r"^R[1-8]/\d{4}$")


def _data_valida(v) -> bool:
    try:
        return isinstance(v, str) and len(v) == 10 and date.fromisoformat(v).isoformat() == v
    except ValueError:
        return False


def valida(e) -> bool:
    if not isinstance(e, dict) or e.get("tipo") not in TIPOS or not _data_valida(e.get("data")):
        return False
    if not (isinstance(e.get("titulo"), str) and e["titulo"].strip()):
        return False
    if e["tipo"] == "copom":
        return isinstance(e.get("reuniao"), str) and bool(RE_REUNIAO.match(e["reuniao"]))
    return True


def carregar(arquivo: Path, avisos: list[str]) -> list[dict]:
    """Lê agenda.json; problemas viram avisos, nunca exceção."""
    if not arquivo.exists():
        avisos.append("agenda.json não encontrado; aba Previsões sem agenda")
        return []
    try:
        brutos = json.loads(arquivo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        avisos.append(f"agenda.json inválido ({e}); aba Previsões sem agenda")
        return []
    if not isinstance(brutos, list):
        avisos.append("agenda.json inválido (esperava uma lista); aba Previsões sem agenda")
        return []
    validos = [e for e in brutos if valida(e)]
    if len(validos) < len(brutos):
        avisos.append(f"agenda.json: {len(brutos) - len(validos)} entrada(s) ignorada(s) por formato inválido")
    return sorted(validos, key=lambda e: e["data"])
```

- [ ] **Passo 4: criar `agenda.json`**

A `data` é o dia do anúncio (o segundo dia da reunião). Antes do commit, confira as datas nas fontes oficiais: Copom em https://www.bcb.gov.br/publicacoes/calendarioreunioescopom, FOMC em https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm e IPCA em https://www.ibge.gov.br/calendario-de-divulgacao.html. Se alguma data divergir, corrija aqui. O teste do Passo 1 só confere formato e contagem.

```json
[
{"data":"2026-01-28","tipo":"copom","titulo":"Copom","reuniao":"R1/2026"},
{"data":"2026-01-28","tipo":"fomc","titulo":"FOMC"},
{"data":"2026-03-18","tipo":"copom","titulo":"Copom","reuniao":"R2/2026"},
{"data":"2026-03-18","tipo":"fomc","titulo":"FOMC"},
{"data":"2026-04-29","tipo":"copom","titulo":"Copom","reuniao":"R3/2026"},
{"data":"2026-04-29","tipo":"fomc","titulo":"FOMC"},
{"data":"2026-06-17","tipo":"copom","titulo":"Copom","reuniao":"R4/2026"},
{"data":"2026-06-17","tipo":"fomc","titulo":"FOMC"},
{"data":"2026-07-29","tipo":"fomc","titulo":"FOMC"},
{"data":"2026-08-05","tipo":"copom","titulo":"Copom","reuniao":"R5/2026"},
{"data":"2026-09-16","tipo":"copom","titulo":"Copom","reuniao":"R6/2026"},
{"data":"2026-09-16","tipo":"fomc","titulo":"FOMC"},
{"data":"2026-10-09","tipo":"ipca","titulo":"IPCA de setembro"},
{"data":"2026-10-28","tipo":"fomc","titulo":"FOMC"},
{"data":"2026-11-04","tipo":"copom","titulo":"Copom","reuniao":"R7/2026"},
{"data":"2026-11-10","tipo":"ipca","titulo":"IPCA de outubro"},
{"data":"2026-12-09","tipo":"copom","titulo":"Copom","reuniao":"R8/2026"},
{"data":"2026-12-09","tipo":"fomc","titulo":"FOMC"},
{"data":"2026-12-10","tipo":"ipca","titulo":"IPCA de novembro"},
{"data":"2027-01-27","tipo":"copom","titulo":"Copom","reuniao":"R1/2027"},
{"data":"2027-01-27","tipo":"fomc","titulo":"FOMC"},
{"data":"2027-03-17","tipo":"copom","titulo":"Copom","reuniao":"R2/2027"},
{"data":"2027-03-17","tipo":"fomc","titulo":"FOMC"},
{"data":"2027-04-28","tipo":"copom","titulo":"Copom","reuniao":"R3/2027"},
{"data":"2027-04-28","tipo":"fomc","titulo":"FOMC"},
{"data":"2027-06-09","tipo":"fomc","titulo":"FOMC"},
{"data":"2027-06-16","tipo":"copom","titulo":"Copom","reuniao":"R4/2027"},
{"data":"2027-07-28","tipo":"fomc","titulo":"FOMC"},
{"data":"2027-08-04","tipo":"copom","titulo":"Copom","reuniao":"R5/2027"},
{"data":"2027-09-15","tipo":"fomc","titulo":"FOMC"},
{"data":"2027-09-22","tipo":"copom","titulo":"Copom","reuniao":"R6/2027"},
{"data":"2027-10-27","tipo":"copom","titulo":"Copom","reuniao":"R7/2027"},
{"data":"2027-10-27","tipo":"fomc","titulo":"FOMC"},
{"data":"2027-12-08","tipo":"copom","titulo":"Copom","reuniao":"R8/2027"},
{"data":"2027-12-08","tipo":"fomc","titulo":"FOMC"}
]
```

- [ ] **Passo 5: rodar os testes**

Comando: `python -m pytest tests/test_agenda.py -q`
Esperado: 3 passed.

- [ ] **Passo 6: commit**

```bash
git add pipeline/agenda.py agenda.json tests/test_agenda.py
git commit -m "feat(agenda): agenda curada de Copom, FOMC e IPCA com validação" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarefa 3: sinais do Copom e da trajetória da Selic

**Arquivos:**
- Criar: `pipeline/sinais.py`
- Criar: `tests/test_sinais.py`

**Interfaces:**
- Usa: entradas de agenda no formato da Tarefa 2.
- Fornece:
  - `fmt_br(v: float, casas: int = 2, sinal: bool = False) -> str`, por exemplo `13.75 → "13,75"`, `1234.5 → "1.234,50"` e, com `sinal=True`, `3.0 → "+3,00"`
  - `chave_reuniao(r: str) -> tuple[int, int]`, por exemplo `"R7/2026" → (2026, 7)`
  - `decisoes_esperadas(medianas: dict[str, float], selic_hoje: float, ignorar: set[str]) -> dict[str, dict]`, com valores `{"mediana": float, "dif": float}`
  - `sinal_copom(agenda: list[dict], medianas: dict[str, float], selic_hoje: float, hoje: date, ignorar: set[str]) -> dict | None`
  - `sinal_trajetoria(medianas: dict[str, float], selic_hoje: float, hoje: date, ignorar: set[str]) -> dict | None`
  - Um sinal é um `dict` com `nivel` (`"destaque"` | `"info"`), `tipo`, `texto` e, opcionalmente, `data`.

- [ ] **Passo 1: escrever os testes que falham**

`tests/test_sinais.py`:

```python
from datetime import date

from pipeline import sinais

HOJE = date(2026, 9, 30)
AGENDA = [
    {"data": "2026-09-16", "tipo": "copom", "titulo": "Copom", "reuniao": "R6/2026"},
    {"data": "2026-11-04", "tipo": "copom", "titulo": "Copom", "reuniao": "R7/2026"},
    {"data": "2026-12-09", "tipo": "copom", "titulo": "Copom", "reuniao": "R8/2026"},
    {"data": "2027-09-22", "tipo": "copom", "titulo": "Copom", "reuniao": "R6/2027"},
    {"data": "2027-12-08", "tipo": "copom", "titulo": "Copom", "reuniao": "R8/2027"},
]
MEDIANAS = {"R7/2026": 13.5, "R8/2026": 13.5, "R6/2027": 12.5, "R8/2027": 12.0, "R6/2028": 10.5}


def test_fmt_br():
    assert sinais.fmt_br(13.75) == "13,75"
    assert sinais.fmt_br(1234.5) == "1.234,50"
    assert sinais.fmt_br(7.94, 1) == "7,9"
    assert sinais.fmt_br(3.0, sinal=True) == "+3,00"
    assert sinais.fmt_br(-2.96, 1, sinal=True) == "-3,0"
    assert sinais.fmt_br(0.001, 1, sinal=True) == "0,0"


def test_chave_reuniao_ordena_por_ano_e_numero():
    assert sorted(["R1/2027", "R8/2026", "R2/2026"], key=sinais.chave_reuniao) == ["R2/2026", "R8/2026", "R1/2027"]


def test_decisao_conta_a_partir_da_reuniao_anterior():
    d = sinais.decisoes_esperadas(MEDIANAS, 13.75, set())
    assert d["R7/2026"] == {"mediana": 13.5, "dif": -0.25}
    assert d["R8/2026"] == {"mediana": 13.5, "dif": 0.0}     # manter em dezembro, não "cortar 0,25"
    assert d["R6/2027"]["dif"] == -1.0


def test_decisao_ignora_reuniao_que_ja_aconteceu():
    # Focus de sexta ainda traz a R6/2026, que foi na quarta: a R7 conta a partir da Selic de hoje.
    d = sinais.decisoes_esperadas({"R6/2026": 14.0, "R7/2026": 13.5}, 13.75, {"R6/2026"})
    assert "R6/2026" not in d and d["R7/2026"]["dif"] == -0.25


def test_sinal_copom_info_longe_e_texto():
    s = sinais.sinal_copom(AGENDA, MEDIANAS, 13.75, HOJE, set())
    assert s == {"nivel": "info", "tipo": "copom", "data": "2026-11-04",
                 "texto": "Copom em 35 dias (04/11): mercado espera **cortar 0,25 p.p.**, com a Selic indo a 13,50%."}


def test_sinal_copom_destaque_a_7_dias_e_info_a_8():
    assert sinais.sinal_copom(AGENDA, MEDIANAS, 13.75, date(2026, 10, 28), set())["nivel"] == "destaque"
    assert sinais.sinal_copom(AGENDA, MEDIANAS, 13.75, date(2026, 10, 27), set())["nivel"] == "info"


def test_sinal_copom_no_dia_e_manter():
    s = sinais.sinal_copom(AGENDA, MEDIANAS, 13.5, date(2026, 12, 9), set())
    assert s["nivel"] == "destaque"
    assert s["texto"] == "Copom hoje (09/12): mercado espera **manter**, com a Selic em 13,50%."


def test_sinal_copom_sem_dados():
    assert sinais.sinal_copom([], MEDIANAS, 13.75, HOJE, set()) is None
    assert sinais.sinal_copom(AGENDA, {}, 13.75, HOJE, set()) is None


def test_sinal_trajetoria():
    s = sinais.sinal_trajetoria(MEDIANAS, 13.75, HOJE, set())
    assert s == {"nivel": "info", "tipo": "selic",
                 "texto": "Mercado espera **1,75 p.p. de cortes** até o fim de 2027 (13,75% → 12,00%) e 3,25 p.p. de cortes até R6/2028 (10,50%)."}


def test_sinal_trajetoria_sem_ano_seguinte_e_sem_dados():
    s = sinais.sinal_trajetoria({"R7/2026": 14.0}, 13.75, HOJE, set())
    assert s["texto"] == "Mercado espera **0,25 p.p. de altas** até R7/2026 (13,75% → 14,00%)."
    assert sinais.sinal_trajetoria({}, 13.75, HOJE, set()) is None
```

- [ ] **Passo 2: rodar e ver falhar**

Comando: `python -m pytest tests/test_sinais.py -q`
Esperado: erro de coleta, com `ImportError: cannot import name 'sinais'`.

- [ ] **Passo 3: implementar a primeira parte de `pipeline/sinais.py`**

```python
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
```

- [ ] **Passo 4: rodar os testes**

Comando: `python -m pytest tests/test_sinais.py -q`
Esperado: 10 passed.

- [ ] **Passo 5: commit**

```bash
git add pipeline/sinais.py tests/test_sinais.py
git commit -m "feat(sinais): próximo Copom e trajetória esperada da Selic" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarefa 4: sinal de revisão de expectativa

**Arquivos:**
- Modificar: `pipeline/sinais.py` (acrescentar ao final)
- Modificar: `tests/test_sinais.py` (acrescentar ao final)

**Interfaces:**
- Usa: `semanal` no formato `focus.semanal` (Tarefa 1): `{indicador: {ano: [{"semana", "Mediana", ...}]}}`; `fmt_br`.
- Fornece: `sinais_revisao(semanal: dict, hoje: date) -> list[dict]` e as constantes `LIMITES`, `NOMES`, `SEMANAS_SEGUIDAS` e `JANELA_ACUMULADO`.

- [ ] **Passo 1: escrever os testes que falham**

Acrescente a `tests/test_sinais.py`:

```python
def sem(*medianas):
    return [{"semana": f"2026-{7 + i // 4:02d}-{1 + (i % 4) * 7:02d}", "Mediana": m, "Minimo": m, "Maximo": m,
             "numeroRespondentes": 100} for i, m in enumerate(medianas)]


def test_revisao_3_semanas_seguidas_dispara():
    r = sinais.sinais_revisao({"PIB Total": {"2026": sem(1.95, 1.93, 1.90, 1.88, 1.86)}}, HOJE)
    assert r == [{"nivel": "destaque", "tipo": "revisao",
                  "texto": "Expectativa de PIB 2026 **caiu 4 semanas seguidas** (1,95% → 1,86%)."}]


def test_revisao_exatamente_3_semanas():
    r = sinais.sinais_revisao({"IPCA": {"2027": sem(4.20, 4.20, 4.21, 4.22, 4.23)}}, HOJE)
    assert r[0]["texto"] == "Expectativa de IPCA 2027 **subiu 3 semanas seguidas** (4,20% → 4,23%)."


def test_revisao_semana_parada_interrompe_a_sequencia():
    assert sinais.sinais_revisao({"IPCA": {"2026": sem(4.90, 4.91, 4.92, 4.92, 4.93)}}, HOJE) == []


def test_revisao_acumulado_no_limite_dispara_e_abaixo_nao():
    no_limite = sinais.sinais_revisao({"Selic": {"2026": sem(13.75, 13.75, 13.50, 13.50, 13.50)}}, HOJE)
    assert no_limite[0]["texto"] == "Expectativa de Selic 2026 **caiu 0,25 p.p.** em 4 semanas (13,75% → 13,50%)."
    abaixo = sinais.sinais_revisao({"IPCA": {"2026": sem(4.80, 4.80, 4.99, 4.99, 4.99)}}, HOJE)
    assert abaixo == []  # 0,19 < 0,20 e sem sequência de 3


def test_revisao_cambio_em_reais_e_float_impreciso():
    r = sinais.sinais_revisao({"Câmbio": {"2026": sem(5.30, 5.30, 5.20, 5.20, 5.20)}}, HOJE)
    assert r[0]["texto"] == "Expectativa de Câmbio 2026 **caiu R$ 0,10** em 4 semanas (R$ 5,30 → R$ 5,20)."


def test_revisao_so_ano_atual_e_seguinte_e_poucas_semanas():
    semanal = {"IPCA": {"2028": sem(3.0, 3.1, 3.2, 3.3, 3.4), "2026": sem(4.9)}}
    assert sinais.sinais_revisao(semanal, HOJE) == []
    assert sinais.sinais_revisao({}, HOJE) == []
```

- [ ] **Passo 2: rodar e ver falhar**

Comando: `python -m pytest tests/test_sinais.py -q -k revisao`
Esperado: FAIL com `AttributeError: module 'pipeline.sinais' has no attribute 'sinais_revisao'`.

- [ ] **Passo 3: implementar**

Acrescente a `pipeline/sinais.py`:

```python
LIMITES = {"IPCA": 0.20, "PIB Total": 0.20, "Selic": 0.25, "Câmbio": 0.10}
NOMES = {"IPCA": "IPCA", "PIB Total": "PIB", "Selic": "Selic", "Câmbio": "Câmbio"}
SEMANAS_SEGUIDAS = 3
JANELA_ACUMULADO = 4


def _sequencia(valores: list[float]) -> tuple[int, int]:
    """(semanas seguidas na mesma direção terminando na última, direção +1/-1)."""
    seq, direcao = 0, 0
    for a, b in reversed(list(zip(valores, valores[1:]))):
        d = b - a
        s = 0 if abs(d) < EPS else (1 if d > 0 else -1)
        if s == 0 or (direcao and s != direcao):
            break
        direcao, seq = s, seq + 1
    return seq, direcao


def sinais_revisao(semanal: dict, hoje: date) -> list[dict]:
    saida = []
    for ind, limite in LIMITES.items():
        cambio = ind == "Câmbio"
        nivel = (lambda x: f"R$ {fmt_br(x)}") if cambio else (lambda x: f"{fmt_br(x)}%")
        passo = (lambda x: f"R$ {fmt_br(x)}") if cambio else (lambda x: f"{fmt_br(x)} p.p.")
        for ano in (str(hoje.year), str(hoje.year + 1)):
            v = [l["Mediana"] for l in semanal.get(ind, {}).get(ano, [])]
            if len(v) < 2:
                continue
            seq, direcao = _sequencia(v)
            acum = v[-1] - v[-1 - JANELA_ACUMULADO] if len(v) > JANELA_ACUMULADO else None
            if seq >= SEMANAS_SEGUIDAS:
                texto = (f"Expectativa de {NOMES[ind]} {ano} **{'subiu' if direcao > 0 else 'caiu'} "
                         f"{seq} semanas seguidas** ({nivel(v[-1 - seq])} → {nivel(v[-1])}).")
            elif acum is not None and abs(acum) >= limite - EPS:
                texto = (f"Expectativa de {NOMES[ind]} {ano} **{'subiu' if acum > 0 else 'caiu'} {passo(abs(acum))}** "
                         f"em {JANELA_ACUMULADO} semanas ({nivel(v[-1 - JANELA_ACUMULADO])} → {nivel(v[-1])}).")
            else:
                continue
            saida.append({"nivel": "destaque", "tipo": "revisao", "texto": texto})
    return saida
```

- [ ] **Passo 4: rodar os testes**

Comando: `python -m pytest tests/test_sinais.py -q`
Esperado: 16 passed.

- [ ] **Passo 5: commit**

```bash
git add pipeline/sinais.py tests/test_sinais.py
git commit -m "feat(sinais): revisão de expectativa por sequência ou acumulado" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarefa 5: sinais de juro real, câmbio e agenda próxima, e ordenação

**Arquivos:**
- Modificar: `pipeline/sinais.py` (acrescentar ao final)
- Modificar: `tests/test_sinais.py` (acrescentar ao final)

**Interfaces:**
- Fornece:
  - `sinal_juro_real(agenda: list[dict], medianas: dict[str, float], infl12: float | None, juro_hist: list[float], hoje: date) -> dict | None`
  - `sinal_cambio(usd_hoje: float | None, semanal: dict, hoje: date) -> dict | None`
  - `sinais_agenda(agenda: list[dict], hoje: date, fed_funds: float | None) -> list[dict]`
  - `ordenar(lista: list[dict]) -> list[dict]`

- [ ] **Passo 1: escrever os testes que falham**

Acrescente a `tests/test_sinais.py`:

```python
def test_juro_real_usa_reuniao_mais_perto_de_12_meses():
    hist = [x / 10 for x in range(100)]  # 0,0..9,9
    # R6/2027 (22/09/2027) é a reunião mais perto de 30/09/2027; 12,50 − 4,60 = 7,90, acima de 79 dos 100 valores.
    s = sinais.sinal_juro_real(AGENDA, MEDIANAS, 4.60, hist, HOJE)
    assert s == {"nivel": "info", "tipo": "juro_real",
                 "texto": "Juro real esperado para 12 meses: **7,9%** (Selic esperada 12,50% − IPCA esperado 4,60%). Maior que em 79% dos meses desde 2000."}


def test_juro_real_destaque_nos_extremos():
    assert sinais.sinal_juro_real(AGENDA, MEDIANAS, 4.60, [1.0] * 9 + [9.0], HOJE)["nivel"] == "destaque"   # 90%
    assert sinais.sinal_juro_real(AGENDA, MEDIANAS, 4.60, [1.0] * 8 + [9.0] * 2, HOJE)["nivel"] == "info"    # 80%
    assert sinais.sinal_juro_real(AGENDA, MEDIANAS, 4.60, [9.0] * 10, HOJE)["nivel"] == "destaque"          # 0%
    assert sinais.sinal_juro_real(AGENDA, MEDIANAS, 4.60, [1.0] + [9.0] * 9, HOJE)["nivel"] == "destaque"   # 10%


def test_juro_real_sem_dados():
    assert sinais.sinal_juro_real(AGENDA, MEDIANAS, None, [1.0], HOJE) is None
    assert sinais.sinal_juro_real(AGENDA, MEDIANAS, 4.65, [], HOJE) is None
    assert sinais.sinal_juro_real([], MEDIANAS, 4.65, [1.0], HOJE) is None


def test_cambio():
    semanal = {"Câmbio": {"2026": sem(5.25, 5.20), "2027": sem(5.2769)}}
    s = sinais.sinal_cambio(5.36, semanal, HOJE)
    assert s == {"nivel": "info", "tipo": "cambio",
                 "texto": "Dólar hoje R$ 5,36; mercado espera **R$ 5,20** no fim de 2026 (-3,0%) e R$ 5,28 no fim de 2027."}
    assert sinais.sinal_cambio(None, semanal, HOJE) is None
    assert sinais.sinal_cambio(5.36, {}, HOJE) is None


def test_agenda_proxima_14_dias_sem_copom():
    agenda = [
        {"data": "2026-09-29", "tipo": "ipca", "titulo": "IPCA de agosto"},
        {"data": "2026-10-09", "tipo": "ipca", "titulo": "IPCA de setembro"},
        {"data": "2026-10-14", "tipo": "fomc", "titulo": "FOMC"},
        {"data": "2026-10-15", "tipo": "fomc", "titulo": "FOMC"},
        {"data": "2026-10-01", "tipo": "copom", "titulo": "Copom", "reuniao": "R7/2026"},
    ]
    r = sinais.sinais_agenda(agenda, HOJE, 3.88)
    assert r == [
        {"nivel": "info", "tipo": "ipca", "data": "2026-10-09", "texto": "IPCA de setembro em 9 dias (09/10)."},
        {"nivel": "info", "tipo": "fomc", "data": "2026-10-14", "texto": "FOMC em 14 dias (14/10). Fed Funds hoje em 3,88%."},
    ]
    assert sinais.sinais_agenda(agenda[2:3], HOJE, None)[0]["texto"] == "FOMC em 14 dias (14/10)."


def test_ordenar_destaque_primeiro_depois_data():
    lista = [{"nivel": "info", "tipo": "a"}, {"nivel": "info", "tipo": "b", "data": "2026-10-09"},
             {"nivel": "destaque", "tipo": "c"}, {"nivel": "destaque", "tipo": "d", "data": "2026-11-04"}]
    assert [s["tipo"] for s in sinais.ordenar(lista)] == ["d", "c", "b", "a"]
```

- [ ] **Passo 2: rodar e ver falhar**

Comando: `python -m pytest tests/test_sinais.py -q`
Esperado: FAIL com `AttributeError` para `sinal_juro_real`, `sinal_cambio`, `sinais_agenda` e `ordenar`.

- [ ] **Passo 3: implementar**

Acrescente a `pipeline/sinais.py` (e troque o import do topo para `from datetime import date, timedelta`):

```python
DIAS_AGENDA = 14
PERCENTIL_EXTREMO = 10


def sinal_juro_real(agenda: list[dict], medianas: dict[str, float], infl12: float | None,
                    juro_hist: list[float], hoje: date) -> dict | None:
    if infl12 is None or not juro_hist:
        return None
    datas = {a["reuniao"]: date.fromisoformat(a["data"]) for a in agenda
             if a["tipo"] == "copom" and a["reuniao"] in medianas}
    if not datas:
        return None
    alvo = hoje + timedelta(days=365)
    r = min(sorted(datas), key=lambda k: abs((datas[k] - alvo).days))
    jr = medianas[r] - infl12
    pct = round(100 * sum(h < jr for h in juro_hist) / len(juro_hist))
    extremo = pct >= 100 - PERCENTIL_EXTREMO or pct <= PERCENTIL_EXTREMO
    return {"nivel": "destaque" if extremo else "info", "tipo": "juro_real",
            "texto": (f"Juro real esperado para 12 meses: **{fmt_br(jr, 1)}%** (Selic esperada {fmt_br(medianas[r])}% − "
                      f"IPCA esperado {fmt_br(infl12)}%). Maior que em {pct}% dos meses desde 2000.")}


def sinal_cambio(usd_hoje: float | None, semanal: dict, hoje: date) -> dict | None:
    anos = semanal.get("Câmbio", {})
    atual, seguinte = anos.get(str(hoje.year)), anos.get(str(hoje.year + 1))
    if usd_hoje is None or not atual:
        return None
    m = atual[-1]["Mediana"]
    texto = (f"Dólar hoje R$ {fmt_br(usd_hoje)}; mercado espera **R$ {fmt_br(m)}** no fim de {hoje.year} "
             f"({fmt_br((m / usd_hoje - 1) * 100, 1, sinal=True)}%)")
    if seguinte:
        texto += f" e R$ {fmt_br(seguinte[-1]['Mediana'])} no fim de {hoje.year + 1}"
    return {"nivel": "info", "tipo": "cambio", "texto": texto + "."}


def sinais_agenda(agenda: list[dict], hoje: date, fed_funds: float | None) -> list[dict]:
    """FOMC e IPCA nos próximos 14 dias; o Copom tem sinal próprio."""
    saida = []
    for a in agenda:
        if a["tipo"] == "copom":
            continue
        dias = (date.fromisoformat(a["data"]) - hoje).days
        if not 0 <= dias <= DIAS_AGENDA:
            continue
        texto = f"{a['titulo']} {quando(dias)} ({dm(a['data'])})."
        if a["tipo"] == "fomc" and fed_funds is not None:
            texto += f" Fed Funds hoje em {fmt_br(fed_funds)}%."
        saida.append({"nivel": "info", "tipo": a["tipo"], "data": a["data"], "texto": texto})
    return saida


def ordenar(lista: list[dict]) -> list[dict]:
    """Destaques primeiro; dentro de cada nível, pela data do evento (sem data vai para o fim)."""
    return sorted(lista, key=lambda s: (s["nivel"] != "destaque", s.get("data") or "9999-12-31"))
```

- [ ] **Passo 4: rodar os testes**

Comando: `python -m pytest tests/test_sinais.py -q`
Esperado: 22 passed.

- [ ] **Passo 5: commit**

```bash
git add pipeline/sinais.py tests/test_sinais.py
git commit -m "feat(sinais): juro real esperado, câmbio, agenda próxima e ordenação" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarefa 6: bloco `previsoes` no export e integração no `atualizar.py`

**Arquivos:**
- Modificar: `pipeline/exportar.py` (nova função `previsoes`; `montar` ganha o parâmetro `previsoes`)
- Modificar: `atualizar.py` (imports e trecho entre `eventos = ...` e `dados = exportar.montar(...)`)
- Criar: `tests/test_previsoes.py`
- Modificar: `tests/test_exportar.py:29` (conjunto de chaves)
- Modificar: `tests/test_atualizar.py` (fixture que substitui o Focus e cópia do `agenda.json`)

**Interfaces:**
- Usa: `focus.semanal`, `focus.obter`, `focus.baixar`, `agenda.carregar` e todas as funções de `sinais` das Tarefas 3 a 5.
- Fornece:
  - `exportar.previsoes(bruto: dict | None, agenda_: list[dict], selic_hoje: float | None, usd_hoje: float | None, fed_funds: float | None, juro_hist: list[float], hoje: date, avisos: list[str]) -> dict`
  - `exportar.montar(..., gerado_em=None, previsoes: dict | None = None)`: o dict devolvido ganha a chave `"previsoes"`.
  - Forma do bloco, lida pelo JS na Tarefa 7:

```
{"focus_data": str | None, "respondentes": int | None,
 "sinais": [{"nivel", "tipo", "texto", "data"?}],
 "agenda": [{"data", "tipo", "titulo", "reuniao"?, "espera"?: {"mediana", "dif"}, "contexto"?}],   # só futuras
 "trajetorias": {"selic"|"ipca"|"cambio"|"pib": {"nome", "unidade", "serie_hist": str | None,
                 "proj": [[data_iso, mediana, minimo, maximo, respondentes, rotulo]]}}}          # {} sem Focus
```

- [ ] **Passo 1: escrever os testes que falham**

`tests/test_previsoes.py`:

```python
import json
from datetime import date
from pathlib import Path

from pipeline import exportar

HOJE = date(2026, 9, 30)
FIX = Path(__file__).parent / "fixtures" / "focus_bruto.json"
AGENDA = [
    {"data": "2026-09-16", "tipo": "copom", "titulo": "Copom", "reuniao": "R6/2026"},
    {"data": "2026-10-09", "tipo": "ipca", "titulo": "IPCA de setembro"},
    {"data": "2026-10-28", "tipo": "fomc", "titulo": "FOMC"},
    {"data": "2026-11-04", "tipo": "copom", "titulo": "Copom", "reuniao": "R7/2026"},
    {"data": "2026-12-09", "tipo": "copom", "titulo": "Copom", "reuniao": "R8/2026"},
]


def linha(reuniao, mediana):
    return {"Data": "2026-09-25", "Reuniao": reuniao, "Mediana": mediana, "Minimo": mediana - 0.5,
            "Maximo": mediana + 0.5, "numeroRespondentes": 130, "baseCalculo": 0}


def anual(ind, ref, data, mediana, n=144):
    return {"Indicador": ind, "Data": data, "DataReferencia": ref, "Mediana": mediana,
            "Minimo": mediana - 1, "Maximo": mediana + 1, "numeroRespondentes": n}


BRUTO = {
    "data_pesquisa": "2026-09-25",
    "selic": [linha("R6/2026", 14.0), linha("R7/2026", 13.5), linha("R8/2026", 13.5), linha("R1/2027", 13.25)],
    "anuais": [anual("IPCA", "2026", "2026-09-25", 4.99), anual("IPCA", "2027", "2026-09-25", 4.31),
               anual("Câmbio", "2026", "2026-09-25", 5.2, 110), anual("PIB Total", "2026", "2026-09-25", 1.86),
               anual("Selic", "2026", "2026-09-25", 13.5)],
    "infl12": {"Mediana": 4.65},
}


def montar(**troca):
    args = dict(bruto=BRUTO, agenda_=AGENDA, selic_hoje=13.75, usd_hoje=5.36, fed_funds=3.88,
                juro_hist=[float(x) for x in range(20)], hoje=HOJE, avisos=[])
    args.update(troca)
    return exportar.previsoes(**args), args["avisos"]


def test_forma_do_bloco():
    p, avisos = montar()
    assert set(p) == {"focus_data", "respondentes", "sinais", "agenda", "trajetorias"}
    assert p["focus_data"] == "2026-09-25" and p["respondentes"] == 144
    assert set(p["trajetorias"]) == {"selic", "ipca", "cambio", "pib"}
    assert p["trajetorias"]["selic"]["serie_hist"] == "selic_meta" and p["trajetorias"]["pib"]["serie_hist"] is None
    assert [(x[0], x[1], x[4], x[5]) for x in p["trajetorias"]["ipca"]["proj"]] == [("2026-12-31", 4.99, 144, "2026"), ("2027-12-31", 4.31, 144, "2027")]
    json.dumps(p, allow_nan=False)


def test_reuniao_passada_fica_fora_e_decisoes_contam_da_selic_atual():
    p, avisos = montar()
    assert [x[5] for x in p["trajetorias"]["selic"]["proj"]] == ["R7/2026", "R8/2026"]
    copom = {a["reuniao"]: a for a in p["agenda"] if a["tipo"] == "copom"}
    assert "R6/2026" not in copom                               # só eventos futuros
    assert copom["R7/2026"]["espera"] == {"mediana": 13.5, "dif": -0.25}
    assert copom["R8/2026"]["espera"] == {"mediana": 13.5, "dif": 0.0}
    fomc = next(a for a in p["agenda"] if a["tipo"] == "fomc")
    assert fomc["contexto"] == "Fed Funds hoje 3,88%"
    # R1/2027 está no Focus e não tem data: um único aviso, que não cita a R6/2026 passada
    assert avisos == ["Focus tem 1 reunião do Copom sem data em agenda.json (R1/2027); fica fora do gráfico"]


def test_sem_agenda_selic_usa_projecao_anual_e_nao_avisa_por_reuniao():
    p, avisos = montar(agenda_=[])
    assert p["trajetorias"]["selic"]["proj"] == [["2026-12-31", 13.5, 12.5, 14.5, 144, "2026"]]
    assert avisos == []
    assert not any(s["tipo"] == "copom" for s in p["sinais"])


def test_sinais_presentes_e_ordenados():
    p, _ = montar()
    tipos = [s["tipo"] for s in p["sinais"]]
    assert {"copom", "selic", "juro_real", "cambio", "ipca"} <= set(tipos)
    niveis = [s["nivel"] for s in p["sinais"]]
    assert niveis == sorted(niveis, key=lambda n: n != "destaque")


def test_series_base_ausentes_nao_quebram():
    p, _ = montar(selic_hoje=None, usd_hoje=None, fed_funds=None, juro_hist=[])
    tipos = {s["tipo"] for s in p["sinais"]}
    assert not tipos & {"copom", "selic", "cambio", "juro_real"}
    assert "ipca" in tipos
    assert all("espera" not in a for a in p["agenda"])


def test_sem_focus_mantem_agenda():
    p, _ = montar(bruto=None)
    assert p["focus_data"] is None and p["trajetorias"] == {}
    assert [a["data"] for a in p["agenda"]] == ["2026-10-09", "2026-10-28", "2026-11-04", "2026-12-09"]
    assert [s["tipo"] for s in p["sinais"]] == ["ipca"]


def test_com_resposta_real_gravada():
    bruto = json.loads(FIX.read_text(encoding="utf-8"))
    raiz = Path(__file__).parent.parent
    agenda_ = json.loads((raiz / "agenda.json").read_text(encoding="utf-8"))
    p, avisos = montar(bruto=bruto, agenda_=agenda_)
    assert p["trajetorias"]["selic"]["proj"] and p["sinais"]
    json.dumps(p, allow_nan=False)
```

Em `tests/test_exportar.py`, troque a asserção de `test_montar_formato` por:

```python
    assert set(d) == {"gerado_em", "series", "correlacao", "arestas", "eventos", "avisos", "previsoes"}
    assert d["previsoes"] is None
```

Em `tests/test_atualizar.py`, acrescente logo depois de `RAIZ = ...`:

```python
import pytest
from pipeline import focus


@pytest.fixture(autouse=True)
def sem_focus_na_rede(monkeypatch):
    """Os testes nunca chamam o Olinda de verdade."""
    def falha(hoje):
        raise ConnectionError("rede desligada no teste")
    monkeypatch.setattr(focus, "baixar", falha)
```

E acrescente ao final do arquivo:

```python
def test_main_gera_bloco_previsoes(tmp_path, monkeypatch):
    bruto = json.loads((RAIZ / "tests" / "fixtures" / "focus_bruto.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(cache_mod.fontes, "baixar", serie_fake)
    monkeypatch.setattr(focus, "baixar", lambda hoje: bruto)
    shutil.copy(RAIZ / "eventos.json", tmp_path / "eventos.json")
    shutil.copy(RAIZ / "agenda.json", tmp_path / "agenda.json")
    assert atualizar.main(["--pasta", str(tmp_path)]) == 0
    d = json.loads((tmp_path / "dados.json").read_text(encoding="utf-8"))
    assert d["previsoes"]["focus_data"] == bruto["data_pesquisa"]
    assert (tmp_path / "cache" / "focus.json").exists()
    # Offline: o Focus vem do cache, com aviso próprio e fora do resumo "Modo offline" das séries.
    assert atualizar.main(["--pasta", str(tmp_path), "--offline"]) == 0
    d = json.loads((tmp_path / "dados.json").read_text(encoding="utf-8"))
    assert d["previsoes"]["focus_data"] == bruto["data_pesquisa"]
    assert any(a.startswith("Focus: lido do cache de") for a in d["avisos"])


def test_main_sem_focus_e_sem_cache_continua(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod.fontes, "baixar", serie_fake)
    shutil.copy(RAIZ / "eventos.json", tmp_path / "eventos.json")
    assert atualizar.main(["--pasta", str(tmp_path)]) == 0
    d = json.loads((tmp_path / "dados.json").read_text(encoding="utf-8"))
    assert d["previsoes"]["focus_data"] is None
    assert any(a.startswith("Focus: falha ao baixar") for a in d["avisos"])
    assert "agenda.json não encontrado; aba Previsões sem agenda" in d["avisos"]
```

- [ ] **Passo 2: rodar e ver falhar**

Comando: `python -m pytest tests/test_previsoes.py tests/test_exportar.py tests/test_atualizar.py -q`
Esperado: FAIL com `AttributeError: module 'pipeline.exportar' has no attribute 'previsoes'`, a asserção de chaves em `test_montar_formato` falhando e os dois testes novos do `atualizar` falhando por `KeyError: 'previsoes'`.

- [ ] **Passo 3: implementar `exportar.previsoes` e a chave em `montar`**

Em `pipeline/exportar.py`, troque `from datetime import datetime` por `from datetime import date, datetime` e acrescente, junto dos imports de `pipeline`:

```python
from pipeline import focus, sinais
```

Troque a assinatura e o retorno de `montar`:

```python
def montar(metas: dict[str, Serie], diarias: dict[str, pd.Series], mensais: dict[str, pd.Series],
           status: dict[str, str], avisos: list[str], correl: dict, eventos: list[dict],
           gerado_em: datetime | None = None, previsoes: dict | None = None) -> dict:
```

e acrescente `"previsoes": previsoes,` ao dict devolvido, depois de `"avisos": list(avisos),`. Atenção: `avisos` é copiado nesse ponto, então o `atualizar.py` precisa chamar `previsoes()` **antes** de `montar()` (Passo 4).

Acrescente ao final de `pipeline/exportar.py`:

```python
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


def previsoes(bruto: dict | None, agenda_: list[dict], selic_hoje: float | None, usd_hoje: float | None,
              fed_funds: float | None, juro_hist: list[float], hoje: date, avisos: list[str]) -> dict:
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

    if selic_hoje is not None:
        decisoes = sinais.decisoes_esperadas(medianas, selic_hoje, passadas)
        for a in futura:
            if a["tipo"] == "copom" and a["reuniao"] in decisoes:
                a["espera"] = decisoes[a["reuniao"]]
        lista += [s for s in (sinais.sinal_copom(futura, medianas, selic_hoje, hoje, passadas),
                              sinais.sinal_trajetoria(medianas, selic_hoje, hoje, passadas)) if s]
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

    ipca_ano = semanal.get("IPCA", {}).get(str(hoje.year)) or []
    return {"focus_data": bruto.get("data_pesquisa"),
            "respondentes": ipca_ano[-1]["numeroRespondentes"] if ipca_ano else None,
            "sinais": sinais.ordenar(lista), "agenda": futura, "trajetorias": trajetorias}
```

- [ ] **Passo 4: integrar no `atualizar.py`**

Imports: troque a linha `from pipeline import correlacao, exportar, fontes, transformar` por

```python
from datetime import date

from pipeline import agenda, correlacao, exportar, focus, fontes, transformar
```

(o `from datetime import date` fica junto dos outros imports da biblioteca padrão, logo depois de `import sys`).

Depois do bloco `if "selic_meta" in brutas: eventos = eventos + ciclos_copom(...)` e antes de `metas = {...}`, insira:

```python
    hoje = date.today()
    bruto_focus, aviso_focus = focus.obter(pasta / "cache" / "focus.json", args.offline, hoje, baixar=focus.baixar)
    if aviso_focus:
        avisos.append(aviso_focus)
    agenda_ = agenda.carregar(pasta / "agenda.json", avisos)

    def ultimo(id: str) -> float | None:
        return float(brutas[id].dropna().iloc[-1]) if id in brutas and not brutas[id].dropna().empty else None

    jr = mensais.get("juro_real")
    juro_hist = [] if jr is None else [float(v) for i, v in jr.dropna().items() if str(i)[:4] >= "2000"]
    prev = exportar.previsoes(bruto_focus, agenda_, ultimo("selic_meta"), ultimo("usd_brl"), ultimo("fed_funds"),
                              juro_hist, hoje, avisos)
```

Troque a chamada de `montar` por:

```python
    dados = exportar.montar(metas, diarias, mensais, status, avisos, correl, eventos, previsoes=prev)
```

A chamada a `focus.obter` fica **depois** do bloco `if args.offline:`, que agrupa os avisos com o texto "modo offline". O aviso do Focus usa "(offline)" justamente para não entrar nessa contagem.

- [ ] **Passo 5: rodar a suíte inteira**

Comando: `python -m pytest -q`
Esperado: todos passam. Nenhum teste chama a rede: o fixture `sem_focus_na_rede` cobre o `test_atualizar.py`.

- [ ] **Passo 6: rodar com dados reais**

Comando: `python atualizar.py`
Esperado: a saída termina sem traceback. Se aparecer um aviso "Focus tem N reuniões do Copom sem data em agenda.json (R1/2028, …)", é o esperado enquanto o BCB não publicar o calendário de 2028. Confira o bloco:

```bash
python -c "import json; p = json.load(open('dados.json', encoding='utf-8'))['previsoes']; print(p['focus_data'], p['respondentes']); [print(s['nivel'], s['texto']) for s in p['sinais']]"
```

Esperado: data da pesquisa recente e de 5 a 12 sinais em português, com vírgula decimal.

- [ ] **Passo 7: commit**

`dados.json` e `dados.js` estão no `.gitignore`; confirme com `git status --short`.

```bash
git add pipeline/exportar.py atualizar.py tests/test_previsoes.py tests/test_exportar.py tests/test_atualizar.py
git commit -m "feat(previsoes): bloco previsoes no dados.json com sinais, agenda e trajetórias" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarefa 7: aba Previsões no painel

**Arquivos:**
- Modificar: `painel.html` (botão da aba e `<section>`)
- Modificar: `painel.css` (estilos novos no final)
- Modificar: `painel.js` (estado, funções da aba, registro em `RENDER`)

**Interfaces:**
- Usa: `D.previsoes` no formato da Tarefa 6; os helpers existentes `$`, `$$`, `el`, `fmt`, `fmtData`, `cssVar`, `corGrupo`, `corCat`, `grafico`, `tooltipBase`, `eixoBase`, `textoBase`, `pontos`, `anosAtras` e `estado`; o mecanismo de abas (`RENDER[nome]`, `data-aba`).
- Fornece: `RENDER.previsoes = renderPrevisoes`.

- [ ] **Passo 1: HTML**

Em `painel.html`, logo depois do botão da aba Séries (`<button role="tab" ... data-aba="series" ...>Séries</button>`), insira:

```html
  <button role="tab" type="button" data-aba="previsoes" aria-selected="false">Previsões</button>
```

Logo depois do `</section>` de `aba-series`, insira:

```html
  <section id="aba-previsoes" class="aba" role="tabpanel" hidden>
    <div class="prev-cab">
      <h2>O que o mercado espera</h2>
      <span id="focus-info" class="muted"></span>
    </div>
    <div id="prev-vazio" class="card muted" hidden>Previsões indisponíveis: rode o Abrir Painel.bat com internet para baixar o Boletim Focus.</div>
    <div id="sinais" class="sinais"></div>
    <div class="grade-prev">
      <div id="card-traj" class="card">
        <div class="controles">
          <div id="seg-traj" class="segmentos" role="group" aria-label="Indicador"></div>
          <span id="leg-traj" class="hint"></span>
        </div>
        <div id="chart-traj" class="chart" style="height:400px"></div>
        <p class="legenda-faixa muted">Linha contínua: histórico. Tracejada: mediana do Focus. Faixa: menor e maior projeção entre as instituições.</p>
      </div>
      <div class="card">
        <h3>Agenda</h3>
        <table class="agenda"><tbody id="agenda"></tbody></table>
        <p id="agenda-vazia" class="muted" hidden>Sem eventos futuros em agenda.json.</p>
      </div>
    </div>
  </section>
```

- [ ] **Passo 2: CSS**

Acrescente ao final de `painel.css`:

```css
/* Aba Previsões */
.prev-cab { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.prev-cab h2 { font-size: 16px; margin: 0; font-weight: 600; }
.sinais { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr)); gap: 10px; margin-bottom: 14px; }
.sinal { background: var(--card); border-radius: 10px; padding: 10px 14px 10px 12px; box-shadow: var(--sombra); border-left: 3px solid var(--border-solid); display: flex; gap: 10px; align-items: flex-start; font-size: 13px; line-height: 1.45; }
.sinal.destaque { border-left-color: #fab219; }
.sinal-tag { flex: none; font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); background: color-mix(in srgb, var(--muted) 14%, transparent); border-radius: 4px; padding: 2px 6px; margin-top: 2px; }
.sinal.destaque .sinal-tag { color: #b77f00; background: color-mix(in srgb, #fab219 16%, transparent); }
:root[data-theme="dark"] .sinal.destaque .sinal-tag { color: #fab219; }
.sinal strong { font-weight: 600; }
.grade-prev { display: grid; grid-template-columns: minmax(0, 2fr) minmax(300px, 1fr); gap: 12px; align-items: start; }
@media (max-width: 900px) { .grade-prev { grid-template-columns: 1fr; } }
.grade-prev .card h3 { margin: 2px 4px 8px; font-size: 14px; font-weight: 600; }
.agenda { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
.agenda td { padding: 7px 4px; border-top: 1px solid var(--border-solid); vertical-align: top; }
.agenda tr:first-child td { border-top: 0; }
.agenda .ag-data { white-space: nowrap; font-weight: 600; width: 1%; }
.agenda .ag-dias { white-space: nowrap; text-align: right; color: var(--muted); width: 1%; }
.agenda .ag-tipo { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; background: var(--cor); }
.agenda .ag-sub { color: var(--text-2); font-size: 12px; }
```

- [ ] **Passo 3: JS, estado e registro**

Em `painel.js`, dentro do objeto `estado`, acrescente depois de `busca: '',`:

```js
    traj: 'selic',
```

Logo antes da linha `  // ---------- aba Séries ----------`, insira o bloco completo:

```js
  // ---------- aba Previsões ----------
  const TRAJ = [['selic', 'Selic'], ['ipca', 'IPCA 12m'], ['cambio', 'Dólar'], ['pib', 'PIB']];
  const COR_TRAJ = { selic: 'juros', ipca: 'inflacao', cambio: 'cambio', pib: 'macro' };
  const TAG_SINAL = { copom: 'Copom', selic: 'Selic', revisao: 'Revisão', juro_real: 'Juro real', cambio: 'Câmbio', fomc: 'Agenda', ipca: 'Agenda' };
  const COR_AGENDA = { copom: 'copom', fomc: 'fomc', ipca: 'plano' };

  // "**x**" vira <strong>, sem innerHTML.
  function textoRico(texto) {
    const s = el('span');
    texto.split('**').forEach((parte, i) => s.append(i % 2 ? el('strong', { text: parte }) : document.createTextNode(parte)));
    return s;
  }

  function renderPrevisoes() {
    const P = D.previsoes || null;
    const hoje = D.gerado_em.slice(0, 10);
    const semFocus = !P || !P.focus_data;
    $('#prev-vazio').hidden = !semFocus;
    $('#focus-info').textContent = semFocus ? '' : `Boletim Focus de ${fmtData(P.focus_data)}` + (P.respondentes ? ` · ${P.respondentes} instituições` : '');
    $('#sinais').replaceChildren(...((P && P.sinais) || []).map((s) =>
      el('div', { class: 'sinal ' + s.nivel }, el('span', { class: 'sinal-tag', text: TAG_SINAL[s.tipo] || s.tipo }), textoRico(s.texto))));
    renderAgenda((P && P.agenda) || [], hoje);
    $('#card-traj').hidden = semFocus;
    if (!semFocus) renderTrajetoria(P.trajetorias, hoje);
  }

  function renderAgenda(agenda, hoje) {
    const prox = agenda.filter((a) => a.data >= hoje).slice(0, 8);
    $('#agenda-vazia').hidden = prox.length > 0;
    $('#agenda').replaceChildren(...prox.map((a) => {
      const dias = Math.round((Date.parse(a.data) - Date.parse(hoje)) / 864e5);
      let sub = null;
      if (a.espera) {
        const d = a.espera.dif;
        const v = d === 0 ? 'manter' : (d < 0 ? `cortar ${fmt(-d)}` : `subir ${fmt(d)}`);
        sub = el('div', { class: 'ag-sub', text: `${a.reuniao} · mercado espera ${v} → ${fmt(a.espera.mediana)}%` });
      } else if (a.contexto) sub = el('div', { class: 'ag-sub', text: a.contexto });
      return el('tr', {},
        el('td', { class: 'ag-data', text: fmtData(a.data).slice(0, 5) }),
        el('td', {}, el('span', { class: 'ag-tipo', style: `--cor:${corCat(COR_AGENDA[a.tipo])}` }), a.titulo, sub),
        el('td', { class: 'ag-dias', text: dias === 0 ? 'hoje' : `em ${dias} d` }));
    }));
  }

  function renderTrajetoria(trajetorias, hoje) {
    const seg = $('#seg-traj');
    if (!seg.children.length) {
      for (const [k, nome] of TRAJ) {
        seg.append(el('button', { type: 'button', class: 'seg', 'data-traj': k, text: nome, onclick: () => { estado.traj = k; renderPrevisoes(); } }));
      }
    }
    $$('[data-traj]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.traj === estado.traj)));
    const t = trajetorias[estado.traj];
    const c = grafico('chart-traj');
    if (!t || !t.proj.length) {
      $('#leg-traj').textContent = '';
      c.setOption({ title: { text: 'Sem projeções do Focus para este indicador', left: 'center', top: 'middle', textStyle: { color: cssVar('--muted'), fontWeight: 400, fontSize: 14 } } }, true);
      return;
    }
    const cor = corGrupo(COR_TRAJ[estado.traj]);
    const inicio = anosAtras(hoje, 3);
    const hist = t.serie_hist && D.series[t.serie_hist] ? pontos(t.serie_hist).filter((p) => p[0] >= inicio && p[1] != null) : [];
    const ultimo = hist.length ? hist[hist.length - 1] : null;
    // A projeção parte do último ponto real para a linha não ter buraco.
    const proj = (ultimo ? [[ultimo[0], ultimo[1], ultimo[1], ultimo[1], null, 'hoje']] : []).concat(t.proj);
    const degrau = estado.traj === 'selic' && t.proj[0] && t.proj[0][5].startsWith('R') ? 'end' : false;
    $('#leg-traj').textContent = `${t.nome} · ${t.unidade}` + (t.serie_hist ? '' : ' · sem histórico no painel, só projeções');
    c.setOption({
      textStyle: textoBase(), animation: false,
      grid: { left: 52, right: 20, top: 24, bottom: 30 },
      tooltip: Object.assign(tooltipBase(), {
        trigger: 'axis',
        formatter: (ps) => {
          const p = ps.find((q) => q.seriesId === 'proj' && q.data[4] != null) || ps.find((q) => q.seriesId === 'hist');
          if (!p) return '';
          const d = p.data;
          const caixa = el('div', { class: 'tt' }, el('div', { class: 'tt-titulo', text: p.seriesId === 'proj' ? `${d[5]} · ${fmtData(d[0])}` : fmtData(String(d[0]).slice(0, 10)) }),
            el('div', {}, el('strong', { text: `${fmt(d[1])} ${t.unidade}` }), el('span', { class: 'tt-nome', text: p.seriesId === 'proj' ? ' mediana' : '' })));
          if (p.seriesId === 'proj') caixa.append(el('div', { class: 'tt-nome', text: `Faixa ${fmt(d[2])} a ${fmt(d[3])} · ${d[4]} respostas` }));
          return caixa;
        },
      }),
      xAxis: Object.assign({ type: 'time' }, eixoBase(), { splitLine: { show: false } }),
      yAxis: Object.assign({ type: 'value', scale: true }, eixoBase(), { axisLine: { show: false }, axisLabel: { color: cssVar('--muted'), fontSize: 11, formatter: (v) => v.toLocaleString('pt-BR') } }),
      series: [
        { id: 'hist', type: 'line', data: hist, showSymbol: false, sampling: 'lttb', lineStyle: { width: 2, color: cor }, itemStyle: { color: cor },
          markLine: ultimo ? { symbol: 'none', silent: true, label: { formatter: 'hoje', color: cssVar('--muted'), fontSize: 11 }, lineStyle: { color: cssVar('--muted'), type: 'dotted' }, data: [{ xAxis: ultimo[0] }] } : undefined },
        // Faixa: base invisível no mínimo + área com a diferença até o máximo.
        { id: 'faixa-base', type: 'line', data: proj.map((p) => [p[0], p[2]]), stack: 'faixa', step: degrau, lineStyle: { opacity: 0 }, showSymbol: false, silent: true, tooltip: { show: false } },
        { id: 'faixa', type: 'line', data: proj.map((p) => [p[0], p[3] - p[2]]), stack: 'faixa', step: degrau, lineStyle: { opacity: 0 }, showSymbol: false, silent: true, areaStyle: { color: cor, opacity: 0.16 }, tooltip: { show: false } },
        { id: 'proj', type: 'line', data: proj, step: degrau, showSymbol: true, symbolSize: 6, lineStyle: { width: 2, type: 'dashed', color: cor }, itemStyle: { color: cor } },
      ],
    }, true);
  }
  RENDER.previsoes = renderPrevisoes;
```

- [ ] **Passo 4: verificar no navegador**

Suba o servidor com `python -m http.server 8765` e abra `http://localhost:8765/painel.html`. Confira, com o console aberto:

1. A aba "Previsões" é a segunda e abre sem erros no console.
2. O cabeçalho mostra "Boletim Focus de DD/MM/AAAA · N instituições".
3. Os cartões aparecem com os destaques primeiro (borda âmbar), números com vírgula e partes em negrito.
4. Os quatro botões trocam o gráfico. A Selic aparece em degraus com um ponto por reunião; IPCA e Dólar mostram o histórico de 3 anos mais a projeção tracejada com a faixa; o PIB mostra só projeções, com a legenda "sem histórico no painel".
5. O tooltip do gráfico mostra mediana, faixa e respostas; os eixos usam vírgula decimal.
6. A agenda mostra 8 linhas no máximo, só datas de hoje em diante, com "mercado espera …" nos Copom e "Fed Funds hoje …" nos FOMC.
7. O botão de tema (claro/escuro) redesenha a aba sem perder a trajetória escolhida.
8. Com a janela em 400 px de largura: um cartão por linha e a agenda abaixo do gráfico, sem rolagem horizontal.
9. **Sem Focus:** renomeie `cache/focus.json`, rode `python atualizar.py --offline` e recarregue. Aparece "Previsões indisponíveis…", o gráfico some e a agenda continua. Depois desfaça a renomeação e rode `python atualizar.py --offline` de novo.
10. As outras abas continuam funcionando.

- [ ] **Passo 5: rodar a suíte e commitar**

Comando: `python -m pytest -q`
Esperado: todos passam.

```bash
git add painel.html painel.css painel.js
git commit -m "feat(painel): aba Previsões com sinais, trajetória do Focus e agenda" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarefa 8: README

**Arquivos:**
- Modificar: `README.md`

- [ ] **Passo 1: documentar**

Em `README.md`, na lista de "Uso manual", troque a linha `- Fontes: BCB SGS, FRED, Yahoo Finance e IPEA. Nenhuma chave necessária.` por:

```markdown
- Fontes: BCB SGS, Boletim Focus (BCB), FRED, Yahoo Finance e IPEA. Nenhuma chave necessária.
```

E acrescente, antes de `## Testes`:

```markdown
## Aba Previsões

Mostra o consenso do mercado segundo o Boletim Focus do BCB (mediana,
menor e maior projeção entre as instituições), sinais calculados a partir
dele e a agenda de Copom, FOMC e IPCA. Os sinais descrevem fatos; não são
recomendação de investimento.

- O Focus é baixado junto com as séries e fica em `cache/focus.json`; se a
  consulta falhar, o painel usa o cache e avisa.
- `agenda.json` guarda as datas (dia do anúncio). Quando o BCB e o Fed
  publicarem o calendário de um novo ano, acrescente as linhas no mesmo
  formato: `{"data": "2028-01-26", "tipo": "copom", "titulo": "Copom", "reuniao": "R1/2028"}`.
  Tipos: `copom` (com `reuniao`), `fomc` e `ipca`. Enquanto faltar a data de
  uma reunião que o Focus já projeta, o painel avisa e deixa essa reunião
  fora do gráfico.
- Regras dos sinais e limites: `pipeline/sinais.py` e
  `docs/superpowers/specs/2026-09-30-previsoes-design.md`.
```

- [ ] **Passo 2: commit**

```bash
git add README.md
git commit -m "docs: README com a aba Previsões e o agenda.json" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
