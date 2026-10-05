# Aba Bolsa: mapa de setores, maiores altas e baixas, Ibovespa e IFIX

Data: 2026-10-05
Estado: aprovado em conversa, seção por seção (layout, pipeline, falhas e testes).

## Objetivo

Mostrar como foi a bolsa no dia, na semana, no mês, no ano e em 12 meses:
quais setores e ativos puxaram o índice, quem mais subiu e caiu e se o
movimento foi amplo ou concentrado. Há duas visões: ações do **Ibovespa** e
fundos imobiliários do **IFIX**.

### Decisões tomadas

- **Dados de fechamento.** A aba é atualizada pelo `atualizar.py` no mesmo
  ciclo das demais séries (workflow diário às 20h e botão ⟳ local). Nada é
  buscado pelo navegador.
- **O universo vem das carteiras teóricas da B3** (Ibovespa e IFIX). Não há
  lista fixa de tickers, e o rebalanceamento quadrimestral é absorvido
  automaticamente.
- **Os tipos dos FIIs vêm de um arquivo curado, `fiis.json`**, porque a B3
  classifica todos como "Financ e Outros / Fundos".
- **Os retornos usam o `adjclose` do Yahoo** (com proventos). Nos FIIs, o
  rendimento mensal é boa parte do retorno.
- **Os retornos chegam prontos ao `dados.json`**, junto com uma mini-série
  semanal de 12 meses por ativo. O navegador só desenha.

### Fora do escopo

- Cotações intradiárias ou em tempo real.
- Valuation (P/L, dividend yield, prêmio de risco) e fluxo estrangeiro.
- Ativos fora das carteiras do Ibovespa e do IFIX, incluindo listas pessoais.
- Correlação de cada ativo com Selic, câmbio etc. (as séries `ibovespa` e
  `sp500` continuam no Cérebro, como hoje).
- Histórico de preços além de 13 meses.

## Dados

### Fonte 1: carteira teórica da B3

`GET https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{base64}`

O parâmetro é o JSON
`{"language":"pt-br","pageNumber":1,"pageSize":200,"index":"IBOV"|"IFIX","segment":"2"}`
codificado em base64. A resposta (verificada em 2026-10-05) traz:

- `header.date`: data da carteira, `"05/10/26"`.
- `results[]` com `cod` (ticker sem `.SA`), `asset` (nome), `segment`
  (`"Bens Indls / Mat Transporte"`) e `part` (peso em %, texto no formato
  brasileiro `"2,792"`).
- `page.totalRecords`: 76 no IBOV e 99 no IFIX nessa data. `pageSize` 200
  traz tudo numa página. Se `totalPages > 1`, as páginas seguintes são
  pedidas.

Os números em texto são convertidos com `"1.234,56"` → `1234.56`. No IBOV, o
setor exibido é o trecho de `segment` antes da `/`, sem espaços nas pontas
(`"Bens Indls"`). O texto completo vai como `subsetor` para o tooltip.

### Fonte 2: preços no Yahoo Finance

`GET https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}.SA?range=13mo&interval=1d&events=div`

- Usa `indicators.adjclose[0].adjclose`. Se esse campo faltar, cai para
  `indicators.quote[0].close` e marca o ativo com `sem_proventos: true`.
- Índices: o Ibovespa usa `^BVSP`. Para o IFIX o Yahoo não tem histórico de `IFIX.SA` (só o ponto do dia, verificado em 2026-10-05); por isso a visão do IFIX usa o ETF `XFIX11.SA`, que replica o índice e reinveste os proventos. O card diz "via ETF XFIX11".
- São ~175 tickers baixados com `ThreadPoolExecutor(max_workers=5)`, usando
  o `fontes._get` existente (User-Agent e repetições). O tempo estimado é de
  ~30 s a mais no workflow.
- O `/v7/finance/spark` foi descartado porque aceita até 20 símbolos e não
  traz `adjclose`.

### Arquivo curado `fiis.json`

Fica na raiz, ao lado do `agenda.json`:

```json
{
  "_tipos": ["Logística", "Lajes", "Shoppings", "Renda urbana", "Agro", "Papel", "Híbrido", "Fundo de fundos", "Outros"],
  "HGLG11": "Logística",
  "KNCR11": "Papel"
}
```

- A classificação inicial cobre os 99 fundos da carteira de 2026-10-05 e é
  feita na implementação, com base no regulamento e no tipo de ativo de cada
  fundo. O usuário confere antes do merge.
- Um fundo da carteira ausente do arquivo vai para "Outros" e gera aviso.
- Um tipo fora de `_tipos` também gera aviso, e o fundo vai para "Outros".

