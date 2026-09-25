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
