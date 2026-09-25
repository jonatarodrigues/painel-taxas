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
import socket
import subprocess
import sys
import threading
import webbrowser
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


def atualizar_dados(offline: bool) -> int:
    comando = [sys.executable, str(RAIZ / "atualizar.py")] + (["--offline"] if offline else [])
    print("Atualizando os dados" + (" (modo offline)" if offline else "") + "...\n")
    return subprocess.call(comando, cwd=RAIZ)


def servir(porta: int) -> ThreadingHTTPServer:
    handler = functools.partial(HandlerSilencioso, directory=str(RAIZ))
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), handler)
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
    servidor = servir(porta)
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
