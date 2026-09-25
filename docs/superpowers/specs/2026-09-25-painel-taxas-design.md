# Painel de Taxas de Mercado — Design

Data: 2026-09-25

## 1. Objetivo

Painel web local para acompanhar taxas e indicadores de mercado (juros Brasil,
inflação, câmbio, exterior e bolsas) com o máximo de histórico disponível,
eventos macro que explicam os movimentos, e um grafo de rede ("cérebro")
que mostra como as variáveis se correlacionam entre si.

Uso pessoal, aberto no navegador a partir de um arquivo local. Sem servidor,
sem login, sem chave de API. Dados atualizados por um script Python que o
usuário roda quando quiser.

## 2. Séries

| Grupo | Série | Código | Início | Fonte |
|---|---|---|---|---|
| Juros | Selic meta (% a.a.) | SGS 432 | 1999 | BCB |
| Juros | Selic efetiva diária (% a.a.) | SGS 1178 | 1986 | BCB |
| Juros | CDI diário (% a.a.) | SGS 4389 | 1986 | BCB |
| Inflação | IPCA mensal (%) | SGS 433 | 1980 | BCB |
| Inflação | IPCA-15 mensal (%) | SGS 7478 | 2000 | BCB |
| Inflação | IGP-M mensal (%) | SGS 189 | 1989 | BCB |
| Inflação | INPC mensal (%) | SGS 188 | 1979 | BCB |
| Câmbio | USD/BRL PTAX venda | SGS 1 | 1984 | BCB |
| Câmbio | EUR/BRL PTAX venda | SGS 21619 | 1999 | BCB |
| Atividade | IBC-Br (índice) | SGS 24363 | 2003 | BCB |
| Atividade | Desemprego PNAD (%) | SGS 24369 | 2012 | BCB |
| Fiscal | Dívida bruta / PIB (%) | SGS 13762 | 2006 | BCB |
| Fiscal | Resultado primário 12m / PIB (%) | SGS 5793 | 1991 | BCB |
| Risco | EMBI+ Brasil (pontos) | IPEA JPM366_EMBI366 | 1994 | IPEA |
| Exterior | Fed Funds efetiva (%) | FRED DFF | 1954 | FRED |
| Exterior | Treasury 2 anos (%) | FRED DGS2 | 1976 | FRED |
| Exterior | Treasury 10 anos (%) | FRED DGS10 | 1962 | FRED |
| Exterior | CPI EUA (índice) | FRED CPIAUCSL | 1947 | FRED |
| Exterior | Petróleo WTI (USD) | FRED DCOILWTICO | 1986 | FRED |
| Exterior | Índice dólar DXY | FRED DTWEXBGS | 2006 | FRED |
| Exterior | VIX | FRED VIXCLS | 1990 | FRED |
| Bolsa | Ibovespa (pontos) | Yahoo ^BVSP | 1993 | Yahoo Finance |
| Bolsa | S&P 500 (pontos) | Yahoo ^GSPC | 1927 | Yahoo Finance |
| Bolsa | Ouro (USD/oz) | Yahoo GC=F | 2000 | Yahoo Finance |

Grupos usados no painel (6, para caber numa paleta categórica validada):
`juros`, `inflacao`, `cambio`, `bolsa` (bolsas, petróleo e ouro), `macro`
(atividade, fiscal e risco-país) e `exterior`.

Nota: o Stooq, previsto na primeira versão, passou a bloquear downloads com
desafio JavaScript. O Yahoo Finance (endpoint `v8/finance/chart`) responde
sem chave quando enviado um `User-Agent` de navegador e cobre as três séries.

Séries derivadas calculadas no pipeline:
- IPCA acumulado 12 meses (%).
- IGP-M acumulado 12 meses (%).
- Juro real ex-post: Selic meta menos IPCA 12m.
- Diferencial de juros: Selic meta menos Fed Funds.
- Inclinação da curva EUA: Treasury 10y menos 2y.

Total: em torno de 29 variáveis.

