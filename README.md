# Painel de Taxas de Mercado

[![publicar](https://github.com/jonatarodrigues/painel-taxas/actions/workflows/publicar.yml/badge.svg)](https://github.com/jonatarodrigues/painel-taxas/actions/workflows/publicar.yml)

**Ao vivo:** https://jonatarodrigues.github.io/painel-taxas/

Painel para acompanhar juros, inflação, câmbio, exterior e bolsa com
histórico máximo, eventos que explicam os movimentos, um grafo de
correlações e o consenso do mercado (Boletim Focus), incluindo a comparação
entre o que o mercado previa há 12 meses e o que aconteceu.

**Para ver funcionando, basta abrir o link acima** — não é preciso baixar
nada. Os dados são atualizados automaticamente em dias úteis às 20h.

## Rodar no seu computador

Requer Python 3.10 ou superior (desenvolvido com 3.12).

```bash
pip install -r requirements.txt
python abrir_painel.py            # atualiza os dados e abre o painel no navegador
python abrir_painel.py --rapido   # abre com os dados já gravados, sem baixar nada
```

- A atualização leva de alguns minutos a uns 15 (depende do BCB). Deixe o
  terminal aberto enquanto usa o painel; `Ctrl+C` encerra o servidor.
- Opções: `--offline` (recalcula só do cache), `--porta N`.
- Com o painel aberto assim, o botão ⟳ no topo roda a atualização de novo
  sem fechar nada. No site publicado, o mesmo botão só busca os dados mais
  recentes que já foram publicados.
- O navegador não consegue executar Python a partir do `painel.html`, por
  isso a atualização acontece no `abrir_painel.py`, que também serve a
  página.

Também dá para rodar as etapas separadas: `python atualizar.py` baixa tudo e
gera `dados.json`/`dados.js`, e o `painel.html` abre direto do disco. O
painel precisa de internet na primeira abertura para baixar o ECharts e a
fonte Inter (ambos vêm de CDN).

## Detalhes

- `python atualizar.py --offline` recalcula só do cache (`cache/`).
- Fontes: BCB SGS, Boletim Focus (BCB), FRED, Yahoo Finance e IPEA. Nenhuma chave necessária.
  Se a variável de ambiente `FRED_API_KEY` existir, o FRED é lido pela API
  oficial em vez do CSV público; o workflow de publicação usa o segredo
  `FRED_API_KEY`, porque o CSV não responde a IPs de nuvem.
- `eventos.json` é a base curada de eventos; edite à vontade (data ISO,
  categoria entre `copom, fomc, crise, politica, fiscal, externo, plano`, e
  ids de séries de `pipeline/series.py`). Os ciclos do Copom são detectados
  automaticamente na série da Selic meta.
- O risco-país (EMBI+, IPEA) foi descontinuado na fonte em julho de 2024; a série fica no histórico mas sai das janelas curtas.
- Para adicionar uma série, inclua uma linha em `pipeline/series.py`.
- Na aba Séries, o modo Variação mostra a variação de cada série desde o
  início do período (em % para preços e índices, em pontos percentuais para
  taxas); Nível fica disponível quando todas as séries têm a mesma unidade.

## Aba Previsões

Mostra o consenso do mercado segundo o Boletim Focus do BCB (mediana,
menor e maior projeção entre as instituições), sinais calculados a partir
dele e a agenda de Copom, FOMC e IPCA. Os sinais descrevem fatos; não são
recomendação de investimento.

- O Focus é baixado junto com as séries e fica em `cache/focus.json`; se a
  consulta falhar, o painel usa o cache e avisa.
- `agenda.json` guarda as datas (dia do anúncio). Quando o BCB e o Fed
  publicarem o calendário de um novo ano, acrescente as linhas no mesmo
  formato: `{"data": "2028-01-26", "tipo": "copom", "titulo": "Copom", "reuniao": "R1/2028"}`.
  Tipos: `copom` (com `reuniao`), `fomc` e `ipca`. Enquanto faltar a data de
  uma reunião que o Focus já projeta, o painel avisa e deixa essa reunião
  fora do gráfico.
- Regras dos sinais e limites: `pipeline/sinais.py` e
  `docs/superpowers/specs/2026-09-30-previsoes-design.md`.

## Aba Bolsa

Mostra como foram as ações do Ibovespa e os fundos do IFIX no dia, na
semana, no mês, no ano e em 12 meses: mapa por setor (tamanho = peso no
índice, cor = retorno), maiores altas e baixas, retorno por setor e o
gráfico de cada ativo. Os retornos incluem proventos (`adjclose` do Yahoo
Finance), e a carteira de cada índice vem da B3 a cada atualização.

- A B3 não informa o tipo dos FIIs. Eles ficam em `fiis.json`
  (`"HGLG11": "Logística"`), com os tipos listados em `_tipos`. Fundo novo no
  IFIX sem tipo entra em "Outros", e o painel avisa para classificar.
- Carteiras em `cache/carteiras.json` e preços em `cache/bolsa/`. Se a B3 ou
  o Yahoo falharem, o painel usa o cache e avisa.
- Retorno do IFIX vem do ETF `XFIX11.SA` (replica o IFIX, reinveste
  distribuições), pois o Yahoo não tem histórico para `IFIX.SA`.
- Regras de cálculo: `pipeline/bolsa.py` e
  `docs/superpowers/specs/2026-10-05-aba-bolsa-design.md`.

## Publicação

O workflow `.github/workflows/publicar.yml` roda os testes, executa o
`atualizar.py` e publica o painel no GitHub Pages em dias úteis às 20h
(horário de Brasília), a cada push na `main` e quando disparado à mão
(Actions → publicar → Run workflow). O `cache/` das fontes é guardado entre
execuções; se uma fonte falhar, a série usa o último dado bom e aparece nos
avisos. Só `painel.html`, `painel.css`, `painel.js`, `dados.js`,
`dados.json`, a página inicial e a imagem de prévia do link (`site/og.png`)
vão para o site.

O GitHub desativa workflows agendados em repositórios sem atividade por 60
dias. Se o site parar de atualizar, reative em Actions → publicar →
Enable workflow (ou faça qualquer push).

## Testes

```bash
python -m pytest -q
```

## Como a correlação é calculada

Base mensal; juros e taxas entram como variação em pontos percentuais,
preços e índices como retorno logarítmico, inflação mensal como nível.
Pearson com no mínimo 24 meses por par, em quatro janelas (tudo, 10, 5 e
3 anos). Detalhes em `docs/superpowers/specs/2026-09-25-painel-taxas-design.md`.
