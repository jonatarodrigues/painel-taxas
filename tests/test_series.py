from pipeline.series import DERIVADAS, GRUPOS, POR_ID, SERIES


def test_ids_unicos():
    ids = [s.id for s in SERIES + DERIVADAS]
    assert len(ids) == len(set(ids))


def test_campos_validos():
    for s in SERIES + DERIVADAS:
        assert s.grupo in GRUPOS
        assert s.fonte in {"bcb", "fred", "yahoo", "ipea", "derivada"}
        assert s.freq in {"d", "m"}
        assert s.transformacao in {"diff", "logret", "nivel"}


def test_derivadas_referenciam_series_existentes():
    for d in DERIVADAS:
        for base in d.codigo.split("-"):
            assert base in POR_ID, base


def test_catalogo_tem_as_series_da_spec():
    for id in ["selic_meta", "cdi", "ipca", "usd_brl", "fed_funds", "ibovespa", "sp500", "embi"]:
        assert id in POR_ID
