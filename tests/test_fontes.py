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

    def get_falso(url, params=None, **kwargs):
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
    def get_falso(url, params=None, **kwargs):
        return RespostaFalsa([{"data": "24/09/2026", "valor": "15"}, {"data": "04/11/2026", "valor": "15"}])

    monkeypatch.setattr(fontes, "_get", get_falso)
    s = fontes.bcb("432", "d", hoje=date(2026, 9, 25))
    assert list(s.index) == [pd.Timestamp("2026-09-24")]


def test_bcb_mensal_sem_janela(monkeypatch):
    chamadas = []

    def get_falso(url, params=None, **kwargs):
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


class RespostaHttp:
    def __init__(self, texto, status=200):
        self.text = texto
        self.status_code = status

    def raise_for_status(self):
        pass

    def json(self):
        return json.loads(self.text)


def test_get_json_repete_quando_bcb_devolve_html_com_200(monkeypatch):
    # O firewall do BCB às vezes rejeita a chamada com uma página HTML e status 200.
    respostas = iter([RespostaHttp("<html>Requisição inválida!</html>"), RespostaHttp('[{"data": "01/01/2020", "valor": "4.5"}]')])
    monkeypatch.setattr(fontes.requests, "get", lambda *a, **k: next(respostas))
    monkeypatch.setattr(fontes.time, "sleep", lambda s: None)
    r = fontes._get("https://api.bcb.gov.br/x", json=True)
    assert r.json() == [{"data": "01/01/2020", "valor": "4.5"}]


def test_get_json_desiste_depois_das_tentativas(monkeypatch):
    monkeypatch.setattr(fontes.requests, "get", lambda *a, **k: RespostaHttp("<html>Requisição inválida!</html>"))
    monkeypatch.setattr(fontes.time, "sleep", lambda s: None)
    with pytest.raises(fontes.RespostaInvalida, match="Requisição inválida"):
        fontes._get("https://api.bcb.gov.br/x", json=True)


def test_parse_fred_api_trata_ponto_como_nulo():
    payload = {"observations": [{"date": "2026-09-28", "value": "3.88"}, {"date": "2026-09-29", "value": "."},
                                {"date": "2026-09-30", "value": "3.87"}]}
    s = fontes.parse_fred_api(payload)
    assert list(s.index) == [pd.Timestamp("2026-09-28"), pd.Timestamp("2026-09-30")]
    assert list(s) == [3.88, 3.87]
    assert fontes.parse_fred_api({}).empty


def test_fred_usa_a_api_quando_ha_chave(monkeypatch):
    chamadas = []

    def get_falso(url, params=None, timeout=None, json=False):
        chamadas.append((url, params, json))
        return RespostaHttp('{"observations": [{"date": "2026-09-30", "value": "3.87"}]}')

    monkeypatch.setenv("FRED_API_KEY", "chave-teste")
    monkeypatch.setattr(fontes, "_get", get_falso)
    s = fontes.fred("DFF")
    assert s.iloc[-1] == 3.87
    url, params, eh_json = chamadas[0]
    assert url == "https://api.stlouisfed.org/fred/series/observations" and eh_json is True
    assert params == {"series_id": "DFF", "api_key": "chave-teste", "file_type": "json"}


def test_fred_sem_chave_continua_no_csv(monkeypatch):
    chamadas = []
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(fontes, "_get", lambda url, params=None, **k: chamadas.append(url) or RespostaHttp("DATE,DFF\n2026-09-30,3.87\n"))
    assert fontes.fred("DFF").iloc[-1] == 3.87
    assert chamadas == ["https://fred.stlouisfed.org/graph/fredgraph.csv"]


def test_fred_nunca_expoe_a_chave_no_erro(monkeypatch):
    def get_falso(url, params=None, **k):
        raise fontes.requests.HTTPError(f"400 Client Error for url: {url}?api_key={params['api_key']}&series_id=DFF")

    monkeypatch.setenv("FRED_API_KEY", "chave-secreta-123")
    monkeypatch.setattr(fontes, "_get", get_falso)
    with pytest.raises(fontes.requests.RequestException) as erro:
        fontes.fred("DFF")
    assert "chave-secreta-123" not in str(erro.value) and "***" in str(erro.value)


def test_parse_yahoo_ajustado_prefere_adjclose():
    p = json.loads((FIX / "yahoo_fii_adj.json").read_text(encoding="utf-8"))
    s = fontes.parse_yahoo(p, ajustado=True)
    assert list(s.round(2)) == [102.9, 103.0, 104.5]
    assert s.index[0] == pd.Timestamp("2025-10-03")
    assert fontes.tem_adjclose(p)


def test_parse_yahoo_sem_ajuste_continua_usando_close():
    p = json.loads((FIX / "yahoo_fii_adj.json").read_text(encoding="utf-8"))
    assert list(fontes.parse_yahoo(p).round(2)) == [104.0, 103.0, 104.5]


def test_parse_yahoo_ajustado_cai_para_close_sem_adjclose():
    p = json.loads((FIX / "yahoo_fii_adj.json").read_text(encoding="utf-8"))
    del p["chart"]["result"][0]["indicators"]["adjclose"]
    assert list(fontes.parse_yahoo(p, ajustado=True).round(2)) == [104.0, 103.0, 104.5]
    assert not fontes.tem_adjclose(p)


def test_yahoo_ajustado_pede_13_meses_com_dividendos(monkeypatch):
    p = json.loads((FIX / "yahoo_fii_adj.json").read_text(encoding="utf-8"))
    pedidos = []

    class Resp:
        def json(self):
            return p

    def falso_get(url, params=None, timeout=None, json=False):
        pedidos.append((url, params, json))
        return Resp()

    monkeypatch.setattr(fontes, "_get", falso_get)
    s, com_proventos = fontes.yahoo_ajustado("KNCR11.SA")
    assert com_proventos and len(s) == 3
    url, params, como_json = pedidos[0]
    assert url.endswith("/v8/finance/chart/KNCR11.SA")
    assert params == {"range": "13mo", "interval": "1d", "events": "div"} and como_json


def test_yahoo_ajustado_404_devolve_vazia(monkeypatch):
    monkeypatch.setattr(fontes, "_get", lambda *a, **k: None)
    s, com_proventos = fontes.yahoo_ajustado("XXXX3.SA")
    assert s.empty and not com_proventos
