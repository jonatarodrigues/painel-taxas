import json
from collections import Counter
from pathlib import Path

from pipeline import agenda

RAIZ = Path(__file__).parent.parent


def gravar(tmp_path, conteudo):
    arq = tmp_path / "agenda.json"
    arq.write_text(conteudo if isinstance(conteudo, str) else json.dumps(conteudo), encoding="utf-8")
    return arq


def test_carregar_valida_e_ordena(tmp_path):
    arq = gravar(tmp_path, [
        {"data": "2026-12-09", "tipo": "copom", "titulo": "Copom", "reuniao": "R8/2026"},
        {"data": "2026-10-28", "tipo": "fomc", "titulo": "FOMC"},
        {"data": "2026-11-04", "tipo": "copom", "titulo": "Copom"},               # sem reuniao
        {"data": "2026-02-30", "tipo": "ipca", "titulo": "IPCA de janeiro"},     # data inexistente
        {"data": "2026-11-10", "tipo": "ptax", "titulo": "?"},                   # tipo desconhecido
        {"data": "2026-11-11", "tipo": "copom", "titulo": "Copom", "reuniao": "R9/2026"},
        {"data": "2026-11-12", "tipo": "ipca", "titulo": "  "},
        "texto solto",
    ])
    avisos = []
    r = agenda.carregar(arq, avisos)
    assert [e["data"] for e in r] == ["2026-10-28", "2026-12-09"]
    assert avisos == ["agenda.json: 6 entrada(s) ignorada(s) por formato inválido"]


def test_carregar_arquivo_ausente_quebrado_ou_nao_lista(tmp_path):
    avisos = []
    assert agenda.carregar(tmp_path / "agenda.json", avisos) == []
    assert agenda.carregar(gravar(tmp_path, "{quebrado"), avisos) == []
    assert agenda.carregar(gravar(tmp_path, {"data": "2026-10-28"}), avisos) == []
    assert avisos[0] == "agenda.json não encontrado; aba Previsões sem agenda"
    assert avisos[1].startswith("agenda.json inválido (") and avisos[1].endswith("); aba Previsões sem agenda")
    assert avisos[2] == "agenda.json inválido (esperava uma lista); aba Previsões sem agenda"


def test_agenda_json_do_repositorio_integra():
    brutos = json.loads((RAIZ / "agenda.json").read_text(encoding="utf-8"))
    avisos = []
    validos = agenda.carregar(RAIZ / "agenda.json", avisos)
    assert avisos == [] and len(validos) == len(brutos)
    assert [e["data"] for e in brutos] == sorted(e["data"] for e in brutos), "agenda.json em ordem de data"
    reunioes = [e["reuniao"] for e in brutos if e["tipo"] == "copom"]
    assert len(reunioes) == len(set(reunioes))
    por_ano = Counter(r.split("/")[1] for r in reunioes)
    assert por_ano["2026"] == 8 and por_ano["2027"] == 8
    fomc = Counter(e["data"][:4] for e in brutos if e["tipo"] == "fomc")
    assert fomc["2026"] == 8 and fomc["2027"] == 8
