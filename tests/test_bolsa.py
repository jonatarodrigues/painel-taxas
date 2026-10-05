import base64
import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline import bolsa, fontes
from pipeline.cache import Cache

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


# ---- montagem de uma visão ----

REF = pd.Timestamp("2026-10-07")


def ativo(ticker, setor, peso, dia):
    return {"ticker": ticker, "setor": setor, "peso": peso, "ret": {p: dia for p in bolsa.PERIODOS}}


def test_agregar_setores_pondera_pelo_peso_e_ordena_por_peso():
    ativos = [ativo("A", "Fin", 6.0, 2.0), ativo("B", "Fin", 2.0, -2.0), ativo("C", "Pet", 10.0, 1.0)]
    s = bolsa.agregar_setores(ativos)
    assert [x["nome"] for x in s] == ["Pet", "Fin"]
    assert s[1]["peso"] == 8.0 and s[1]["ret"]["dia"] == 1.0   # (6*2 + 2*-2) / 8


def test_agregar_setores_normaliza_sem_ativo_sem_dado():
    ativos = [ativo("A", "Fin", 6.0, 2.0), ativo("B", "Fin", 2.0, None)]
    s = bolsa.agregar_setores(ativos)
    assert s[0]["ret"]["dia"] == 2.0 and s[0]["peso"] == 8.0


def test_agregar_setores_tudo_sem_dado_fica_nulo():
    assert bolsa.agregar_setores([ativo("A", "Fin", 6.0, None)])[0]["ret"]["dia"] is None


def test_soma_dos_setores_igual_a_soma_dos_ativos():
    ativos = [ativo("A", "X", 3.0, 1.5), ativo("B", "X", 1.0, -4.0), ativo("C", "Y", 5.0, 0.7), ativo("D", "Z", 1.0, 9.0)]
    por_ativo = sum(a["peso"] * a["ret"]["dia"] for a in ativos)
    por_setor = sum(s["peso"] * s["ret"]["dia"] for s in bolsa.agregar_setores(ativos))
    assert por_setor == pytest.approx(por_ativo, abs=0.05)


def test_amplitude():
    ativos = [ativo("A", "X", 1, 1.0), ativo("B", "X", 1, -1.0), ativo("C", "X", 1, 0.0), ativo("D", "X", 1, None)]
    assert bolsa.amplitude(ativos)["dia"] == {"alta": 1, "total": 3}


def test_data_referencia_usa_indice_e_cai_para_a_moda():
    ind = serie({"2026-10-06": 1, "2026-10-07": 2})
    assert bolsa.data_referencia(ind, []) == REF
    a = serie({"2026-10-07": 1}); b = serie({"2026-10-07": 1}); c = serie({"2026-10-02": 1})
    assert bolsa.data_referencia(None, [a, b, c, None]) == REF
    assert bolsa.data_referencia(None, [None]) is None


def carteira(*itens):
    return {"data": "2026-10-05", "ativos": [
        {"ticker": t, "nome": t, "setor": setor, "subsetor": setor + " / Sub", "peso": peso} for t, setor, peso in itens]}


def precos_ok(*tickers, valor_final=110.0):
    s = serie({"2026-10-06": 100, "2026-10-07": valor_final})
    return {t: bolsa.Preco(s) for t in tickers}


def test_montar_visao_ibov():
    avisos = []
    c = carteira(("AAAA3", "Fin", 6.0), ("BBBB3", "Pet", 4.0))
    precos = precos_ok("AAAA3", "BBBB3")
    precos["BBBB3"] = bolsa.Preco(serie({"2026-10-06": 100, "2026-10-07": 95}), desatualizado=True, sem_proventos=True)
    ind = serie({"2026-10-06": 1000, "2026-10-07": 1020})
    v = bolsa.montar_visao("ibov", c, False, precos, ind, None, avisos)
    assert v["nome"] == "Ibovespa" and v["data_ref"] == "2026-10-07" and v["carteira_data"] == "2026-10-05"
    assert v["indice"]["ret"]["dia"] == 2.0 and v["alerta"] is None and avisos == []
    assert v["indice"]["simbolo"] == "^BVSP" and bolsa.INDICES["ifix"][2] == "XFIX11.SA"
    assert v["amplitude"]["dia"] == {"alta": 1, "total": 2}
    assert len(v["semanas"]) == 52 and v["semanas"][-1] == "2026-10-07"
    a, b = v["ativos"]
    assert a["ret"]["dia"] == 10.0 and a["subsetor"] == "Fin / Sub" and len(a["semanal"]) == 52
    assert b["desatualizado"] and b["sem_proventos"] and not b["parado"]
    assert [s["nome"] for s in v["setores"]] == ["Fin", "Pet"]


def test_montar_visao_ativo_sem_preco():
    avisos = []
    c = carteira(("AAAA3", "Fin", 6.0), ("EMBJ3", "Bens", 4.0))
    v = bolsa.montar_visao("ibov", c, False, precos_ok("AAAA3"), None, None, avisos)
    emb = v["ativos"][1]
    assert emb["parado"] and emb["ret"] == {p: None for p in bolsa.PERIODOS}
    assert emb["semanal"] == [None] * 52