### Cache e falhas

| Situação | Comportamento |
|---|---|
| A B3 falha ou devolve formato inesperado | Usa `cache/carteiras.json` e mostra a data da carteira com "(cache)". Sem cache, a visão mostra só o card do índice e o aviso "Carteira indisponível". |
| O Yahoo falha num ticker | Usa `cache/bolsa/{TICKER}.csv` (classe `Cache` atual) e marca `desatualizado: true`. Sem cache, o ativo fica com `ret` nulo (cinza). |
| Último preço anterior à data de referência (suspenso, sem negócio ou ticker novo ainda desconhecido no Yahoo) | `ret` nulo e `parado: true`. Ativo cinza no mapa. |
| Mais de 20% dos ativos de uma visão sem retorno no período Dia | Aviso destacado no topo da visão. |
| Índice (`^BVSP`/`XFIX11.SA`) indisponível | A data de referência passa a ser a data mais frequente entre os últimos pregões dos ativos, e o card do índice mostra "—". |
| `--offline` | Lê só os caches, como as demais séries. |

Os avisos entram em `bolsa.avisos` e também na lista geral de avisos do
`atualizar.py`, que já é exibida no painel.

## Cálculos (`pipeline/bolsa.py`, funções puras)

### Data de referência

`data_ref` = último pregão do índice da visão. Cada visão (IBOV, IFIX) tem a
sua.

### Retornos

Para uma série `s` (adjclose diário) e `data_ref`, `ret = s[data_ref] / base − 1`,
em %, com uma casa decimal na exibição. A `base` de cada período é o último
fechamento:

| Período | Base: último fechamento com data… |
|---|---|
| `dia` | `< data_ref` |
| `semana` | `<` segunda-feira da semana de `data_ref` |
| `mes` | `<` dia 1 do mês de `data_ref` |
| `ano` | `<` 1º de janeiro do ano de `data_ref` |
| `m12` | `<=` `data_ref` menos 12 meses (mesma data do calendário) |

Se `s` não tem ponto em `data_ref`, todos os retornos são `null` e o ativo é
marcado `parado`. Se não existe base para um período (ativo listado há
pouco), só aquele período fica `null`. Numa segunda-feira, `semana == dia`,
o que é esperado.

### Setores e amplitude

- **Retorno do setor** = Σ(peso × ret) / Σ(peso), somando só os ativos com
  `ret` não nulo no período. O peso do setor é a soma dos pesos da carteira.
- **Amplitude** = ativos com `ret > 0` / ativos com `ret` não nulo, por
  período.
- **Melhor e pior setor** por período, entre setores com pelo menos um ativo
  com dado.

### Mini-série semanal

Cada visão tem uma lista comum `semanas` com as 52 semanas (períodos
`W-FRI`) até `data_ref`, rotuladas pela sexta-feira ou por `data_ref` na
semana corrente. Cada ativo traz em `semanal` só os valores alinhados a
essa lista: o último `adjclose` da semana, ou `null` se não houve pregão
para ele. Com isso o bloco fica em ~70 KB, contra ~230 KB se cada ativo
repetisse as datas.

## Saída: bloco `bolsa` em `dados.json`

Montado por `exportar.bolsa(...)` e chamado no `atualizar.py` ao lado de
`exportar.previsoes`. É opcional: se a montagem inteira falhar, o bloco vem
`null` e a aba mostra "Dados da bolsa indisponíveis".

```
bolsa: {
  ibov: {
    nome: "Ibovespa", data_ref: "2026-10-05", carteira_data: "2026-10-05", carteira_cache: false,
    alerta: null,                                          // texto quando > 20% sem cotação
    semanas: ["2025-10-10", ..., "2026-10-05"],
    indice:  { ret: {dia, semana, mes, ano, m12}, simbolo },
    amplitude: { dia: {alta: 48, total: 76}, ... },
    setores: [ {nome, peso, ret: {...}} ],                 // ordenados por peso
    ativos:  [ {ticker, nome, setor, subsetor, peso, ret: {...},
                parado, desatualizado, sem_proventos,
                semanal: [31.2, null, ...]} ]                // alinhado a semanas
  },
  ifix: { ...mesma forma; setor = tipo do fiis.json; subsetor ausente... },
  avisos: ["IFIX: 2 fundos sem tipo em fiis.json: XXXX11, YYYY11"]
}
```

Orçamento de tamanho: o bloco `bolsa` deve ficar abaixo de 250 KB no JSON,
com valores arredondados a 2 casas, o que é verificado em teste.

