# Botão de atualizar e publicação no GitHub Pages

Data: 2026-09-30
Estado: aprovado em conversa.

## Objetivo

Publicar o painel como portfólio num repositório público
(`jonatarodrigues/painel-taxas`, site `https://jonatarodrigues.github.io/painel-taxas/`)
com dados atualizados sozinhos, e dar ao painel um botão de atualizar
(seta em círculo) que funciona nos dois ambientes.

### Decisões tomadas

- O botão se comporta conforme o ambiente:
  - **local** (servido pelo `abrir_painel.py`): roda o `atualizar.py` de verdade;
  - **público** (GitHub Pages): recarrega os dados já publicados;
  - **arquivo** (`file://`): recarrega a página.
- Visitantes do site público não disparam o GitHub Actions: isso exigiria
  expor um token.
- Publicação por artefato do Pages. Nenhum dado é commitado.
- O `cache/` persiste entre execuções via `actions/cache`.
- Antes do primeiro push, o autor dos commits passa para o e-mail privativo
  do GitHub.

- A aba Previsões ganha a comparação "o que o mercado previa há 12 meses"
  contra o que aconteceu (seção própria abaixo). Ela entra antes da
  publicação, para o site já sair com ela.

### Fora do escopo

- Disparo remoto do Actions pelo site.
- Domínio próprio.
- Notícias.
- Várias safras de previsão (3, 6 e 24 meses); só a de 12 meses entra.
- Guardar as projeções do próprio painel ao longo do tempo: o histórico
  vem da API do Focus.

## Previsão de 12 meses atrás contra o realizado

### Dados (`pipeline/focus.py`)

- **`baixar(hoje)`** passa a buscar também a pesquisa de cerca de um ano
  atrás, na chave `ha_12m` do bruto:
  - **Selic por reunião:** `ExpectativasMercadoSelic` com
    `baseCalculo eq 0 and Data le '<hoje − 365 dias>'`,
    `orderby=Data desc`, `top=60`. Fica só a data mais recente
    (`ha_12m.data_pesquisa`).
  - **Anuais:** `ExpectativasMercadoAnuais` com `baseCalculo eq 0`,
    `Data` entre `data_pesquisa − 7 dias` e `data_pesquisa`, `Indicador`
    em IPCA, Câmbio e PIB Total, e `DataReferencia` de `hoje.year − 1` a
    `hoje.year + 1`. Para cada indicador e ano, fica a linha da maior
    `Data`.
- **Falha só da consulta retroativa:** não derruba a atualização. Nesse
  caso `ha_12m` fica `None` e entra o aviso "Focus: sem a pesquisa de 12
  meses atrás (…); comparação omitida". As regras de "Focus sem projeções"
  continuam valendo só para a pesquisa atual.
- **Cache:** vem junto no `cache/focus.json`. Um cache antigo, sem a chave
  `ha_12m`, é tratado como `None`.

### Agenda

O `agenda.json` ganha R7/2025 (`2025-11-05`) e R8/2025 (`2025-12-10`),
com o FOMC correspondente (`2025-10-29` e `2025-12-10`), para a linha
antiga da Selic ter datas desde o fim de 2025. As contagens de 2026 e 2027
no teste de integridade não mudam.

### Export (`exportar.previsoes`)

- Cada trajetória ganha `proj_12m`:
  `{"data_pesquisa": "2025-09-30", "pontos": [[data_iso, mediana, rotulo]]}`
  ou `null`.
  - **Selic:** as reuniões da pesquisa antiga que têm data no
    `agenda.json`, em ordem.
  - **IPCA, Câmbio e PIB:** um ponto por `31/12` de cada ano da pesquisa
    antiga.
- **Sinal novo `tipo: "acerto"`** (nível `info`), um por indicador. Os
  textos dizem fatos, nunca julgam o mercado:
  - **Selic:** a reunião mais recente com data ≤ hoje que existe na
    pesquisa antiga, comparada com a Selic meta atual (ou, havendo o aviso
    de Selic defasada, com a mediana usada como âncora). Exemplo:
    "Há 12 meses (Focus de 30/09/2025) o mercado esperava a Selic em
    **12,75%** no Copom de 16/09/2026; ela está em 13,75% (1,00 p.p.
    acima)."
  - **IPCA:** o ano `hoje.year − 1`, comparado com `ipca_12m` de dezembro
    desse ano. Exemplo: "Há 12 meses o mercado esperava IPCA de **4,81%**
    em 2025; fechou em 4,26% (0,55 p.p. abaixo)."
  - **Câmbio:** o ano `hoje.year − 1`, comparado com o último `usd_brl`
    daquele ano. Exemplo: "Há 12 meses o mercado esperava o dólar a
    **R$ 5,46** no fim de 2025; fechou em R$ 5,50 (+0,8%)."
  - **PIB:** fica sem sinal (o painel não tem a série do PIB anual).
  - Sem o dado realizado (série ausente, ou dezembro do ano anterior ainda
    não publicado), o sinal daquele indicador não aparece.
  - Diferença com `|dif| < 0,005` → "igual ao previsto".