Endpoints (todos públicos, sem chave):
- BCB SGS: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial=dd/mm/aaaa&dataFinal=dd/mm/aaaa`. Para séries diárias, a API limita a 10 anos por chamada; o pipeline faz chamadas em janelas de 10 anos.
- FRED: `https://fred.stlouisfed.org/graph/fredgraph.csv?id={codigo}`.
- Yahoo: `https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1=-2208988800&period2={agora}&interval=1d` (exige header `User-Agent`).
- IPEA: `http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{codigo}')`.

Comportamentos confirmados das fontes:
- BCB responde `404` quando a janela pedida não tem dados (ex.: Selic meta
  antes de 1999). O pipeline trata 404 como janela vazia, não como erro.
- A série 432 (Selic meta) vem preenchida até a data da próxima reunião do
  Copom, ou seja, com datas futuras. O pipeline corta em "hoje".
- Petróleo WTI teve preço negativo em 20/04/2020. O retorno logarítmico
  ignora valores não positivos.

## 3. Pipeline (Python)

Entrada: lista de séries em `pipeline/series.py` (código, nome, grupo, fonte,
unidade, tipo de transformação). Saída: `dados.json`.

Módulos:
- `pipeline/fontes.py`: uma função por fonte (`bcb`, `fred`, `yahoo`, `ipea`),
  cada uma retornando `pd.Series` indexada por data com nome igual ao id da
  série. Baixa com `requests`, timeout 30 s, 3 tentativas.
- `pipeline/cache.py`: grava e lê `cache/{id}.csv`. Se o download falha, usa
  o cache e registra a série como "desatualizada". Se não há cache nem
  download, a série é marcada "ausente" e excluída dos cálculos.
- `pipeline/transformar.py`: gera a tabela diária (forward-fill até 5 dias
  úteis) e a mensal (último valor do mês para diárias; valor do mês para
  mensais), as séries derivadas e as transformações para correlação.
- `pipeline/correlacao.py`: matrizes de correlação de Pearson para quatro
  janelas (`tudo`, `10a`, `5a`, `3a`), mais a lista de arestas do grafo.
- `pipeline/ciclos.py`: detecta na própria série 432 cada virada de direção
  da Selic meta (alta para baixa ou baixa para alta) e gera um evento
  `copom` automático por virada, com `"auto": true`. Assim os ciclos do Copom
  ficam sempre corretos e atualizados sem edição manual.
- `pipeline/exportar.py`: monta o JSON final.
- `atualizar.py`: orquestra tudo e imprime resumo (séries ok, desatualizadas,
  ausentes, período de cada uma).

Transformações para correlação (coluna `transformacao` em `series.py`):
- `diff`: variação mensal em pontos percentuais. Juros, Treasuries, Fed Funds,
  desemprego, dívida/PIB, primário, EMBI, VIX, juro real, diferenciais.
- `logret`: retorno logarítmico mensal. Câmbio, bolsas, petróleo, ouro, DXY,
  IBC-Br, CPI EUA.
- `nivel`: valor mensal usado direto. IPCA, IPCA-15, IGP-M, INPC.

Regras de correlação:
- Mínimo de 24 meses de sobreposição por par. Abaixo disso, o valor é `null`.
- A matriz de cada janela usa apenas os meses dentro da janela contados a
  partir do último mês disponível. A janela curta é de 36 meses (não 24):
  com janela igual ao mínimo de 24 meses, qualquer série mensal com um mês
  de defasagem de publicação (IPCA, IGP-M, IBC-Br, CPI, fiscais) ficava de
  fora, como se viu nos dados reais (17 de 29 séries).
- Arestas do grafo: todos os pares com `|r| >= 0.15` entram no JSON; o corte
  visual é feito no painel pelo slider (padrão 0,30). Cada aresta carrega
  `r`, `n` (meses) e a janela.

## 4. Formato do `dados.json`

