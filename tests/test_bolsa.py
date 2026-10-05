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


# ---- retornos e mini-série semanal ----

def serie(pontos: dict) -> pd.Series:
    s = pd.Series(pontos, dtype=float)
    s.index = pd.DatetimeIndex(pd.to_datetime(s.index), name="data")
    return s


BASE = serie({
    "2025-10-03": 80, "2025-10-06": 90,      # m12 da ref 07/10/2026 usa 06/10/2025 (<= 07/10/2025)
    "2025-12-31": 100,                       # base do ano
    "2026-09-30": 110,                       # base do mês
    "2026-10-02": 120,                       # sexta: base da semana
    "2026-10-05": 125, "2026-10-06": 130,    # 06/10: base do dia
    "2026-10-07": 143,
})


def test_retornos_quarta_feira():
    r = bolsa.retornos(BASE, pd.Timestamp("2026-10-07"))
    assert r == {"dia": 10.0, "semana": 19.17, "mes": 30.0, "ano": 43.0, "m12": 58.89}


def test_retornos_segunda_feira_semana_igual_dia():
    r = bolsa.retornos(BASE, pd.Timestamp("2026-10-05"))
    assert r["dia"] == r["semana"] == 4.17


def test_retornos_virada_de_ano():
    s = serie({"2025-12-26": 100, "2025-12-31": 100, "2026-01-02": 105})  # 26/12: base da semana (< seg 29/12)
    r = bolsa.retornos(s, pd.Timestamp("2026-01-02"))
    assert r["dia"] == r["semana"] == r["mes"] == r["ano"] == 5.0
    assert r["m12"] is None


def test_retornos_ativo_parado_tudo_nulo():
    r = bolsa.retornos(BASE, pd.Timestamp("2026-10-08"))
    assert r == {p: None for p in bolsa.PERIODOS}


def test_retornos_serie_vazia_ou_none():
    assert bolsa.retornos(None, pd.Timestamp("2026-10-07")) == {p: None for p in bolsa.PERIODOS}
    assert bolsa.retornos(serie({}), pd.Timestamp("2026-10-07")) == {p: None for p in bolsa.PERIODOS}


def test_retornos_ativo_recente_so_periodos_sem_base_ficam_nulos():
    s = serie({"2026-03-02": 50, "2026-09-30": 55, "2026-10-06": 60, "2026-10-07": 66})
    r = bolsa.retornos(s, pd.Timestamp("2026-10-07"))
    assert r["m12"] is None and r["ano"] is None
    assert r["mes"] == 20.0 and r["dia"] == 10.0


def test_retornos_ignora_pontos_depois_da_ref():
    s = BASE.copy()
    s[pd.Timestamp("2026-10-08")] = 999
    assert bolsa.retornos(s, pd.Timestamp("2026-10-07"))["dia"] == 10.0


def test_semanas_e_rotulos():
    ref = pd.Timestamp("2026-10-07")  # quarta
    per = bolsa.semanas(ref, 3)
    assert len(per) == 3
    assert bolsa.rotulos_semanas(per, ref) == ["2026-09-25", "2026-10-02", "2026-10-07"]


def test_semanal_ultimo_valor_de_cada_semana_e_nulo_sem_pregao():
    ref = pd.Timestamp("2026-10-07")
    per = bolsa.semanas(ref, 3)
    s = serie({"2026-09-22": 1, "2026-09-24": 2,      # semana até 25/09: último = 2
               "2026-10-05": 5, "2026-10-07": 7,      # semana corrente: 7
               "2026-10-08": 99})                     # depois da ref: ignorado
    assert bolsa.semanal(s, ref, per) == [2.0, None, 7.0]
    assert bolsa.semanal(None, ref, per) == [None, None, None]
