import json
from datetime import date
from pathlib import Path

import pytest

from pipeline import focus, fontes

FIX = Path(__file__).parent / "fixtures" / "focus_bruto.json"


def test_url_odata_codifica_espaco_como_pct20():
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


def _falso(anuais, infl):
    def consultar_falso(entidade, **op):
        if entidade == "ExpectativasMercadoSelic":
            return [linha_selic("2026-09-25", "R7/2026", 13.5)]
        if entidade == "ExpectativasMercadoInflacao12Meses":
            return infl
        return anuais
    return consultar_falso


def test_baixar_sem_anuais_levanta_resposta_vazia(monkeypatch):
    monkeypatch.setattr(focus, "consultar", _falso([], [{"Data": "2026-09-25", "Mediana": 4.65}]))
    with pytest.raises(fontes.RespostaVazia, match="Focus sem projeções anuais"):
        focus.baixar(date(2026, 9, 30))


def test_baixar_sem_infl12_levanta_resposta_vazia(monkeypatch):
    monkeypatch.setattr(focus, "consultar", _falso([{"Indicador": "IPCA"}], []))
    with pytest.raises(fontes.RespostaVazia, match="Focus sem IPCA 12 meses"):
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
