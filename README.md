# Painel de Taxas de Mercado

Painel local para acompanhar juros, inflação, câmbio, exterior e bolsa com
histórico máximo, eventos que explicam os movimentos e um grafo de
correlações.

Requer Python 3.10 ou superior (desenvolvido com 3.12).

## Uso

```bash
pip install -r requirements.txt
python atualizar.py          # baixa tudo e gera dados.json / dados.js
python -m http.server 8765   # opcional
```

Abra `painel.html` (duplo clique funciona) ou `http://localhost:8765/painel.html`.
Os dados ficam todos locais, mas o painel precisa de internet na primeira
abertura para baixar o ECharts e a fonte Inter (ambos vêm de CDN).

- `python atualizar.py --offline` recalcula só do cache (`cache/`).
- Fontes: BCB SGS, FRED, Yahoo Finance e IPEA. Nenhuma chave necessária.
- `eventos.json` é a base curada de eventos; edite à vontade (data ISO,
  categoria entre `copom, fomc, crise, politica, fiscal, externo, plano`, e
  ids de séries de `pipeline/series.py`). Os ciclos do Copom são detectados
  automaticamente na série da Selic meta.
- O risco-país (EMBI+, IPEA) foi descontinuado na fonte em julho de 2024; a série fica no histórico mas sai das janelas curtas.
- Para adicionar uma série, inclua uma linha em `pipeline/series.py`.
- Na aba Séries, o modo Variação mostra a variação de cada série desde o
  início do período (em % para preços e índices, em pontos percentuais para
  taxas); Nível fica disponível quando todas as séries têm a mesma unidade.

## Testes

```bash
python -m pytest -q
```

## Como a correlação é calculada

Base mensal; juros e taxas entram como variação em pontos percentuais,
preços e índices como retorno logarítmico, inflação mensal como nível.
Pearson com no mínimo 24 meses por par, em quatro janelas (tudo, 10, 5 e
3 anos). Detalhes em `docs/superpowers/specs/2026-09-25-painel-taxas-design.md`.
