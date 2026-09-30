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
