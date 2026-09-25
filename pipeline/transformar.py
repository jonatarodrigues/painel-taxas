"""Alinhamento temporal e transformações para correlação."""
from __future__ import annotations

import numpy as np
import pandas as pd

LIMITE_FFILL = 5


def _meses_completos(s: pd.Series) -> pd.Series:
    """Reindexa para todos os meses entre o primeiro e o último, deixando NaN nos buracos."""
    if s.empty:
        return s
    return s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))


def para_diaria(s: pd.Series, limite_ffill: int = LIMITE_FFILL) -> pd.Series:
    """Reindexa em dias úteis, preenchendo buracos de até `limite_ffill` dias úteis."""
    if s.empty:
        return pd.Series(dtype=float)
    uteis = pd.bdate_range(s.index.min(), s.index.max())
    cheia = s.reindex(s.index.union(uteis)).ffill(limit=limite_ffill)
    return cheia.reindex(uteis).dropna()


def para_mensal(s: pd.Series, freq: str) -> pd.Series:
    """Índice PeriodIndex('M'). Diária: último valor do mês. Mensal: o valor do mês."""
    if s.empty:
        return pd.Series(dtype=float)
    m = s.resample("ME").last().dropna() if freq == "d" else s.dropna().copy()
    m.index = pd.DatetimeIndex(m.index).to_period("M")
    return m[~m.index.duplicated(keep="last")].sort_index()


def acumulado_12m(pct_mensal: pd.Series) -> pd.Series:
    pct_mensal = _meses_completos(pct_mensal)
    fator = (1 + pct_mensal / 100).rolling(12).apply(np.prod, raw=True)
    return ((fator - 1) * 100).dropna()


def transformar(mensal: pd.Series, tipo: str) -> pd.Series:
    if tipo == "diff":
        return _meses_completos(mensal).diff().dropna()
    if tipo == "logret":
        positivos = mensal[mensal > 0]  # WTI negativo em 2020 quebraria o log
        return np.log(_meses_completos(positivos)).diff().dropna()
    if tipo == "nivel":
        return mensal.dropna()
    raise ValueError(f"transformação desconhecida: {tipo}")


def derivadas(mensais: dict[str, pd.Series]) -> dict[str, pd.Series]:
    def tem(*ids: str) -> bool:
        return all(i in mensais and not mensais[i].empty for i in ids)

    out: dict[str, pd.Series] = {}
    if tem("ipca"):
        out["ipca_12m"] = acumulado_12m(mensais["ipca"])
    if tem("igpm"):
        out["igpm_12m"] = acumulado_12m(mensais["igpm"])
    if "ipca_12m" in out and tem("selic_meta"):
        out["juro_real"] = (mensais["selic_meta"] - out["ipca_12m"]).dropna()
    if tem("selic_meta", "fed_funds"):
        out["dif_selic_fed"] = (mensais["selic_meta"] - mensais["fed_funds"]).dropna()
    if tem("treasury_10y", "treasury_2y"):
        out["curva_eua"] = (mensais["treasury_10y"] - mensais["treasury_2y"]).dropna()
    return out