### Tela

- O gráfico de trajetória ganha a série "Previsto há 12 meses": linha
  tracejada fina em `--muted`, sem faixa. Ela começa no valor real da
  série na data da pesquisa antiga (via `valorEm`, já existente no
  `painel.js`) e segue pelos `pontos`. A Selic aparece em degraus.
- **Legenda** abaixo do gráfico: "Cinza tracejado: o que o Focus previa
  em DD/MM/AAAA."
- **Tooltip:** mostra "Previsto em DD/MM/AAAA: X". Ao passar sobre uma data
  que tem as duas linhas, mostra os dois valores.
- A etiqueta do sinal `acerto` é "Retrospectiva".

### Testes

- `test_focus.py`:
  - a consulta retroativa monta os filtros certos;
  - falha só na consulta retroativa → `ha_12m: None`, sem exceção.
- `test_previsoes.py`:
  - `proj_12m` da Selic só com reuniões datadas;
  - `proj_12m` anual com os pontos em 31/12;
  - sinal da Selic acima e abaixo do previsto;
  - sinal do IPCA usando dezembro do ano anterior;
  - sinal do câmbio usando o último valor do ano;
  - sem dado realizado → sem sinal;
  - `ha_12m` ausente → sem `proj_12m` e sem sinais `acerto`.
- `test_sinais.py`: as funções puras dos três sinais, com os textos
  exatos.
- O fixture `focus_bruto.json` é regravado com `ha_12m`.

## Botão de atualizar

### Página (`painel.html`, `painel.css`, `painel.js`)

- **O botão:** fica em `.topo-acoes`, antes do botão de tema:
  `<button id="btn-atualizar" class="btn btn-icone" type="button" aria-label="Atualizar dados" title="Atualizar dados">`
  com um SVG inline de seta em círculo (`currentColor`, 16 px). Durante a
  atualização, o SVG gira (classe `girando`, `@keyframes`) e o botão fica
  `disabled`.
- **Status:** o texto ao lado do título (`#atualizado`) continua
  "Atualizado em DD/MM/AAAA às HH:MM". No modo público ele ganha
  " · atualização automática em dias úteis às 20h".
- **Mensagens:** um elemento `#toast` (role `status`, `aria-live="polite"`)
  mostra mensagens curtas por 4 s.
- **Detecção do modo, uma vez no `init`:**
  - protocolo `file:` → `arquivo`;
  - senão, `GET api/status` (caminho relativo, `cache: 'no-store'`):
    resposta 200 com JSON `{"local": true}` → `local`;
  - qualquer outra coisa → `publico`.
- **Recarregar sem duplicar listeners:** uma nova função
  `aplicarDados(novo)` faz `validar(novo)`, `D = novo`, atualiza
  `#atualizado`, a lista e a contagem de avisos (sem registrar listeners de
  novo) e chama `renderKpis(); renderAba()`. O `montarControlesBase`
  continua registrando os listeners uma única vez, no `init`.
- **Clique no modo `local`:**
  1. `POST api/atualizar` com o cabeçalho `X-Painel: 1`.
     - 202 → inicia;
     - 409 → já está atualizando (entra no mesmo acompanhamento);
     - outro código → toast de erro.
  2. Consulta `GET api/status` a cada 3 s até `atualizando: false`.
  3. Se `ultimo_codigo === 0`, `aplicarDados(await carregar())` e toast
     "Dados atualizados".
     Se não, toast "A atualização falhou (código N); dados anteriores
     mantidos". Mesmo assim tenta `carregar()`, porque o `atualizar.py`
     grava arquivos mesmo com falhas parciais: o código 1 só aparece quando
     todas as séries falham.
- **Clique no modo `publico`:** `carregar()` (já usa `cache: 'no-store'`).
  Se o `gerado_em` mudou, `aplicarDados` e toast "Dados atualizados"; senão,
  toast "Os dados já são os mais recentes (DD/MM HH:MM)".
- **Clique no modo `arquivo`:** `location.reload()`.
- **Rodapé:** um novo `<footer class="rodape">` com "Conteúdo informativo,
  gerado automaticamente a partir de fontes públicas (BCB, FRED, Yahoo
  Finance, IPEA). Não é recomendação de investimento." e o link "Código no
  GitHub" (`https://github.com/jonatarodrigues/painel-taxas`).

### Servidor local (`abrir_painel.py`)

- O `HandlerSilencioso` passa a tratar:
  - `GET /api/status` → 200 JSON:
    `{"local": true, "atualizando": bool, "ultimo_codigo": int|null, "iniciado_em": str|null, "terminado_em": str|null}`;
  - `POST /api/atualizar` → aceita somente se o cabeçalho `X-Painel` for
    `1` **e** o `Host` for `127.0.0.1:<porta>` ou `localhost:<porta>`;
    senão 403. Com uma atualização em curso → 409. Senão, inicia uma
    thread que roda o mesmo comando de `atualizar_dados(offline=False)` e
    responde 202.
  - Qualquer outro caminho continua servindo arquivos estáticos como hoje.
