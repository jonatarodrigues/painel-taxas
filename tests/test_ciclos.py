import pandas as pd

from pipeline.ciclos import ciclos_copom


def selic(pares):
    datas, valores = zip(*pares)
    return pd.Series(valores, index=pd.DatetimeIndex(pd.to_datetime(datas), name="data"), dtype=float)


def test_uma_virada_por_mudanca_de_direcao():
    s = selic([("2021-01-01", 2.0), ("2021-03-17", 2.75), ("2021-05-05", 3.5), ("2022-08-03", 13.75),
               ("2023-08-02", 13.25), ("2024-05-08", 10.5), ("2024-09-18", 10.75)])
    ev = ciclos_copom(s)
    assert [e["data"] for e in ev] == ["2021-03-17", "2023-08-02", "2024-09-18"]
    assert ev[0]["titulo"] == "Copom inicia ciclo de alta: 2,00% → 2,75%"
    assert ev[1]["titulo"].startswith("Copom inicia ciclo de baixa")
    assert all(e["categoria"] == "copom" and e["auto"] is True for e in ev)


def test_dias_repetidos_nao_geram_evento():
    s = selic([("2021-01-01", 2.0), ("2021-01-04", 2.0), ("2021-01-05", 2.0)])
    assert ciclos_copom(s) == []


def test_vazia():
    assert ciclos_copom(pd.Series(dtype=float)) == []
