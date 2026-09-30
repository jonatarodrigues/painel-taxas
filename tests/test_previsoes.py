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
