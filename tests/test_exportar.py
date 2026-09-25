import json

import numpy as np
import pandas as pd

from pipeline import correlacao, exportar, transformar
from pipeline.series import POR_ID


def diaria(n, inicio="2020-01-01", base=100.0):
    idx = pd.bdate_range(inicio, periods=n, name="data")
    return pd.Series(base + np.arange(n, dtype=float), index=idx)


def montar_exemplo():
    brutas = {"usd_brl": diaria(700, base=4.0), "selic_meta": diaria(700, base=10.0), "cdi": diaria(30, base=10.0)}
    diarias = {k: transformar.para_diaria(v) for k, v in brutas.items()}
    mensais = {k: transformar.para_mensal(v, "d") for k, v in brutas.items()}
    mensais["usd_brl"].iloc[3] = np.nan  # buraco de propósito
    transformadas = {k: transformar.transformar(m, POR_ID[k].transformacao) for k, m in mensais.items()}
    correl = correlacao.calcular(transformadas)
    metas = {k: POR_ID[k] for k in brutas}
    eventos = [{"data": "2020-03-11", "titulo": "t", "categoria": "crise", "descricao": "d", "series": ["usd_brl"]}]
    return exportar.montar(metas, diarias, mensais, {k: "ok" for k in brutas}, ["aviso x"], correl, eventos)


def test_montar_formato():
    d = montar_exemplo()
    assert set(d) == {"gerado_em", "series", "correlacao", "arestas", "eventos", "avisos"}
    usd = d["series"]["usd_brl"]
    assert usd["var_tipo"] == "pct" and d["series"]["selic_meta"]["var_tipo"] == "pp"
    assert usd["diario"][0][0] == "2020-01-01" and len(usd["diario"][0]) == 2
    assert usd["mensal"][0][0] == "2020-01"
    assert usd["inicio"] == "2020-01-01" and usd["fim"] == usd["diario"][-1][0]
    assert usd["ultimo"] == usd["mensal"][-1][1]
    assert usd["var_1m"] is not None and usd["var_12m"] is not None
    assert "n" in d["correlacao"]["tudo"]


def test_montar_mantem_serie_curta():
    d = montar_exemplo()
    assert "cdi" in d["series"]                         # fica nos gráficos
    assert "cdi" not in d["correlacao"]["tudo"]["ids"]  # mas sai da correlação
    assert d["series"]["cdi"]["var_12m"] is None


def test_gravar_sem_nan(tmp_path):
    d = montar_exemplo()
    exportar.gravar(d, tmp_path)
    texto = (tmp_path / "dados.json").read_text(encoding="utf-8")
    assert "NaN" not in texto and "Infinity" not in texto
    assert json.loads(texto)["avisos"] == ["aviso x"]
    js = (tmp_path / "dados.js").read_text(encoding="utf-8")
    assert js.startswith("window.DADOS = {") and js.rstrip().endswith("};")


def test_variacao_percentual_e_pontos():
    m = pd.Series([100.0, 110.0], index=pd.period_range("2024-01", periods=2, freq="M"))
    assert exportar._variacao(m, 1, pct=True) == 10.0
    assert exportar._variacao(m, 1, pct=False) == 10.0
    assert exportar._variacao(m, 12, pct=True) is None
