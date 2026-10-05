"""Baixa as séries, recalcula correlações e grava dados.json / dados.js.

Uso:
    python atualizar.py            # baixa tudo (usa cache se alguma fonte falhar)
    python atualizar.py --offline  # recalcula só a partir do cache
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline import agenda, bolsa, correlacao, exportar, focus, fontes, transformar
from pipeline.cache import Cache, obter
from pipeline.ciclos import ciclos_copom
from pipeline.series import DERIVADAS, POR_ID, SERIES

RAIZ = Path(__file__).resolve().parent

ORDEM_STATUS = {"ok": 0, "desatualizada": 1, "ausente": 2}

CATEGORIAS_EVENTO = {"copom", "fomc", "crise", "politica", "fiscal", "externo", "plano"}
RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def carregar_eventos(arquivo: Path, avisos: list[str]) -> list[dict]:
    """Lê eventos.json; JSON quebrado ou eventos malformados viram avisos, nunca exceção."""
    if not arquivo.exists():
        avisos.append(f"eventos.json não encontrado em {arquivo.parent}; painel sem eventos curados")
        return []
    try:
        brutos = json.loads(arquivo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        avisos.append(f"eventos.json inválido ({e}); painel sem eventos curados")
        return []
    if not isinstance(brutos, list):
        avisos.append("eventos.json inválido (esperava uma lista); painel sem eventos curados")
        return []
    validos, rejeitados = [], []
    for e in brutos:
        ok = (isinstance(e, dict)
              and isinstance(e.get("data"), str) and RE_DATA.match(e["data"])
              and isinstance(e.get("titulo"), str) and e["titulo"].strip()
              and isinstance(e.get("descricao"), str)
              and e.get("categoria") in CATEGORIAS_EVENTO
              and isinstance(e.get("series"), list) and e["series"]
              and all(isinstance(s, str) and s in POR_ID for s in e["series"]))
        if ok:
            validos.append(e)
        else:
            rejeitados.append(str(e.get("titulo", e.get("data", "?"))) if isinstance(e, dict) else "?")
    if rejeitados:
        avisos.append(f"eventos.json: {len(rejeitados)} evento(s) ignorado(s) por formato inválido: " + "; ".join(rejeitados[:5]) + (" …" if len(rejeitados) > 5 else ""))
    return validos


def status_derivada(id: str, status: dict[str, str]) -> str:
    """Pior status entre as séries-base de uma derivada."""
    bases = POR_ID[id].codigo.split("-")
    return max((status.get(b, "ausente") for b in bases), key=ORDEM_STATUS.__getitem__)


def valor_dezembro(mensal: pd.Series | None, ano: int) -> float | None:
    """Valor mensal de dezembro de `ano` (o IPCA 12 meses fechado do ano)."""
    if mensal is None:
        return None
    for i, v in mensal.dropna().items():
        if str(i)[:7] == f"{ano}-12":
            return float(v)
    return None


def ultimo_do_ano(serie: pd.Series | None, ano: int) -> float | None:
    """Último valor observado em `ano` (o fechamento do dólar)."""
    if serie is None:
        return None
    s = serie.dropna()
    s = s[s.index.year == ano]
    return float(s.iloc[-1]) if len(s) else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Atualiza os dados do painel de taxas.")
    ap.add_argument("--offline", action="store_true", help="recalcula só a partir do cache, sem rede")
    ap.add_argument("--pasta", default=str(RAIZ), help="pasta de saída (padrão: pasta do script)")
    args = ap.parse_args(argv)
    pasta = Path(args.pasta)
    cache = Cache(pasta / "cache")

    brutas, status, avisos = {}, {}, []
    for serie in SERIES:
        s, st, aviso = obter(serie, cache, offline=args.offline, baixar=fontes.baixar)
        status[serie.id] = st
        if aviso:
            avisos.append(aviso)
        if s is not None and not s.empty:
            brutas[serie.id] = s
            periodo = f"{s.index.min():%Y-%m-%d} -> {s.index.max():%Y-%m-%d} ({len(s)} pts)"
        else:
            periodo = "-"
        print(f"[{st:13}] {serie.nome:34} {periodo}")

    if args.offline:
        offline = [a for a in avisos if "modo offline" in a]
        if offline:
            datas = sorted(re.findall(r"\d{4}-\d{2}-\d{2}", " ".join(offline)))
            avisos = [a for a in avisos if "modo offline" not in a]
            if datas:
                avisos.insert(0, f"Modo offline: {len(offline)} séries lidas do cache (mais antigo de {datas[0]})")
            else:
                avisos.insert(0, f"Modo offline: {len(offline)} séries sem cache disponível")

    diarias = {id: transformar.para_diaria(s) for id, s in brutas.items() if POR_ID[id].freq == "d"}
    mensais = {id: transformar.para_mensal(s, POR_ID[id].freq) for id, s in brutas.items()}
    for id, s in transformar.derivadas(mensais).items():
        mensais[id] = s
        status[id] = status_derivada(id, status)
    transformadas = {id: transformar.transformar(m, POR_ID[id].transformacao)
                     for id, m in mensais.items() if not m.empty}
    correl = correlacao.calcular(transformadas)

    eventos = carregar_eventos(pasta / "eventos.json", avisos)
    if "selic_meta" in brutas:
        eventos = eventos + ciclos_copom(brutas["selic_meta"])

    hoje = date.today()
    bruto_focus, aviso_focus = focus.obter(pasta / "cache" / "focus.json", args.offline, hoje, baixar=focus.baixar)
    if aviso_focus:
        avisos.append(aviso_focus)
    agenda_ = agenda.carregar(pasta / "agenda.json", avisos)

    def ultimo(id: str) -> float | None:
        return float(brutas[id].dropna().iloc[-1]) if id in brutas and not brutas[id].dropna().empty else None

    jr = mensais.get("juro_real")
    juro_hist = [] if jr is None else [float(v) for i, v in jr.dropna().items() if str(i)[:4] >= "2000"]
    selic_serie = brutas["selic_meta"].dropna() if "selic_meta" in brutas else None
    selic_data = None if selic_serie is None or selic_serie.empty else str(selic_serie.index[-1])[:10]
    prev = exportar.previsoes(bruto_focus, agenda_, ultimo("selic_meta"), selic_data, ultimo("usd_brl"),
                              ultimo("fed_funds"), juro_hist, hoje, avisos,
                              ipca_dez_anterior=valor_dezembro(mensais.get("ipca_12m"), hoje.year - 1),
                              usd_fim_anterior=ultimo_do_ano(brutas.get("usd_brl"), hoje.year - 1))

    try:
        bloco_bolsa = bolsa.obter(pasta, args.offline, avisos)
    except Exception as e:  # a aba Bolsa nunca derruba a atualização das séries
        avisos.append(f"Bolsa: falha ao montar a aba ({e})")
        bloco_bolsa = None

    metas = {s.id: s for s in SERIES + DERIVADAS}
    dados = exportar.montar(metas, diarias, mensais, status, avisos, correl, eventos, previsoes=prev, bolsa=bloco_bolsa)
    exportar.gravar(dados, pasta)

    n_arestas = sum(len(a) for a in dados["arestas"].values())
    print(f"\n{len(dados['series'])} séries, {len(dados['eventos'])} eventos, {n_arestas} arestas. "
          f"Avisos: {len(avisos)}")
    for a in avisos:
        print("  !", a)
    print(f"Gravado em {pasta / 'dados.json'}")
    return 0 if any(st in ("ok", "desatualizada") for st in status.values()) else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
