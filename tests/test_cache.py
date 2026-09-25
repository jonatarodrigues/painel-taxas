import pandas as pd

from pipeline.cache import Cache, obter
from pipeline.series import POR_ID

SELIC = POR_ID["selic_meta"]


def serie_exemplo():
    idx = pd.DatetimeIndex(pd.to_datetime(["2024-01-02", "2024-01-03"]), name="data")
    return pd.Series([11.75, 11.75], index=idx)


def test_gravar_e_ler_round_trip(tmp_path):
    c = Cache(tmp_path)
    c.gravar("x", serie_exemplo())
    lida = c.ler("x")
    assert isinstance(lida.index, pd.DatetimeIndex)
    assert list(lida.index) == list(serie_exemplo().index)
    assert lida.tolist() == [11.75, 11.75]


def test_ler_inexistente(tmp_path):
    assert Cache(tmp_path).ler("nada") is None
    assert Cache(tmp_path).modificado_em("nada") is None


def test_obter_ok_grava_cache(tmp_path):
    c = Cache(tmp_path)
    s, status, aviso = obter(SELIC, c, baixar=lambda serie: serie_exemplo())
    assert status == "ok" and aviso is None and len(s) == 2
    assert c.ler("selic_meta") is not None


def test_obter_falha_usa_cache(tmp_path):
    c = Cache(tmp_path)
    c.gravar("selic_meta", serie_exemplo())

    def quebrado(serie):
        raise ConnectionError("sem rede")

    s, status, aviso = obter(SELIC, c, baixar=quebrado)
    assert status == "desatualizada" and len(s) == 2
    assert "sem rede" in aviso and "usando cache" in aviso


def test_obter_resposta_vazia_conta_como_falha(tmp_path):
    c = Cache(tmp_path)
    s, status, aviso = obter(SELIC, c, baixar=lambda serie: pd.Series(dtype=float))
    assert s is None and status == "ausente" and "sem cache" in aviso


def test_obter_offline(tmp_path):
    c = Cache(tmp_path)
    assert obter(SELIC, c, offline=True)[1] == "ausente"
    c.gravar("selic_meta", serie_exemplo())
    s, status, aviso = obter(SELIC, c, offline=True, baixar=lambda serie: 1 / 0)
    assert status == "desatualizada" and len(s) == 2
