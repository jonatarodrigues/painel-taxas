import numpy as np
import pandas as pd

from pipeline import correlacao as C


def mensal(valores, inicio="2000-01"):
    return pd.Series(valores, index=pd.period_range(inicio, periods=len(valores), freq="M"), dtype=float)


def test_matriz_simetrica_com_diagonal_um():
    rng = np.random.default_rng(0)
    x = rng.normal(size=60)
    t = {"a": mensal(x), "b": mensal(x * 2 + rng.normal(scale=0.1, size=60)), "c": mensal(rng.normal(size=60))}
    m = C.matriz(t, None)
    assert m["ids"] == ["a", "b", "c"]
    assert m["matriz"][0][0] == 1.0
    assert m["matriz"][0][1] == m["matriz"][1][0] > 0.95
    assert m["n"][0][1] == 60


def test_sobreposicao_curta_da_nulo():
    t = {"a": mensal(np.arange(40.0)), "b": mensal(np.arange(40.0), inicio="2002-06")}  # 11 meses em comum
    m = C.matriz(t, None)
    assert m["matriz"][0][1] is None
    assert m["n"][0][1] == 11


def test_serie_curta_excluida():
    t = {"a": mensal(np.arange(40.0)), "curta": mensal(np.arange(10.0))}
    assert C.matriz(t, None)["ids"] == ["a"]


def test_janela_recorta_pelos_ultimos_meses():
    t = {"a": mensal(np.arange(200.0)), "b": mensal(np.arange(200.0) ** 2)}
    assert C.matriz(t, 24)["n"][0][1] == 24
    assert C.matriz(t, None)["n"][0][1] == 200


def test_arestas_respeitam_corte_e_ordenam():
    m = {"ids": ["a", "b", "c"], "matriz": [[1, 0.5, 0.1], [0.5, 1, -0.8], [0.1, -0.8, 1]], "n": [[9, 9, 9]] * 3}
    ar = C.arestas(m, corte=0.15)
    assert [(e["a"], e["b"], e["r"]) for e in ar] == [("b", "c", -0.8), ("a", "b", 0.5)]


def test_calcular_tem_todas_as_janelas():
    t = {"a": mensal(np.random.default_rng(1).normal(size=150)), "b": mensal(np.random.default_rng(2).normal(size=150))}
    out = C.calcular(t)
    assert set(out["correlacao"]) == set(out["arestas"]) == {"tudo", "10a", "5a", "2a"}