def test_montar_visao_alerta_acima_de_20_por_cento():
    avisos = []
    c = carteira(*[(f"T{i}", "X", 1.0) for i in range(5)])
    v = bolsa.montar_visao("ibov", c, False, precos_ok("T0", "T1", "T2"), None, None, avisos)
    assert v["alerta"] == "Ibovespa: 2 de 5 ativos sem cotação em 07/10/2026; o mapa não representa o índice inteiro."
    assert avisos == [v["alerta"]]


def test_montar_visao_exatamente_20_por_cento_nao_alerta():
    c = carteira(*[(f"T{i}", "X", 1.0) for i in range(5)])
    v = bolsa.montar_visao("ibov", c, False, precos_ok("T0", "T1", "T2", "T3"), None, None, [])
    assert v["alerta"] is None


def test_montar_visao_ifix_usa_tipos_e_avisa_sem_tipo():
    avisos = []
    c = carteira(("KNCR11", "Financ e Outros", 9.0), ("NOVO11", "Financ e Outros", 1.0))
    v = bolsa.montar_visao("ifix", c, False, precos_ok("KNCR11", "NOVO11"), None, {"KNCR11": "Papel"}, avisos)
    assert [a["setor"] for a in v["ativos"]] == ["Papel", "Outros"]
    assert "subsetor" not in v["ativos"][0]
    assert avisos == ["IFIX: 1 fundo sem tipo em fiis.json: NOVO11 (fica em Outros)."]


def test_montar_visao_sem_carteira_mostra_so_o_indice():
    avisos = []
    ind = serie({"2026-10-06": 1000, "2026-10-07": 1020})
    v = bolsa.montar_visao("ibov", None, False, {}, ind, None, avisos)
    assert v["ativos"] == [] and v["setores"] == [] and v["alerta"] is None
    assert v["amplitude"]["dia"] == {"alta": 0, "total": 0}
    assert v["indice"]["ret"]["dia"] == 2.0 and v["carteira_data"] is None
    assert avisos == ["Ibovespa: carteira indisponível (B3 fora do ar e sem cache)."]


def test_montar_visao_sem_carteira_e_sem_indice_e_none():
    assert bolsa.montar_visao("ibov", None, False, {}, None, None, []) is None


def test_url_carteira_codifica_o_json_em_base64():
    url = bolsa.url_carteira("IFIX", 2)
    assert url.startswith("https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/")
    p = json.loads(base64.b64decode(url.rsplit("/", 1)[1]))
    assert p == {"language": "pt-br", "pageNumber": 2, "pageSize": 200, "index": "IFIX", "segment": "2"}


def test_baixar_carteira_junta_paginas(monkeypatch):
    p1 = carregar("b3_ibov.json"); p1["page"]["totalPages"] = 2
    p2 = carregar("b3_ibov.json"); p2["results"] = [dict(p2["results"][0], cod="VALE3")]
    respostas = iter([p1, p2])

    class Resp:
        def __init__(self, j): self.j = j
        def json(self): return self.j

    monkeypatch.setattr(fontes, "_get", lambda url, json=False, **k: Resp(next(respostas)))
    c = bolsa.baixar_carteira("IBOV")
    assert [a["ticker"] for a in c["ativos"]][-1] == "VALE3" and len(c["ativos"]) == 5


def test_obter_carteira_grava_e_usa_cache(tmp_path):
    arq = tmp_path / "carteiras.json"
    c = bolsa.parse_carteira_b3(carregar("b3_ibov.json"))
    assert bolsa.obter_carteira("ibov", arq, False, baixar=lambda cod: c) == (c, False)
    def caiu(cod): raise ConnectionError("B3 fora")
    assert bolsa.obter_carteira("ibov", arq, False, baixar=caiu) == (c, True)
    assert bolsa.obter_carteira("ibov", arq, True, baixar=caiu) == (c, True)
    assert bolsa.obter_carteira("ifix", arq, False, baixar=caiu) == (None, False)


def test_obter_carteira_cache_corrompido(tmp_path):
    arq = tmp_path / "carteiras.json"
    arq.write_text("{quebrado", encoding="utf-8")
    def caiu(cod): raise ConnectionError("B3 fora")
    assert bolsa.obter_carteira("ibov", arq, False, baixar=caiu) == (None, False)


def test_obter_precos_baixa_grava_e_cai_para_cache(tmp_path):
    cache = Cache(tmp_path / "bolsa")
    s = serie({"2026-10-06": 100, "2026-10-07": 110})
    r = bolsa.obter_precos(["AAAA3.SA", "^BVSP"], cache, False, baixar=lambda sim: (s, sim != "^BVSP"))
    assert not r["AAAA3.SA"].desatualizado and not r["AAAA3.SA"].sem_proventos
    assert r["^BVSP"].sem_proventos
    def caiu(sim): raise ConnectionError("Yahoo fora")
    r = bolsa.obter_precos(["AAAA3.SA", "BBBB3.SA"], cache, False, baixar=caiu)
    assert r["AAAA3.SA"].desatualizado and len(r["AAAA3.SA"].serie) == 2
    assert r["BBBB3.SA"].serie is None


