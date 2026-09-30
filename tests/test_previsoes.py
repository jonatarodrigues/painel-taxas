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
    args = dict(bruto=BRUTO, agenda_=AGENDA, selic_hoje=13.75, selic_data="2026-09-29", usd_hoje=5.36, fed_funds=3.88,
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
    # o juro real de 12 meses precisa de uma reunião perto de 30/09/2027
    agenda = AGENDA + [{"data": "2027-09-22", "tipo": "copom", "titulo": "Copom", "reuniao": "R6/2027"}]
    bruto = dict(BRUTO, selic=BRUTO["selic"] + [linha("R6/2027", 12.5)])
    p, _ = montar(agenda_=agenda, bruto=bruto)
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


def test_selic_defasada_com_mediana_da_reuniao_passada_ancora_na_mediana():
    hoje = date(2026, 11, 10)            # R7/2026 (04/11) já passou; a série da Selic é de 01/11
    bruto = dict(BRUTO, selic=[linha("R7/2026", 13.5), linha("R8/2026", 13.5), linha("R1/2027", 13.25)])
    p, avisos = montar(bruto=bruto, hoje=hoje, selic_hoje=13.75, selic_data="2026-11-01")
    copom = {a["reuniao"]: a for a in p["agenda"] if a["tipo"] == "copom"}
    assert copom["R8/2026"]["espera"] == {"mediana": 13.5, "dif": 0.0}     # e não "cortar 0,25"
    assert any(s["tipo"] == "copom" and "manter" in s["texto"] for s in p["sinais"])
    assert ("Selic meta mais recente é de 01/11/2026, antes do Copom de 04/11 (R7/2026); decisões esperadas "
            "contadas a partir da mediana do Focus para essa reunião (13,50%)") in avisos


def test_selic_defasada_sem_mediana_omite_sinais_do_copom():
    hoje = date(2026, 11, 10)
    bruto = dict(BRUTO, selic=[linha("R8/2026", 13.5), linha("R1/2027", 13.25)])
    p, avisos = montar(bruto=bruto, hoje=hoje, selic_hoje=13.75, selic_data="2026-11-01")
    assert not any(s["tipo"] in ("copom", "selic") for s in p["sinais"])
    assert not any("espera" in a for a in p["agenda"])
    assert ("Selic meta mais recente é de 01/11/2026, antes do Copom de 04/11 (R7/2026); "
            "sinais do Copom omitidos até a atualização da série") in avisos


def test_selic_posterior_ao_ultimo_copom_nao_avisa():
    p, avisos = montar(selic_data="2026-09-17")
    assert not any("Selic meta mais recente" in a for a in avisos)
    assert any(s["tipo"] == "copom" for s in p["sinais"])


def test_focus_sem_alguns_indicadores_avisa():
    bruto = dict(BRUTO, anuais=[a for a in BRUTO["anuais"] if a["Indicador"] == "IPCA"])
    _, avisos = montar(bruto=bruto)
    for ind in ("Câmbio", "PIB Total", "Selic"):
        assert f"Focus sem projeções anuais de {ind}; sinais e gráfico desse indicador ficam de fora" in avisos
    assert not any("de IPCA;" in a for a in avisos)


HA_12M = {"data_pesquisa": "2025-09-30",
          "selic": [{"Reuniao": "R6/2026", "Mediana": 12.75}, {"Reuniao": "R7/2026", "Mediana": 12.5},
                    {"Reuniao": "R1/2027", "Mediana": 12.0}],
          "anuais": [{"Indicador": "Câmbio", "DataReferencia": "2025", "Mediana": 5.4555},
                     {"Indicador": "IPCA", "DataReferencia": "2025", "Mediana": 4.8061},
                     {"Indicador": "IPCA", "DataReferencia": "2026", "Mediana": 4.29}]}


def com_ha(**troca):
    return montar(bruto=dict(BRUTO, ha_12m=HA_12M, ha_12m_erro=None), **troca)


def test_proj_12m_selic_so_reunioes_datadas_e_anual_em_31_12():
    p, _ = com_ha()
    assert p["trajetorias"]["selic"]["proj_12m"] == {
        "data_pesquisa": "2025-09-30",
        "pontos": [["2026-09-16", 12.75, "R6/2026"], ["2026-11-04", 12.5, "R7/2026"]]}  # R1/2027 sem data na AGENDA
    assert p["trajetorias"]["ipca"]["proj_12m"]["pontos"] == [["2025-12-31", 4.8061, "2025"], ["2026-12-31", 4.29, "2026"]]
    assert p["trajetorias"]["cambio"]["proj_12m"]["pontos"] == [["2025-12-31", 5.4555, "2025"]]
    assert p["trajetorias"]["pib"]["proj_12m"] is None


def test_sinais_de_retrospectiva():
    p, _ = com_ha(ipca_dez_anterior=4.2644, usd_fim_anterior=5.5024)
    assert [s["texto"] for s in p["sinais"] if s["tipo"] == "acerto"] == [
        "Há 12 meses (Focus de 30/09/2025) o mercado esperava a Selic em **12,75%** no Copom de 16/09/2026; "
        "ela está em 13,75% (1,00 p.p. acima).",
        "Há 12 meses o mercado esperava IPCA de **4,81%** em 2025; fechou em 4,26% (0,55 p.p. abaixo).",
        "Há 12 meses o mercado esperava o dólar a **R$ 5,46** no fim de 2025; fechou em R$ 5,50 (+0,7%).",
    ]


def test_retrospectiva_sem_realizado_so_selic():
    p, _ = com_ha()
    acertos = [s["texto"] for s in p["sinais"] if s["tipo"] == "acerto"]
    assert len(acertos) == 1 and acertos[0].startswith("Há 12 meses (Focus de 30/09/2025) o mercado esperava a Selic")


def test_retrospectiva_da_selic_usa_a_ancora_quando_a_selic_esta_defasada():
    p, _ = com_ha(selic_data="2026-09-10")  # antes do Copom de 16/09; o Focus traz R6/2026 = 14,00
    texto = next(s["texto"] for s in p["sinais"] if s["tipo"] == "acerto")
    assert "ela está em 14,00% (1,25 p.p. acima)" in texto


def test_retrospectiva_no_dia_do_copom_nao_conta_a_decisao_do_dia():
    # 16/09 e o dia da R6/2026: a decisao ainda nao esta na Selic quando o pipeline roda
    p, _ = com_ha(hoje=date(2026, 9, 16), selic_data="2026-09-15")
    assert not any(s["tipo"] == "acerto" and "Selic" in s["texto"] for s in p["sinais"])


def test_sem_ha_12m_cache_antigo_e_falha():
    p, avisos = montar()  # BRUTO sem a chave ha_12m, como um cache antigo
    assert all(t["proj_12m"] is None for t in p["trajetorias"].values())
    assert not any(s["tipo"] == "acerto" for s in p["sinais"])
    assert not any("12 meses atrás" in a for a in avisos)
    p, avisos = montar(bruto=dict(BRUTO, ha_12m=None, ha_12m_erro="rede fora"), avisos=[])
    assert "Focus: sem a pesquisa de 12 meses atrás (rede fora); comparação omitida" in avisos
