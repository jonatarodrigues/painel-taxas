import json
import re
from pathlib import Path

from pipeline.series import POR_ID

CATEGORIAS = {"copom", "fomc", "crise", "politica", "fiscal", "externo", "plano"}


def test_eventos_json_integro():
    eventos = json.loads((Path(__file__).parent.parent / "eventos.json").read_text(encoding="utf-8"))
    assert len(eventos) >= 60
    datas = []
    for e in eventos:
        assert set(e) == {"data", "titulo", "categoria", "descricao", "series"}, e["titulo"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["data"]), e["data"]
        assert e["categoria"] in CATEGORIAS, e["titulo"]
        assert 10 <= len(e["descricao"]) <= 400, e["titulo"]
        assert e["series"] and all(s in POR_ID for s in e["series"]), e["titulo"]
        datas.append(e["data"])
    assert datas == sorted(datas), "eventos devem estar em ordem cronológica"