```json
{
  "gerado_em": "2026-09-25T16:00:00",
  "series": {
    "selic_meta": {
      "nome": "Selic meta", "grupo": "juros", "unidade": "% a.a.",
      "fonte": "BCB SGS 432", "inicio": "1999-03-05", "fim": "2026-09-24",
      "status": "ok", "transformacao": "diff", "freq": "d",
      "ultimo": 15.0, "var_tipo": "pp", "var_1m": 0.0, "var_12m": 4.25,
      "diario": [["1999-03-05", 45.0]],
      "mensal": [["1999-03", 45.0]]
    }
  },
  "correlacao": {
    "tudo": {"ids": ["selic_meta"], "matriz": [[1]], "n": [[320]]},
    "10a": {}, "5a": {}, "3a": {}
  },
  "arestas": {
    "tudo": [{"a": "selic_meta", "b": "cdi", "r": 0.98, "n": 320}],
    "10a": [], "5a": [], "3a": []
  },
  "eventos": [],
  "avisos": ["FRED DGS2: usando cache de 2026-09-10"]
}
```

Séries diárias são gravadas apenas para as fontes diárias; séries mensais
têm `diario` vazio. Valores nulos são omitidos das listas. `var_tipo` é
`"pct"` (variação percentual) para séries `logret` e `"pp"` (diferença em
pontos) para as demais. `n` é a matriz de meses em comum de cada par.

## 5. Eventos (`eventos.json`)

Arquivo curado manualmente, editável. Cerca de 100 entradas de 1986 até
hoje. Cada evento:

```json
{
  "data": "2008-09-15",
  "titulo": "Quebra do Lehman Brothers",
  "categoria": "crise",
  "descricao": "Falência do banco detona a fase aguda da crise financeira global. Dólar salta de 1,60 para 2,40 em dez semanas; BC vende reservas e cria linhas em dólar.",
  "series": ["usd_brl", "ibovespa", "sp500", "embi", "vix"]
}
```

Categorias: `copom`, `fomc`, `crise`, `politica`, `fiscal`, `externo`,
`plano`. Ciclos do Copom entram como um evento por início de ciclo (alta ou
baixa), não por reunião, para não poluir o gráfico; esses são gerados
automaticamente por `pipeline/ciclos.py` a partir da série 432 e recebem
`"auto": true`. O arquivo curado cobre o restante (crises, planos, eleições,
decisões do Fed, choques externos e marcos fiscais).

O painel calcula, para cada evento, a variação das séries listadas em
`series` 30 e 90 dias depois, usando a tabela diária (ou mensal quando a
série não tem diária).

## 6. Painel (`painel.html`)

Página única, sem build: `painel.html` + `painel.css` + `painel.js` (três
arquivos para manter cada um legível; nenhum passo de compilação).
Dependências carregadas de CDN: Apache ECharts 5 (cdn.jsdelivr.net). Fonte:
Inter via Google Fonts. Tema escuro padrão com alternância para claro,
lembrada em `localStorage` (leitura e escrita protegidas por try/catch).
Carrega `dados.json` via `fetch` quando servido por http; aberto por
`file://`, usa o fallback `dados.js` (`window.DADOS = {...}`), que o script
`atualizar.py` também gera, para abrir com duplo clique.

Layout:

1. **Topo**: título, data de atualização, avisos, seletor de tema.
2. **Cartões KPI** (6): Selic meta, CDI, IPCA 12m, USD/BRL, Fed Funds,
   Ibovespa. Cada um com valor, variação 1m e 12m e sparkline de 2 anos.
3. **Aba Séries**: seletor múltiplo de variáveis agrupado por grupo (até 8
   ao mesmo tempo), gráfico de linhas com **um único eixo Y** em dois modos:
   `Variação` (variação de cada série desde o início do período: em % para
   preços e índices, em pontos percentuais para taxas e inflação; eixo
   centrado em zero) e `Nível` (disponível só quando todas as séries
   selecionadas têm a mesma unidade; com unidades mistas o painel força
   Variação e avisa). O modo "Base 100" da primeira versão foi descartado
   porque 8 das 29 séries cruzam zero e o rebase explodia. Atalhos de período
   1a / 5a / 10a / 20a / tudo e dataZoom. Eventos aparecem numa **faixa
   própria abaixo do gráfico**, alinhada ao mesmo eixo de tempo, com um
   ponto por evento colorido pela categoria e filtrável por categoria;
   passar o mouse mostra o título e a descrição, clicar abre um cartão com
   a variação 30/90 dias das séries afetadas. Eixo duplo foi descartado
   porque induz leitura errada de escala.