def test_obter_precos_offline_nao_chama_a_rede(tmp_path):
    cache = Cache(tmp_path / "bolsa")
    cache.gravar(bolsa._id_cache("^BVSP"), serie({"2026-10-07": 1}))
    def proibido(sim): raise AssertionError("não devia baixar")
    r = bolsa.obter_precos(["^BVSP"], cache, True, baixar=proibido)
    assert r["^BVSP"].desatualizado and len(r["^BVSP"].serie) == 1


def test_carregar_fiis(tmp_path):
    arq = tmp_path / "fiis.json"
    arq.write_text(json.dumps({"_tipos": ["Papel", "Outros"], "KNCR11": "Papel", "XXXX11": "Lajão"}), encoding="utf-8")
    avisos = []
    assert bolsa.carregar_fiis(arq, avisos) == {"KNCR11": "Papel", "XXXX11": "Outros"}
    assert avisos == ["fiis.json: tipo desconhecido em XXXX11 (fica em Outros)."]


@pytest.mark.parametrize("conteudo, trecho", [(None, "ausente"), ("{quebrado", "inválido"), ("[1, 2]", "inválido")])
def test_carregar_fiis_ausente_ou_quebrado(tmp_path, conteudo, trecho):
    arq = tmp_path / "fiis.json"
    if conteudo is not None:
        arq.write_text(conteudo, encoding="utf-8")
    avisos = []
    assert bolsa.carregar_fiis(arq, avisos) == {}
    assert len(avisos) == 1 and trecho in avisos[0]


def test_fiis_json_do_repo_e_valido():
    avisos = []
    tipos = bolsa.carregar_fiis(Path(__file__).parent.parent / "fiis.json", avisos)
    assert avisos == [] and len(tipos) >= 90
    assert set(tipos.values()) <= set(bolsa.TIPOS_FII)


def preco_fake(sim):
    s = serie({"2025-10-06": 90, "2026-10-06": 100, "2026-10-07": 105})
    return s, True


def carteira_fake(cod):
    return bolsa.parse_carteira_b3(carregar("b3_ibov.json" if cod == "IBOV" else "b3_ifix.json"))


def test_obter_monta_o_bloco(tmp_path):
    (tmp_path / "fiis.json").write_text(json.dumps({"_tipos": list(bolsa.TIPOS_FII), "KNCR11": "Papel", "HGLG11": "Logística"}), encoding="utf-8")
    avisos = []
    b = bolsa.obter(tmp_path, False, avisos, baixar_carteira_=carteira_fake, baixar_preco=preco_fake)
    assert set(b) == {"ibov", "ifix", "avisos"}
    assert len(b["ibov"]["ativos"]) == 4 and b["ibov"]["indice"]["ret"]["dia"] == 5.0
    assert [a["setor"] for a in b["ifix"]["ativos"]] == ["Papel", "Logística", "Outros"]
    assert b["avisos"] == ["IFIX: 1 fundo sem tipo em fiis.json: CACR11 (fica em Outros)."]
    assert avisos == b["avisos"]
    assert b["ifix"]["indice"]["simbolo"] == "XFIX11.SA" and b["ibov"]["indice"]["simbolo"] == "^BVSP"
    assert (tmp_path / "cache" / "carteiras.json").exists()
    assert (tmp_path / "cache" / "bolsa" / "WEGE3.SA.csv").exists()


def test_obter_b3_fora_usa_carteira_do_cache_e_avisa(tmp_path):
    bolsa.obter(tmp_path, False, [], baixar_carteira_=carteira_fake, baixar_preco=preco_fake)
    def caiu(cod): raise ConnectionError("B3 fora")
    avisos = []
    b = bolsa.obter(tmp_path, False, avisos, baixar_carteira_=caiu, baixar_preco=preco_fake)
    assert b["ibov"]["carteira_cache"] and len(b["ibov"]["ativos"]) == 4
    assert "Ibovespa: carteira da B3 indisponível; usando a de 05/10/2026." in avisos


def test_obter_sem_nada_devolve_none(tmp_path):
    def caiu(*a): raise ConnectionError("fora")
    avisos = []
    assert bolsa.obter(tmp_path, False, avisos, baixar_carteira_=caiu, baixar_preco=caiu) is None
    assert avisos[-1] == "Bolsa: sem carteiras e sem preços; a aba fica vazia nesta atualização."


def test_tamanho_do_bloco_com_175_ativos():
    ref = pd.Timestamp("2026-10-07")
    s = serie({str(d.date()): 100 + i * 0.37 for i, d in enumerate(pd.bdate_range("2025-09-01", ref))})
    c = carteira(*[(f"T{i:03d}3", f"Setor{i % 12}", 100 / 175) for i in range(175)])
    v = bolsa.montar_visao("ibov", c, False, {f"T{i:03d}3": bolsa.Preco(s) for i in range(175)}, s, None, [])
    texto = json.dumps({"ibov": v, "ifix": None, "avisos": []}, ensure_ascii=False, separators=(",", ":"))
    assert len(texto.encode("utf-8")) < 250_000
