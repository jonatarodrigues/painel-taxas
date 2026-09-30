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