4. **Aba Cérebro**: gráfico `graph` do ECharts com layout `force`. Nó: cor
   por grupo, tamanho proporcional à soma de |r| das arestas visíveis.
   Aresta: espessura proporcional a |r|, azul para positiva, vermelho para
   negativa (par divergente azul/vermelho com cinza neutro, o mesmo do
   heatmap). Controles: janela (tudo/10a/5a/3a), slider de |r| mínimo
   (0,15 a 0,9, padrão 0,30), filtro por grupo. Clicar em nó destaca
   vizinhos e abre um painel lateral com a lista de correlações daquele nó
   ordenada por |r|.
5. **Aba Correlações**: heatmap da matriz completa, com a mesma escolha de
   janela, ordenado por grupo, tooltip com r e n, célula vazia quando o par
   tem menos de 24 meses em comum (legenda explica).
6. **Aba Linha do tempo**: lista vertical de eventos (curados e
   automáticos) com filtro por categoria e busca por texto; cada card mostra
   a data, título, descrição e a tabela de variação 30/90 dias das séries
   afetadas.

Visual: tema escuro com fundo `#0f1117`, cartões `#1a1d27`, texto `#e6e8ef`;
tema claro com fundo `#f4f5f8`, cartões `#ffffff`, texto `#0b0b0b`. Paleta
categórica de grupos validada para daltonismo nos dois temas (validador da
skill dataviz, todos os checks PASS):

| Grupo | Claro | Escuro |
|---|---|---|
| juros | `#2a78d6` | `#3987e5` |
| inflacao | `#eb6834` | `#d95926` |
| cambio | `#1baf7a` | `#199e70` |
| bolsa | `#eda100` | `#c98500` |
| macro | `#e87ba4` | `#d55181` |
| exterior | `#008300` | `#008300` |

As linhas da aba Séries usam os 8 slots categóricos da mesma paleta na
ordem de seleção. Correlação positiva/negativa e variações com sinal usam o
par divergente azul/vermelho. Layout responsivo com grade CSS, mínimo
360 px.

## 7. Tratamento de erros

- Falha de uma fonte não derruba o script: série vai para cache ou é
  marcada ausente, e o aviso aparece no JSON e no painel.
- Séries com menos de 24 meses são excluídas da correlação mas continuam
  nos gráficos de linha.
- O painel valida a presença de `series`, `correlacao`, `arestas` e
  `eventos`; se faltar, mostra mensagem de erro em vez de tela em branco.
- `atualizar.py --offline` recalcula tudo só do cache, sem rede.

## 8. Testes

`pytest` em `tests/`:
- `test_transformar.py`: diária para mensal, forward-fill limitado, as três
  transformações, séries derivadas.
- `test_correlacao.py`: sobreposição mínima produz `null`, janelas cortam
  corretamente, arestas respeitam o corte de 0,15, simetria da matriz.
- `test_exportar.py`: JSON gerado bate com o formato da seção 4 e não tem
  `NaN`.
- `test_fontes.py`: parsers de cada fonte com respostas gravadas em
  `tests/fixtures/` (sem rede); janelas de 10 anos do BCB e corte de datas
  futuras testados com um `_get` falso.
- `test_ciclos.py`: viradas de direção da Selic geram um evento cada, sem
  evento para continuações de ciclo.

O painel é verificado manualmente no navegador com o JSON real e com um
JSON reduzido de fixture.

## 9. Fora de escopo

- Previsão de taxas (o nome da pasta é "Previsao", mas isso fica para uma
  etapa seguinte, quando o histórico estiver montado).
- Notícias automáticas, DI futuro da B3 (exige scraping), agendamento.
- Exportar para Power BI.

## 10. Estrutura de arquivos

```
Previsao/
  atualizar.py
  requirements.txt
  pipeline/
    __init__.py
    series.py
    fontes.py
    cache.py
    transformar.py
    correlacao.py
    ciclos.py
    exportar.py
  eventos.json
  painel.html
  painel.css
  painel.js
  README.md
  dados.json          (gerado)
  dados.js            (gerado)
  cache/              (gerado)
  tests/
    fixtures/
    test_transformar.py
    test_correlacao.py
    test_exportar.py
    test_fontes.py
  docs/superpowers/specs/2026-09-25-painel-taxas-design.md
```
