import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline import bolsa

FIX = Path(__file__).parent / "fixtures"


def carregar(nome):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


@pytest.mark.parametrize("texto, esperado", [
    ("2,792", 2.792), ("1.460.506.056", 1460506056.0), ("100,000", 100.0),
    ("0,045", 0.045), ("", None), (None, None), ("abc", None),
])
def test_numero_br(texto, esperado):
    assert bolsa.numero_br(texto) == esperado


def test_parse_carteira_ibov():
    c = bolsa.parse_carteira_b3(carregar("b3_ibov.json"))
    assert c["data"] == "2026-10-05"
    assert [a["ticker"] for a in c["ativos"]] == ["WEGE3", "EMBJ3", "ITUB4", "PETR4"]
    weg = c["ativos"][0]
    assert weg == {"ticker": "WEGE3", "nome": "WEG", "setor": "Bens Indls",
                   "subsetor": "Bens Indls / Máqs e Equips", "peso": 2.792}
    petr = c["ativos"][3]
    assert petr["setor"] == "Petróleo, Gás e Biocombustíveis"  # sem "/": setor é o texto todo


def test_parse_carteira_ifix():
    c = bolsa.parse_carteira_b3(carregar("b3_ifix.json"))
    assert [a["peso"] for a in c["ativos"]] == [9.177, 4.462, 0.045]
    assert c["ativos"][0]["nome"] == "FII KINEA RI"


@pytest.mark.parametrize("payload", [
    None, {}, {"header": {"date": "05/10/26"}}, {"header": {}, "results": []},
    {"header": {"date": "05/10/26"}, "results": []},
    {"header": {"date": "ontem"}, "results": [{"cod": "X", "part": "1"}]},
])
def test_parse_carteira_malformada_devolve_none(payload):
    assert bolsa.parse_carteira_b3(payload) is None


def test_parse_carteira_descarta_linhas_sem_peso():
    p = carregar("b3_ibov.json")
    p["results"][1]["part"] = ""
    p["results"][2]["cod"] = "  "
    c = bolsa.parse_carteira_b3(p)
    assert [a["ticker"] for a in c["ativos"]] == ["WEGE3", "PETR4"]


def test_parse_carteira_ano_com_quatro_digitos():
    p = carregar("b3_ibov.json")
    p["header"]["date"] = "05/10/2026"
    assert bolsa.parse_carteira_b3(p)["data"] == "2026-10-05"
