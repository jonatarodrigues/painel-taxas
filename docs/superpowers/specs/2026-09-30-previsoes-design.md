# Aba Previsões: consenso do mercado, sinais e agenda

Data: 2026-09-30
Estado: aprovado em conversa; protótipo visto com dados reais do Focus de 2026-09-25.

## Objetivo

Ajudar a decidir investimentos (travar prefixado ou IPCA+, comprar dólar)
mostrando o que o mercado espera para juros, inflação, câmbio e PIB, o que
mudou nessas expectativas e quais eventos vêm pela frente.

### Decisões tomadas

- A fonte das previsões é o **consenso do mercado** (Boletim Focus do BCB),
  não um modelo estatístico próprio.
- Os "alertas" são **sinais calculados a partir dos dados**. Manchetes de
  notícias (RSS) ficam fora desta etapa.
- Os sinais descrevem fatos e contexto. Nunca dizem "compre" ou "venda".
- Os dados são baixados pelo `atualizar.py`, como as demais séries. Nada roda
  no navegador além do desenho.

### Fora do escopo

- Notícias e RSS.
- Indicadores do Focus além de IPCA, Câmbio, PIB Total e Selic.
- Histórico do Focus anterior a 12 semanas.
- Previsões mensais (`ExpectativaMercadoMensais`).

## Dados

### Fonte: API Olinda de Expectativas

Base: `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata`

| Entidade | Filtro | Uso |
|---|---|---|
| `ExpectativasMercadoSelic` | `baseCalculo eq 0`, pesquisa mais recente | Selic esperada por reunião (`Reuniao` = `"R7/2026"`) |
| `ExpectativasMercadoAnuais` | `baseCalculo eq 0`, `Indicador` em IPCA, Câmbio, PIB Total, Selic; `DataReferencia` do ano atual até o atual + 3; `Data` nas últimas 13 semanas | Trajetória anual e sinais de revisão |
| `ExpectativasMercadoInflacao12Meses` | `Indicador eq 'IPCA'`, `Suavizada eq 'S'`, `baseCalculo eq 0`, mais recente | Juro real esperado |

Campos usados: `Data`, `DataReferencia` ou `Reuniao`, `Mediana`, `Minimo`,
`Maximo` e `numeroRespondentes`.

