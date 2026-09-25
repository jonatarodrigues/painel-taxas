import numpy as np
import pandas as pd
import pytest

from pipeline import transformar as T


def diaria(valores, datas):
    return pd.Series(valores, index=pd.DatetimeIndex(pd.to_datetime(datas), name="data"), dtype=float)


def test_para_diaria_preenche_buraco_curto_e_nao_longo():
    s = diaria([1, 2, 3], ["2024-01-02", "2024-01-04", "2024-01-31"])
    d = T.para_diaria(s, limite_ffill=5)
    assert d[pd.Timestamp("2024-01-03")] == 1          # buraco de 1 dia: preenchido
    assert pd.Timestamp("2024-01-12") not in d.index  # buraco de 18 dias úteis: não
    assert pd.Timestamp("2024-01-06") not in d.index  # sábado nunca entra


def test_para_mensal_diaria_pega_ultimo_do_mes():
    s = diaria([10, 11, 20], ["2024-01-02", "2024-01-31", "2024-02-15"])
    m = T.para_mensal(s, "d")
    assert isinstance(m.index, pd.PeriodIndex)
    assert m[pd.Period("2024-01", "M")] == 11
    assert m[pd.Period("2024-02", "M")] == 20


def test_para_mensal_mensal_mantem_valor():
    s = diaria([0.5, 0.4], ["2024-01-01", "2024-02-01"])
    m = T.para_mensal(s, "m")
    assert list(m.index.astype(str)) == ["2024-01", "2024-02"]


def test_para_mensal_vazia():
    assert T.para_mensal(pd.Series(dtype=float), "d").empty


def test_acumulado_12m():
    idx = pd.period_range("2023-01", periods=13, freq="M")
    s = pd.Series([1.0] * 13, index=idx)
    a = T.acumulado_12m(s)
    assert len(a) == 2
    assert a.iloc[0] == pytest.approx((1.01 ** 12 - 1) * 100)


def test_transformar_diff_e_nivel():
    idx = pd.period_range("2024-01", periods=3, freq="M")
    s = pd.Series([10.0, 10.5, 10.25], index=idx)
    assert list(T.transformar(s, "diff").round(4)) == [0.5, -0.25]
    assert list(T.transformar(s, "nivel")) == [10.0, 10.5, 10.25]


def test_logret_ignora_nao_positivos():
    idx = pd.period_range("2020-02", periods=4, freq="M")
    s = pd.Series([50.0, -37.0, 20.0, 40.0], index=idx)  # WTI ficou negativo em abril/2020
    r = T.transformar(s, "logret")
    assert not r.isna().any()
    assert r.iloc[-1] == pytest.approx(np.log(2))


def test_transformar_tipo_desconhecido():
    with pytest.raises(ValueError):
        T.transformar(pd.Series(dtype=float), "raiz")


def test_derivadas():
    idx = pd.period_range("2023-01", periods=13, freq="M")
    mensais = {
        "ipca": pd.Series([0.5] * 13, index=idx),
        "selic_meta": pd.Series([13.75] * 13, index=idx),
        "fed_funds": pd.Series([5.0] * 13, index=idx),
        "treasury_10y": pd.Series([4.0] * 13, index=idx),
        "treasury_2y": pd.Series([4.5] * 13, index=idx),
    }
    d = T.derivadas(mensais)
    assert set(d) == {"ipca_12m", "juro_real", "dif_selic_fed", "curva_eua"}  # sem igpm -> sem igpm_12m
    assert d["dif_selic_fed"].iloc[-1] == pytest.approx(8.75)
    assert d["curva_eua"].iloc[-1] == pytest.approx(-0.5)
    assert d["juro_real"].iloc[-1] == pytest.approx(13.75 - d["ipca_12m"].iloc[-1])


def test_diff_nao_atravessa_buraco_de_mes():
    idx = pd.PeriodIndex(["2024-01", "2024-02", "2024-04"], freq="M")
    s = pd.Series([10.0, 10.5, 12.0], index=idx)
    r = T.transformar(s, "diff")
    assert list(r.index.astype(str)) == ["2024-02"]  # 2024-04 não tem mês anterior


def test_acumulado_12m_exige_12_meses_consecutivos():
    idx = pd.period_range("2023-01", periods=14, freq="M").delete(6)  # falta 2023-07
    s = pd.Series([1.0] * 13, index=idx)
    assert T.acumulado_12m(s).empty
