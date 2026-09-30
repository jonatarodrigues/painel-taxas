import http.client
import json
import sys
import time

import pytest

import abrir_painel


@pytest.fixture
def servidor(tmp_path):
    (tmp_path / "ola.txt").write_text("oi", encoding="utf-8")
    criados = []

    def criar(codigo=0, espera=0.3, comando=None):
        cmd = comando or [sys.executable, "-c", f"import time, sys; time.sleep({espera}); sys.exit({codigo})"]
        at = abrir_painel.Atualizador(cmd, tmp_path)
        s = abrir_painel.servir(abrir_painel.porta_livre(8900), at, tmp_path)
        criados.append(s)
        return s

    yield criar
    for s in criados:
        s.shutdown()
        s.server_close()


def pedir(s, metodo, caminho, cabecalhos=None, host=None):
    porta = s.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=5)
    c.request(metodo, caminho, headers={"Host": host or f"127.0.0.1:{porta}", **(cabecalhos or {})})
    r = c.getresponse()
    corpo = r.read()
    c.close()
    return r.status, corpo


def esperar_fim(s, limite=10):
    fim = time.time() + limite
    while time.time() < fim:
        st = json.loads(pedir(s, "GET", "/api/status")[1])
        if not st["atualizando"]:
            return st
        time.sleep(0.1)
    raise AssertionError("atualização não terminou")


def test_status_inicial(servidor):
    s = servidor()
    codigo, corpo = pedir(s, "GET", "/api/status")
    assert codigo == 200
    assert json.loads(corpo) == {"local": True, "atualizando": False, "ultimo_codigo": None,
                                 "iniciado_em": None, "terminado_em": None}


def test_post_sem_cabecalho_ou_com_host_estranho_e_proibido(servidor):
    s = servidor()
    assert pedir(s, "POST", "/api/atualizar")[0] == 403
    assert pedir(s, "POST", "/api/atualizar", {"X-Painel": "1"}, host="evil.example")[0] == 403
    assert json.loads(pedir(s, "GET", "/api/status")[1])["iniciado_em"] is None


def test_get_com_host_estranho_e_proibido(servidor):
    s = servidor()
    assert pedir(s, "GET", "/ola.txt", host="evil.example")[0] == 403
    assert pedir(s, "GET", "/api/status", host="evil.example")[0] == 403
    assert pedir(s, "GET", "/ola.txt")[0] == 200


def test_post_valido_roda_uma_vez_e_registra_codigo(servidor):
    s = servidor(codigo=3)
    codigo, corpo = pedir(s, "POST", "/api/atualizar", {"X-Painel": "1"})
    assert codigo == 202 and json.loads(corpo)["atualizando"] is True
    assert pedir(s, "POST", "/api/atualizar", {"X-Painel": "1"})[0] == 409
    st = esperar_fim(s)
    assert st["ultimo_codigo"] == 3 and st["terminado_em"] is not None


def test_localhost_tambem_aceito(servidor):
    s = servidor()
    porta = s.server_address[1]
    assert pedir(s, "POST", "/api/atualizar", {"X-Painel": "1"}, host=f"localhost:{porta}")[0] == 202
    esperar_fim(s)


def test_comando_inexistente_vira_codigo_menos_1(servidor):
    s = servidor(comando=["comando-que-nao-existe-xyz"])
    assert pedir(s, "POST", "/api/atualizar", {"X-Painel": "1"})[0] == 202
    assert esperar_fim(s)["ultimo_codigo"] == -1


def test_estaticos_e_rota_desconhecida(servidor):
    s = servidor()
    assert pedir(s, "GET", "/ola.txt") == (200, b"oi")
    assert pedir(s, "POST", "/api/outra", {"X-Painel": "1"})[0] == 404


def test_comando_atualizar():
    cmd = abrir_painel.comando_atualizar(offline=True)
    assert cmd[0] == sys.executable and cmd[1].endswith("atualizar.py") and cmd[2:] == ["--offline"]
    assert abrir_painel.comando_atualizar(offline=False)[2:] == []