**Armadilhas vistas no protótipo:**
- O `$filter` precisa de espaços codificados como `%20`. O `requests` com
  `params=` codifica espaço como `+`, e o Olinda responde 400 ("The types
  'Edm.Boolean' and 'Edm.String' are not compatible"). Por isso a query string
  é montada com `urllib.parse.quote(..., safe='')`.
- As chamadas usam `_get(..., json=True)`, que repete a tentativa quando o BCB
  devolve HTML com status 200.
- A tabela anual tem uma linha por dia útil. A série semanal usa a última
  linha de cada semana (período `W-FRI`).

### Arquivo curado `agenda.json`

Lista de objetos, no mesmo espírito do `eventos.json`:

```json
{"data": "2026-11-04", "tipo": "copom", "titulo": "Copom", "reuniao": "R7/2026"}
{"data": "2026-10-28", "tipo": "fomc", "titulo": "FOMC"}
{"data": "2026-11-10", "tipo": "ipca", "titulo": "IPCA de outubro"}
```

- `tipo` ∈ `copom`, `fomc`, `ipca`. `reuniao` é obrigatório quando o tipo é
  `copom` e segue o formato `R<n>/<ano>`.
- A `data` é o dia do anúncio (o segundo dia da reunião).
- As datas do Copom e do FOMC de 2026 e 2027 e as divulgações do IPCA de 2026
  são preenchidas a partir das fontes oficiais (BCB, Federal Reserve, IBGE) e
  conferidas antes do commit.
- A validação segue o padrão do `carregar_eventos`: uma entrada malformada
  vira aviso e é ignorada, sem gerar exceção.
- Se o Focus trouxer uma reunião sem data na agenda, o painel mostra um aviso
  ("Focus tem R3/2028 sem data em agenda.json") e ela fica fora do gráfico.

### Cache e falhas

- O resultado bruto das três consultas é gravado em `cache/focus.json` com a
  data da pesquisa.
- Se a consulta falhar, o painel usa o cache e mostra o aviso "Focus: falha ao
  baixar (...); usando cache de AAAA-MM-DD".
- `--offline` lê só do cache.
- Sem cache e sem rede, o bloco `previsoes` sai sem trajetórias e sem sinais,
  e a agenda continua aparecendo.

### Saída

O `dados.json` e o `dados.js` ganham a chave `previsoes`:

```
previsoes: {
  focus_data: "2026-09-25", respondentes: 110,
  sinais:  [{nivel: "destaque"|"info", tipo, texto, data?}],
  agenda:  [{data, tipo, titulo, reuniao?, espera?: {mediana, dif}, contexto?}],
  trajetorias: {
    selic:  {nome, unidade, serie_hist: "selic_meta", proj: [[data, mediana, min, max, n, rotulo]]},
    ipca:   {... serie_hist: "ipca_12m"},
    cambio: {... serie_hist: "usd_brl"},
    pib:    {... serie_hist: null}
  }
}
```

O histórico não é duplicado: o JavaScript lê a série indicada em `serie_hist`
de `D.series`. O texto dos sinais usa `**negrito**` como única marcação e sai
com números no formato brasileiro (vírgula decimal).

## Sinais

As regras são calculadas em `pipeline/sinais.py`, uma função pura por sinal.
Cada uma recebe os dados já parseados e devolve um sinal ou `None`.

1. **Próximo Copom** (sempre): a primeira reunião da agenda depois de hoje.
   A decisão esperada é a mediana da reunião **menos a mediana da reunião
   anterior** (na primeira reunião, menos a Selic meta atual). Verbos:
   *manter*, *cortar X p.p.* ou *subir X p.p.* Vira *destaque* quando faltam 7
   dias ou menos.
2. **Trajetória da Selic** (sempre, *info*): cortes ou altas acumulados até a
   última reunião do ano seguinte e até a última reunião disponível no Focus.
3. **Revisão de expectativa** (*destaque*), para IPCA, Câmbio, PIB Total e
   Selic, no ano atual e no seguinte. Dispara se:
   - a mediana semanal andou na mesma direção por 3 semanas seguidas ou mais
     (uma semana sem mudança interrompe a sequência), ou
   - a mudança nas últimas 4 semanas atingiu o limite: IPCA ±0,20 p.p.,
     PIB ±0,20 p.p., Selic ±0,25 p.p., Câmbio ±R$ 0,10.
   Quando as duas condições valem, o texto usa a da sequência.
4. **Juro real esperado** (sempre): Selic esperada na reunião cuja data na
   agenda fica mais perto de (hoje + 365 dias), menos o IPCA esperado para
   12 meses. Mostra o percentil
   dessa diferença na série `juro_real` desde 2000-01. Vira *destaque* se o
   percentil for ≥ 90 ou ≤ 10.
5. **Câmbio** (sempre, *info*): último `usd_brl` contra a mediana do Câmbio
   no fim do ano atual e do seguinte, com a variação em %.
6. **Agenda próxima** (*info*): eventos `fomc` e `ipca` nos próximos 14 dias.
   O Copom já tem o sinal 1. O FOMC traz a Fed Funds atual como contexto.

Ordem de exibição: primeiro os *destaque*, depois os demais pela `data` do
evento; sinais sem data vão para o fim.

## Tela

A nova aba "Previsões" é a segunda da barra: Séries · Previsões · Cérebro ·
Correlações · Linha do tempo.

- **Cabeçalho:** "O que o mercado espera", à direita "Boletim Focus de
  DD/MM/AAAA · N instituições".
- **Sinais:** grade de cartões (`minmax(320px, 1fr)`). O *destaque* tem
  borda esquerda âmbar (#fab219, a mesma cor dos avisos) e etiqueta colorida.
  O *info* tem borda neutra.
- **Trajetória** (2/3 da largura): botões segmentados Selic / IPCA 12m /
  Dólar / PIB e um gráfico ECharts:
  - histórico dos últimos 3 anos em linha contínua;
  - mediana do Focus em linha tracejada, começando no último ponto real;
  - faixa mínimo–máximo sombreada (duas séries empilhadas: base invisível no
    mínimo e a diferença até o máximo);
  - linha pontilhada "hoje";
  - Selic em degraus, um ponto por reunião na data da agenda; IPCA, Câmbio e
    PIB com um ponto por 31/12;
  - tooltip com mediana, faixa e número de respostas;
  - eixos com números no formato pt-BR;
  - PIB sem histórico, com a legenda "só projeções".
- **Agenda** (1/3 da largura, empilha abaixo de 900px): as próximas 8
  entradas, com data, bolinha na cor do tipo (Copom `--c-copom`, FOMC
  `--c-fomc`, IPCA `--c-plano`), título, "mercado espera cortar 0,25 →
  13,50%" nos Copom, e "em N d".
- **Sem dados do Focus:** a mensagem "Previsões indisponíveis: rode o Abrir
  Painel.bat com internet" no lugar dos sinais e do gráfico; a agenda
  continua.

O código reaproveita `grafico()`, `tooltipBase()`, `eixoBase()`, `el()`,
`fmt()` e os tokens de cor do `painel.css`. Nenhuma dependência nova.

## Estrutura de código

| Arquivo | Responsabilidade |
|---|---|
| `pipeline/focus.py` | Consultas ao Olinda, parse e série semanal |
| `pipeline/agenda.py` | Leitura e validação do `agenda.json` |
| `pipeline/sinais.py` | As seis regras, puras |
| `pipeline/exportar.py` | Monta o bloco `previsoes` |
| `atualizar.py` | Orquestra: Focus com cache, agenda, sinais |
| `agenda.json` | Datas curadas |
| `painel.html` / `painel.js` / `painel.css` | Aba, gráfico, cartões, agenda |

## Testes

- `tests/fixtures/focus_*.json` gravados das respostas reais.
- `test_focus.py`: parse, filtro de `baseCalculo`, agregação semanal, montagem
  da query com `%20` e uso do cache quando a consulta falha.
- `test_agenda.py`: entradas válidas, `reuniao` ausente em Copom, tipo
  desconhecido, JSON quebrado, arquivo ausente.
- `test_sinais.py`, uma bateria por regra, com os casos de borda:
  - exatamente 3 semanas seguidas; uma semana parada no meio;
  - acumulado em 4 semanas igual ao limite; logo abaixo do limite;
  - Copom a 7 e a 8 dias; decisão contada a partir da reunião anterior (o
    caso "manter em dezembro" do protótipo);
  - percentil 90 e percentil 10;
  - Focus ausente, em que cada regra devolve `None`.
- `test_exportar.py`: forma do bloco `previsoes`.
- Tela verificada no navegador: as quatro trajetórias, os temas claro e
  escuro, a largura estreita e o estado sem Focus.
