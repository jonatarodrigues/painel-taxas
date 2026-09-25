"""Cache CSV por série e obtenção com fallback."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from pipeline import fontes
from pipeline.series import Serie


class Cache:
    def __init__(self, pasta: Path | str):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)

    def caminho(self, id: str) -> Path:
        return self.pasta / f"{id}.csv"

    def gravar(self, id: str, s: pd.Series) -> None:
        s.rename("valor").rename_axis("data").to_csv(self.caminho(id), date_format="%Y-%m-%d")

    def ler(self, id: str) -> pd.Series | None:
        p = self.caminho(id)
        if not p.exists():
            return None
        df = pd.read_csv(p, parse_dates=["data"], index_col="data")
        s = df["valor"].astype(float)
        s.index = pd.DatetimeIndex(s.index, name="data")
        return s

    def modificado_em(self, id: str) -> datetime | None:
        p = self.caminho(id)
        return datetime.fromtimestamp(p.stat().st_mtime) if p.exists() else None


Resultado = tuple[pd.Series | None, str, str | None]


def obter(serie: Serie, cache: Cache, offline: bool = False,
          baixar: Callable[[Serie], pd.Series] = fontes.baixar) -> Resultado:
    """Retorna (serie, status, aviso). status: ok | desatualizada | ausente."""
    if offline:
        s = cache.ler(serie.id)
        if s is None:
            return None, "ausente", f"{serie.nome}: sem cache (modo offline)"
        quando = cache.modificado_em(serie.id)
        return s, "desatualizada", f"{serie.nome}: modo offline, usando cache de {quando:%Y-%m-%d}"
    try:
        s = baixar(serie)
        if s is None or s.empty:
            raise fontes.RespostaVazia("resposta vazia")
        cache.gravar(serie.id, s)
        return s, "ok", None
    except Exception as e:  # rede, parsing ou vazio: qualquer falha cai no cache
        s = cache.ler(serie.id)
        if s is not None:
            quando = cache.modificado_em(serie.id)
            return s, "desatualizada", f"{serie.nome}: falha ao baixar ({e}); usando cache de {quando:%Y-%m-%d}"
        return None, "ausente", f"{serie.nome}: falha ao baixar ({e}) e sem cache"