- O estado fica numa classe `Atualizador` com `threading.Lock`, testável
  sem rede: o comando é injetável.
- **Por que o cabeçalho e o Host:** um site aberto em outra aba do navegador
  pode mandar POST para `127.0.0.1`, mas não consegue enviar um cabeçalho
  próprio sem preflight de CORS, que o servidor não autoriza. O Host
  barra DNS rebinding.

### Testes

- `tests/test_abrir_painel.py` sobe o servidor numa porta livre com um
  comando falso (Python que dorme 0,3 s e sai com o código escolhido) e
  verifica:
  - status inicial;
  - POST sem cabeçalho → 403;
  - POST com Host estranho → 403;
  - POST válido → 202 e `atualizando: true`;
  - segundo POST → 409;
  - ao terminar → `atualizando: false`, `ultimo_codigo` correto;
  - arquivos estáticos continuam servidos.
- Página verificada no navegador:
  - modo local, com o `abrir_painel.py` e um `atualizar.py` real ou
    `--offline`;
  - modo público, com `python -m http.server`, onde `api/status` dá 404;
  - listeners não duplicados após recarregar (troca de aba e botão de
    avisos funcionam uma vez por clique).

## Publicação

### Repositório

- **Autor dos commits:** antes do primeiro push, reescrever autor e
  committer de todos os commits para
  `jonatarodrigues <13991187+jonatarodrigues@users.noreply.github.com>`
  (`git filter-branch --env-filter`). Configurar esse e-mail em
  `git config user.email` deste repositório. Conferir com
  `git log --format='%ae %ce' | sort -u`.
- **Ordem** (o push dispara o workflow, então o Pages precisa existir antes):
  1. `gh repo create jonatarodrigues/painel-taxas --public --source . --remote origin`,
     sem `--push`, com a descrição "Painel de taxas de mercado do Brasil e
     do exterior, com correlações e previsões do Boletim Focus";
  2. configurar o Pages para publicar via GitHub Actions
     (`gh api -X POST repos/jonatarodrigues/painel-taxas/pages -f build_type=workflow`);
  3. `git push -u origin main`.
- **Conferência antes do push:** nenhum arquivo sensível. O `git ls-files`
  não pode listar `cache/`, `dados.*`, `.superpowers/`, `.remember/`,
  `.playwright-mcp/` nem `capturas/`, e um grep por `token|senha|password|api_key`
  nos arquivos versionados não deve encontrar segredo.

### Workflow `.github/workflows/publicar.yml`

- **Gatilhos:** `schedule: cron '0 23 * * 1-5'`, `workflow_dispatch` e `push`
  na `main`.
- **Permissões:** `contents: read`, `pages: write`, `id-token: write`.
  `concurrency: {group: pages, cancel-in-progress: false}`.
- **Ambiente:** `TZ: America/Sao_Paulo`, para `gerado_em` e `date.today()`
  saírem no horário de Brasília.
- **Job `publicar`** (ubuntu-latest, environment `github-pages`):
  1. `actions/checkout@v4`;
  2. `actions/setup-python@v5` com `python-version: '3.12'` e `cache: pip`;
  3. `pip install -r requirements.txt pytest`;
  4. `python -m pytest -q`;
  5. `actions/cache/restore@v4`, `path: cache`, `key: dados-${{ github.run_id }}`,
     `restore-keys: dados-`;
  6. `python atualizar.py`. Código diferente de 0 falha o job e o site
     anterior continua no ar;
  7. `actions/cache/save@v4`, `path: cache`, `key: dados-${{ github.run_id }}`,
     com `if: always()` e somente se `cache/` existir;
  8. montar `_site/` copiando exatamente `painel.html`, `painel.css`,
     `painel.js`, `dados.js` e `dados.json`, mais `index.html`, um redirect
     para `painel.html` (`<meta http-equiv="refresh" content="0; url=painel.html">`
     com um link visível);
  9. `actions/upload-pages-artifact@v3` com `path: _site`;
  10. `actions/deploy-pages@v4`.
- **Primeira execução:** sem cache. Se alguma fonte bloquear IPs de nuvem,
  a série sai "ausente" e aparece nos avisos; o resto publica. O resultado
  da primeira execução é conferido e relatado.

### README

- No topo: link do site e selo do workflow
  (`https://github.com/jonatarodrigues/painel-taxas/actions/workflows/publicar.yml/badge.svg`).
- Seção "Publicação": o que o workflow faz, o horário e como disparar
  manualmente (Actions → publicar → Run workflow). Inclui o aviso de que o
  GitHub desativa workflows agendados de repositórios sem atividade por
  60 dias, e como reativar.
- Seção de uso local: menciona o botão de atualizar.