## Tela

A nova aba **Bolsa** fica entre "Previsões" e "Cérebro" e usa o mesmo padrão
de `role="tab"` / `section.aba`.

1. **Barra de controle:** alternância `Ibovespa | IFIX` e seletor de período
   `Dia Semana Mês Ano 12m` (padrão: Dia). A escolha fica guardada em
   `localStorage` (com try/catch), como as outras preferências do painel.
2. **Cards (4):** retorno do índice no período; amplitude ("48 de 76 em
   alta", 63%); melhor setor; pior setor.
3. **Mapa (treemap ECharts, 2 níveis setor → ativo):** a área é o peso e a cor
   é o retorno no período. A escala divergente usa os tokens do painel,
   `--neg` (vermelho) → `--mid` → `--pos` (azul), centrada em 0 e saturada em ±limite por período: dia ±3%, semana
   ±6%, mês ±10%, ano ±25%, 12m ±40% (valores iniciais, ajustáveis numa
   constante do `painel.js`). Cada bloco mostra ticker e retorno. Ativos com
   `ret` nulo ficam cinza. Clicar no setor dá zoom e clicar no ativo abre o
   detalhe.
4. **Maiores altas e maiores baixas:** 5 de cada, ao lado do mapa (abaixo
   dele no celular).
5. **Retorno por setor:** barras horizontais ordenadas, com as mesmas cores
   do mapa.
6. **Detalhe do ativo:** nome, setor, peso, os 5 retornos e a linha da
   mini-série semanal. Os indicadores `desatualizado`, `parado` e
   `sem_proventos` aparecem como etiquetas.
7. **Rodapé:** "Carteira B3 de DD/MM/AAAA" (+ "(cache)") e os avisos do
   bloco.

As cores vêm dos tokens de tema existentes, claro e escuro. A barra de
controle e o mapa funcionam em largura de celular.

## Estrutura de código

| Arquivo | Mudança |
|---|---|
| `pipeline/bolsa.py` (novo) | `parse_carteira_b3`, `numero_br`, `retornos`, `setores`, `amplitude`, `semanal`, `montar_visao` (puras); `baixar_carteira`, `baixar_precos` (rede, com cache). |
| `pipeline/fontes.py` | `parse_yahoo(payload, ajustado=False)`: com `ajustado=True`, prefere `adjclose`. O comportamento atual não muda. |
| `pipeline/exportar.py` | `bolsa(...)` monta o bloco final e os avisos. |
| `atualizar.py` | Chama a montagem da bolsa (respeitando `--offline`) e passa o bloco a `exportar.montar(..., bolsa=...)`. Uma falha inesperada vira aviso e `bolsa: null`, sem abortar o resto. |
| `fiis.json` (novo) | Classificação curada. |
| `painel.html` / `painel.js` / `painel.css` | Aba, renderização e estilos. |
| `README.md` | Uma linha sobre a aba e o `fiis.json`. |

O workflow `publicar.yml` não muda: `cache/` já é persistido inteiro.

## Testes

Sem rede, com fixtures em `tests/fixtures/`:

- `b3_ibov.json` e `b3_ifix.json`: recortes reais (~10 ativos cada).
- `yahoo_fii_adj.json`: payload com `adjclose` e eventos de dividendos.

Casos:

- **Parsers:** `numero_br` (`"2,792"`, `"1.460.506.056"`, vazio); carteira
  com setor dividido em `setor`/`subsetor`; payload B3 malformado → lista
  vazia; `parse_yahoo(ajustado=True)` prefere `adjclose` e cai para `close`
  quando falta.
- **Retornos:** cada período numa data conhecida; segunda-feira
  (`semana == dia`); virada de ano (2 de janeiro); ativo parado (tudo
  `null`); ativo recente (só `m12` nulo).
- **Setores:** ponderação; normalização sem um ativo; sanidade, em que
  Σ(peso_setor × ret_setor)/100 é igual a Σ(peso × ret)/100 dos ativos.
- **FIIs:** tipo pelo `fiis.json`; ausente → "Outros" + aviso; tipo
  inválido → "Outros" + aviso.
- **Falhas:** B3 caída com e sem cache; ticker sem dado e sem cache; limiar
  de 20%; índice indisponível (data de referência pela moda).
- **Export:** forma do bloco; tamanho < 250 KB com 175 ativos sintéticos;
  `dados.json` com `bolsa: null` continua válido.
- **`atualizar.py`:** uma exceção na montagem da bolsa não interrompe a
  atualização (vira aviso).
