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

### Fora do escopo

- Disparo remoto do Actions pelo site.
- Domínio próprio.
- Notícias.

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
