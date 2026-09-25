import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

import atualizar
from pipeline import cache as cache_mod
from pipeline.series import SERIES

RAIZ = Path(__file__).parent.parent


def serie_fake(serie):
    if serie.freq == "d":
        idx = pd.bdate_range("2018-01-01", periods=1600, name="data")
    else:
        idx = pd.date_range("2018-01-01", periods=80, freq="MS", name="data")
    rng = np.random.default_rng(sum(map(ord, serie.id)))  # semente determinística por série
    base = 100 + np.cumsum(rng.normal(size=len(idx)))
    return pd.Series(base, index=idx)


def test_main_gera_arquivos(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod.fontes, "baixar", serie_fake)
    shutil.copy(RAIZ / "eventos.json", tmp_path / "eventos.json")
    assert atualizar.main(["--pasta", str(tmp_path)]) == 0
    d = json.loads((tmp_path / "dados.json").read_text(encoding="utf-8"))
    assert len(d["series"]) >= len(SERIES)          # baixadas + derivadas
    assert "ipca_12m" in d["series"] and "juro_real" in d["series"]
    assert any(e.get("auto") for e in d["eventos"])  # ciclos da Selic detectados
    assert (tmp_path / "dados.js").exists() and (tmp_path / "cache" / "selic_meta.csv").exists()


def test_offline_usa_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod.fontes, "baixar", serie_fake)
    shutil.copy(RAIZ / "eventos.json", tmp_path / "eventos.json")
    atualizar.main(["--pasta", str(tmp_path)])
    monkeypatch.setattr(cache_mod.fontes, "baixar", lambda s: 1 / 0)
    assert atualizar.main(["--pasta", str(tmp_path), "--offline"]) == 0
    d = json.loads((tmp_path / "dados.json").read_text(encoding="utf-8"))
    assert d["series"]["ipca_12m"]["status"] == "desatualizada"


def test_status_derivada_herda_pior_status():
    st = {"ipca": "desatualizada", "selic_meta": "ok"}
    assert atualizar.status_derivada("ipca_12m", st) == "desatualizada"
    st["ipca_12m"] = atualizar.status_derivada("ipca_12m", st)
    assert atualizar.status_derivada("juro_real", st) == "desatualizada"
    assert atualizar.status_derivada("curva_eua", {}) == "ausente"


def test_offline_sem_cache_retorna_1(tmp_path):
    shutil.copy(RAIZ / "eventos.json", tmp_path / "eventos.json")
    assert atualizar.main(["--pasta", str(tmp_path), "--offline"]) == 1
