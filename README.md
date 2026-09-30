# Painel de Taxas de Mercado

[![publicar](https://github.com/jonatarodrigues/painel-taxas/actions/workflows/publicar.yml/badge.svg)](https://github.com/jonatarodrigues/painel-taxas/actions/workflows/publicar.yml)

**Ao vivo:** https://jonatarodrigues.github.io/painel-taxas/

Painel local para acompanhar juros, inflação, câmbio, exterior e bolsa com
histórico máximo, eventos que explicam os movimentos e um grafo de
correlações.

Requer Python 3.10 ou superior (desenvolvido com 3.12).

## Abrir com duplo clique

- **`Abrir Painel.bat`**: atualiza os dados (de alguns minutos a uns 15, depende do BCB),
  sobe um servidor local e abre o painel no navegador. Deixe a janela preta
  aberta enquanto usa o painel; fechá-la encerra o servidor.
- **`Abrir Painel (rapido).bat`**: abre com os dados já gravados, sem baixar
  nada.
- Com o painel aberto pelo `Abrir Painel.bat`, o botão ⟳ no topo roda a
  atualização de novo sem fechar a janela. No site publicado, o mesmo botão
  só busca os dados mais recentes que já foram publicados.

Os dois chamam `python abrir_painel.py` (opções: `--rapido`, `--offline`,
`--porta N`). O navegador não consegue executar Python a partir do
`painel.html`, por isso a atualização acontece nesse atalho, antes de abrir.

## Uso manual

```bash
pip install -r requirements.txt
python atualizar.py          # baixa tudo e gera dados.json / dados.js
python -m http.server 8765   # opcional
```

Abra `painel.html` (duplo clique funciona) ou `http://localhost:8765/painel.html`.
Os dados ficam todos locais, mas o painel precisa de internet na primeira
abertura para baixar o ECharts e a fonte Inter (ambos vêm de CDN).

- `python atualizar.py --offline` recalcula só do cache (`cache/`).
- Fontes: BCB SGS, Boletim Focus (BCB), FRED, Yahoo Finance e IPEA. Nenhuma chave necessária.
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

## Publicação

O workflow `.github/workflows/publicar.yml` roda os testes, executa o
`atualizar.py` e publica o painel no GitHub Pages em dias úteis às 20h
(horário de Brasília), a cada push na `main` e quando disparado à mão
(Actions → publicar → Run workflow). O `cache/` das fontes é guardado entre
execuções; se uma fonte falhar, a série usa o último dado bom e aparece nos
avisos. Só `painel.html`, `painel.css`, `painel.js`, `dados.js`,
`dados.json` e a página inicial vão para o site.

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
