"""Catálogo das séries do painel."""
from dataclasses import dataclass

GRUPOS = {
    "juros": "Juros Brasil",
    "inflacao": "Inflação Brasil",
    "cambio": "Câmbio",
    "bolsa": "Bolsa e commodities",
    "macro": "Macro Brasil",
    "exterior": "Exterior",
}


@dataclass(frozen=True)
class Serie:
    id: str
    nome: str
    grupo: str
    fonte: str          # bcb | fred | yahoo | ipea | derivada
    codigo: str         # código na fonte; nas derivadas, ids-base separados por "-"
    unidade: str
    freq: str           # d (diária) | m (mensal)
    transformacao: str  # diff | logret | nivel (para a correlação)


SERIES = [
    Serie("selic_meta", "Selic meta", "juros", "bcb", "432", "% a.a.", "d", "diff"),
    Serie("selic_efetiva", "Selic efetiva", "juros", "bcb", "1178", "% a.a.", "d", "diff"),
    Serie("cdi", "CDI", "juros", "bcb", "4389", "% a.a.", "d", "diff"),
    Serie("ipca", "IPCA mensal", "inflacao", "bcb", "433", "% a.m.", "m", "nivel"),
    Serie("ipca15", "IPCA-15 mensal", "inflacao", "bcb", "7478", "% a.m.", "m", "nivel"),
    Serie("igpm", "IGP-M mensal", "inflacao", "bcb", "189", "% a.m.", "m", "nivel"),
    Serie("inpc", "INPC mensal", "inflacao", "bcb", "188", "% a.m.", "m", "nivel"),
    Serie("usd_brl", "Dólar (USD/BRL)", "cambio", "bcb", "1", "R$", "d", "logret"),
    Serie("eur_brl", "Euro (EUR/BRL)", "cambio", "bcb", "21619", "R$", "d", "logret"),
    Serie("ibc_br", "IBC-Br", "macro", "bcb", "24363", "índice", "m", "logret"),
    Serie("desemprego", "Desemprego (PNAD)", "macro", "bcb", "24369", "%", "m", "diff"),
    Serie("divida_pib", "Dívida bruta / PIB", "macro", "bcb", "13762", "% PIB", "m", "diff"),
    Serie("primario_pib", "Resultado primário 12m / PIB", "macro", "bcb", "5793", "% PIB", "m", "diff"),
    Serie("embi", "Risco-país (EMBI+)", "macro", "ipea", "JPM366_EMBI366", "pontos", "d", "diff"),
    Serie("fed_funds", "Fed Funds efetiva", "exterior", "fred", "DFF", "% a.a.", "d", "diff"),
    Serie("treasury_2y", "Treasury 2 anos", "exterior", "fred", "DGS2", "% a.a.", "d", "diff"),
    Serie("treasury_10y", "Treasury 10 anos", "exterior", "fred", "DGS10", "% a.a.", "d", "diff"),
    Serie("cpi_eua", "CPI EUA", "exterior", "fred", "CPIAUCSL", "índice", "m", "logret"),
    Serie("dxy", "Índice dólar (DXY)", "exterior", "fred", "DTWEXBGS", "índice", "d", "logret"),
    Serie("vix", "VIX", "exterior", "fred", "VIXCLS", "pontos", "d", "diff"),
    Serie("petroleo", "Petróleo WTI", "bolsa", "fred", "DCOILWTICO", "USD", "d", "logret"),
    Serie("ibovespa", "Ibovespa", "bolsa", "yahoo", "^BVSP", "pontos", "d", "logret"),
    Serie("sp500", "S&P 500", "bolsa", "yahoo", "^GSPC", "pontos", "d", "logret"),
    Serie("ouro", "Ouro", "bolsa", "yahoo", "GC=F", "USD/oz", "d", "logret"),
]

DERIVADAS = [
    Serie("ipca_12m", "IPCA 12 meses", "inflacao", "derivada", "ipca", "% 12m", "m", "diff"),
    Serie("igpm_12m", "IGP-M 12 meses", "inflacao", "derivada", "igpm", "% 12m", "m", "diff"),
    Serie("juro_real", "Juro real (Selic − IPCA 12m)", "juros", "derivada", "selic_meta-ipca_12m", "p.p.", "m", "diff"),
    Serie("dif_selic_fed", "Diferencial Selic − Fed Funds", "juros", "derivada", "selic_meta-fed_funds", "p.p.", "m", "diff"),
    Serie("curva_eua", "Inclinação curva EUA (10a − 2a)", "exterior", "derivada", "treasury_10y-treasury_2y", "p.p.", "m", "diff"),
]

POR_ID = {s.id: s for s in SERIES + DERIVADAS}
