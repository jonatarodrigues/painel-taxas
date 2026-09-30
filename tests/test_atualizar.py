import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import atualizar
from pipeline import cache as cache_mod
from pipeline import focus
from pipeline.series import SERIES

RAIZ = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def sem_focus_na_rede(monkeypatch):
    """Os testes nunca chamam o Olinda de verdade."""
    def falha(hoje):
        raise ConnectionError("rede desligada no teste")
    monkeypatch.setattr(focus, "baixar", falha)


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
    assert sum("Modo offline" in a for a in d["avisos"]) == 1 and not any("modo offline, usando" in a for a in d["avisos"])


def test_status_derivada_herda_pior_status():
    st = {"ipca": "desatualizada", "selic_meta": "ok"}
    assert atualizar.status_derivada("ipca_12m", st) == "desatualizada"
    st["ipca_12m"] = atualizar.status_derivada("ipca_12m", st)
    assert atualizar.status_derivada("juro_real", st) == "desatualizada"
    assert atualizar.status_derivada("curva_eua", {}) == "ausente"


def test_offline_sem_cache_retorna_1(tmp_path):
    shutil.copy(RAIZ / "eventos.json", tmp_path / "eventos.json")
    assert atualizar.main(["--pasta", str(tmp_path), "--offline"]) == 1


def test_carregar_eventos_json_quebrado(tmp_path):
    arq = tmp_path / "eventos.json"
    arq.write_text("[{", encoding="utf-8")
    avisos = []
    assert atualizar.carregar_eventos(arq, avisos) == []
    assert any("inválido" in a for a in avisos)


def test_carregar_eventos_descarta_malformados(tmp_path):
    arq = tmp_path / "eventos.json"
    arq.write_text(json.dumps([
        {"data": "2008-09-15", "titulo": "ok", "categoria": "crise", "descricao": "d", "series": ["usd_brl"]},
        {"data": "15/09/2008", "titulo": "data errada", "categoria": "crise", "descricao": "d", "series": ["usd_brl"]},
        {"data": "2008-09-15", "titulo": "serie inexistente", "categoria": "crise", "descricao": "d", "series": ["xpto"]},
        {"data": "2008-09-15", "titulo": "sem series", "categoria": "crise", "descricao": "d"},
    ]), encoding="utf-8")
    avisos = []
    validos = atualizar.carregar_eventos(arq, avisos)
    assert [e["titulo"] for e in validos] == ["ok"]
    assert avisos and "3 evento(s)" in avisos[0]


def test_carregar_eventos_ausente(tmp_path):
    avisos = []
    assert atualizar.carregar_eventos(tmp_path / "eventos.json", avisos) == []
    assert "não encontrado" in avisos[0]


def test_main_gera_bloco_previsoes(tmp_path, monkeypatch):
    bruto = json.loads((RAIZ / "tests" / "fixtures" / "focus_bruto.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(cache_mod.fontes, "baixar", serie_fake)
    monkeypatch.setattr(focus, "baixar", lambda hoje: bruto)
    shutil.copy(RAIZ / "eventos.json", tmp_path / "eventos.json")
    shutil.copy(RAIZ / "agenda.json", tmp_path / "agenda.json")
    assert atualizar.main(["--pasta", str(tmp_path)]) == 0
    d = json.loads((tmp_path / "dados.json").read_text(encoding="utf-8"))
    assert d["previsoes"]["focus_data"] == bruto["data_pesquisa"]
    assert (tmp_path / "cache" / "focus.json").exists()
    # Offline: o Focus vem do cache, com aviso próprio e fora do resumo "Modo offline" das séries.
    assert atualizar.main(["--pasta", str(tmp_path), "--offline"]) == 0
    d = json.loads((tmp_path / "dados.json").read_text(encoding="utf-8"))
    assert d["previsoes"]["focus_data"] == bruto["data_pesquisa"]
    assert any(a.startswith("Focus: lido do cache de") for a in d["avisos"])


def test_main_sem_focus_e_sem_cache_continua(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod.fontes, "baixar", serie_fake)
    shutil.copy(RAIZ / "eventos.json", tmp_path / "eventos.json")
    assert atualizar.main(["--pasta", str(tmp_path)]) == 0
    d = json.loads((tmp_path / "dados.json").read_text(encoding="utf-8"))
    assert d["previsoes"]["focus_data"] is None
    assert any(a.startswith("Focus: falha ao baixar") for a in d["avisos"])
    assert "agenda.json não encontrado; aba Previsões sem agenda" in d["avisos"]


def test_valor_dezembro_e_ultimo_do_ano():
    m = pd.Series([4.1, 4.2644], index=pd.to_datetime(["2025-11-01", "2025-12-01"]))
    assert atualizar.valor_dezembro(m, 2025) == 4.2644
    assert atualizar.valor_dezembro(m, 2024) is None and atualizar.valor_dezembro(None, 2025) is None
    d = pd.Series([5.4, 5.5024, 5.6], index=pd.to_datetime(["2025-12-30", "2025-12-31", "2026-01-02"]))
    assert atualizar.ultimo_do_ano(d, 2025) == 5.5024
    assert atualizar.ultimo_do_ano(d, 2024) is None and atualizar.ultimo_do_ano(None, 2025) is None
