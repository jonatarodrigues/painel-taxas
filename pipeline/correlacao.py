"""Matrizes de correlação por janela e arestas do grafo."""
from __future__ import annotations

import pandas as pd

JANELAS: dict[str, int | None] = {"tudo": None, "10a": 120, "5a": 60, "2a": 24}
MIN_MESES = 24
CORTE_ARESTA = 0.15


def recortar(df: pd.DataFrame, meses: int | None) -> pd.DataFrame:
    if meses is None or df.empty:
        return df
    ultimo = df.index.max()
    return df[df.index > ultimo - meses]


def matriz(transformadas: dict[str, pd.Series], meses: int | None) -> dict:
    df = pd.DataFrame(transformadas).sort_index()
    df = recortar(df, meses)
    df = df.loc[:, df.notna().sum() >= MIN_MESES]
    ids = list(df.columns)
    r = df.corr(min_periods=MIN_MESES)
    presente = df.notna().astype(int)
    n = presente.T @ presente
    k = len(ids)
    mat = [[None if pd.isna(r.iat[i, j]) else round(float(r.iat[i, j]), 4) for j in range(k)] for i in range(k)]
    cont = [[int(n.iat[i, j]) for j in range(k)] for i in range(k)]
    return {"ids": ids, "matriz": mat, "n": cont}


def arestas(m: dict, corte: float = CORTE_ARESTA) -> list[dict]:
    ids, mat, n = m["ids"], m["matriz"], m["n"]
    out = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            r = mat[i][j]
            if r is not None and abs(r) >= corte:
                out.append({"a": ids[i], "b": ids[j], "r": r, "n": n[i][j]})
    return sorted(out, key=lambda e: -abs(e["r"]))


def calcular(transformadas: dict[str, pd.Series]) -> dict:
    correl, ars = {}, {}
    for nome, meses in JANELAS.items():
        m = matriz(transformadas, meses)
        correl[nome] = m
        ars[nome] = arestas(m)
    return {"correlacao": correl, "arestas": ars}
