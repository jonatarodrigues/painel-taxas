"""Atualiza os dados, sobe um servidor local e abre o painel no navegador.

Uso:
    python abrir_painel.py             # atualiza os dados e abre o painel
    python abrir_painel.py --rapido    # abre com os dados já gravados, sem baixar nada
    python abrir_painel.py --offline   # recalcula só do cache e abre

Deixe esta janela aberta enquanto usa o painel; Ctrl+C encerra o servidor.
"""
from __future__ import annotations

import argparse
import functools
import json
import socket
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PORTA_PADRAO = 8765


class HandlerSilencioso(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # não poluir o console com uma linha por arquivo
        pass


def porta_livre(inicio: int, tentativas: int = 20) -> int:
    for porta in range(inicio, inicio + tentativas):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
    raise RuntimeError(f"nenhuma porta livre entre {inicio} e {inicio + tentativas - 1}")


def comando_atualizar(offline: bool) -> list[str]:
    return [sys.executable, str(RAIZ / "atualizar.py")] + (["--offline"] if offline else [])


def atualizar_dados(offline: bool) -> int:
    print("Atualizando os dados" + (" (modo offline)" if offline else "") + "...\n")
    return subprocess.call(comando_atualizar(offline), cwd=RAIZ)


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Atualizador:
    """Roda o atualizar.py em segundo plano, uma execução por vez."""

    def __init__(self, comando: list[str], cwd: Path):
        self.comando, self.cwd = comando, cwd
        self._trava = threading.Lock()
        self.atualizando = False
        self.ultimo_codigo: int | None = None
        self.iniciado_em: str | None = None
        self.terminado_em: str | None = None

    def status(self) -> dict:
        with self._trava:
            return {"local": True, "atualizando": self.atualizando, "ultimo_codigo": self.ultimo_codigo,
                    "iniciado_em": self.iniciado_em, "terminado_em": self.terminado_em}

    def iniciar(self) -> bool:
        with self._trava:
            if self.atualizando:
                return False
            self.atualizando, self.iniciado_em, self.terminado_em = True, agora(), None
        threading.Thread(target=self._rodar, daemon=True).start()
        return True

    def _rodar(self) -> None:
        try:
            codigo = subprocess.call(self.comando, cwd=self.cwd)
        except OSError:
            codigo = -1
        with self._trava:
            self.atualizando, self.ultimo_codigo, self.terminado_em = False, codigo, agora()


class HandlerPainel(HandlerSilencioso):
    """Arquivos estáticos mais as rotas /api/status e /api/atualizar."""

    def do_GET(self):
        if self.path.split("?")[0] == "/api/status":
            return self._json(200, self.server.atualizador.status())
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/api/atualizar":
            return self._json(404, {"erro": "não encontrado"})
        porta = self.server.server_address[1]
        # Um site em outra aba não consegue mandar cabeçalho próprio sem preflight de CORS (não
        # atendido aqui); o Host barra DNS rebinding.
        if self.headers.get("X-Painel") != "1" or self.headers.get("Host") not in {f"127.0.0.1:{porta}", f"localhost:{porta}"}:
            return self._json(403, {"erro": "proibido"})
        at = self.server.atualizador
        return self._json(202 if at.iniciar() else 409, at.status())

    def _json(self, codigo: int, corpo: dict) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)


def servir(porta: int, atualizador: Atualizador, raiz: Path = RAIZ) -> ThreadingHTTPServer:
    handler = functools.partial(HandlerPainel, directory=str(raiz))
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), handler)
    servidor.atualizador = atualizador
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Abre o painel de taxas.")
    ap.add_argument("--rapido", action="store_true", help="não atualiza os dados; usa dados.json existente")
    ap.add_argument("--offline", action="store_true", help="recalcula só a partir do cache, sem rede")
    ap.add_argument("--porta", type=int, default=PORTA_PADRAO, help=f"porta inicial (padrão {PORTA_PADRAO})")
    ap.add_argument("--sem-navegador", action="store_true", help="não abre o navegador (útil em testes)")
    args = ap.parse_args(argv)

    if not args.rapido:
        codigo = atualizar_dados(args.offline)
        if codigo != 0:
            print("\nA atualização falhou; abrindo o painel com os dados já gravados, se existirem.")
    if not (RAIZ / "dados.json").exists():
        print("dados.json não existe. Rode 'python atualizar.py' com internet ao menos uma vez.")
        return 1

    porta = porta_livre(args.porta)
    servidor = servir(porta, Atualizador(comando_atualizar(args.offline), RAIZ))
    url = f"http://127.0.0.1:{porta}/painel.html"
    print(f"\nPainel em {url}\nDeixe esta janela aberta; Ctrl+C encerra.")
    if not args.sem_navegador:
        webbrowser.open(url)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.shutdown()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
