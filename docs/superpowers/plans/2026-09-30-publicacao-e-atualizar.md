# Botão de atualizar, previsão de 12 meses atrás e publicação: plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar este plano tarefa por tarefa. Os passos usam checkbox (`- [ ]`) para acompanhamento.

**Objetivo:** dar ao painel um botão de atualizar que funcione no PC e no site público, mostrar na aba Previsões o que o mercado previa há 12 meses contra o que aconteceu, e publicar o projeto num repositório público com GitHub Pages atualizado pelo Actions.

**Arquitetura:**
- **Servidor local:** o `abrir_painel.py` ganha duas rotas (`/api/status` e `/api/atualizar`) que rodam o `atualizar.py` em segundo plano.
- **Página:** detecta o ambiente e recarrega os dados sem duplicar os listeners.
- **Pipeline:** busca também a pesquisa Focus de cerca de um ano atrás e gera a série `proj_12m` e os sinais "acerto".
- **Publicação:** um workflow do GitHub Actions testa, atualiza e publica um `_site/` fechado no Pages, com o `cache/` persistido via `actions/cache`.

**Tecnologias:** Python 3.10+ (stdlib `http.server`, `threading`, `subprocess`), pandas, requests, pytest; HTML/CSS/JS sem build, ECharts 5.5.1 via CDN; GitHub Actions e `gh` CLI.

**Spec:** `docs/superpowers/specs/2026-09-30-publicacao-e-atualizar-design.md`

## Restrições globais

- Python 3.10 ou superior. Nenhuma dependência nova, nem em Python nem em JS.
- Arquivos com quebra de linha **LF**. No Windows, não reescreva arquivos com `Path.write_text`, que grava CRLF: use a ferramenta de edição. Antes de cada commit, `git diff --stat` deve mostrar só as linhas alteradas.
- Commits via `git commit -F <arquivo>`, com assunto, uma linha em branco e exatamente estas duas linhas finais, seja qual for o modelo:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01EmgUShnjrY9NaSaVvdmJtk`
- Rotas locais:
  - `GET /api/status` → 200 JSON `{"local": true, "atualizando": bool, "ultimo_codigo": int|null, "iniciado_em": str|null, "terminado_em": str|null}`;
  - `POST /api/atualizar` → 403 sem `X-Painel: 1` ou com `Host` diferente de `127.0.0.1:<porta>`/`localhost:<porta>`; 409 durante uma atualização; 202 ao iniciar.
- Modos da página: `arquivo` (protocolo `file:`), `local` (`api/status` responde `{"local": true}`), `publico` (qualquer outro caso).
- Textos exatos:
  - "Atualizando… (1 a 3 min)";
  - "Dados atualizados";
  - "A atualização falhou (código N); dados anteriores mantidos";
  - "Os dados já são os mais recentes (DD/MM HH:MM)";
  - " · atualização automática em dias úteis às 20h";
  - "Cinza tracejado: o que o Focus previa em DD/MM/AAAA.";
  - etiqueta do sinal `acerto`: "Retrospectiva".
- Pesquisa retroativa: `Data le '<hoje − 365 dias>'`; anuais de IPCA, Câmbio e PIB Total, com `DataReferencia` de `hoje.year − 1` a `hoje.year + 1`, `Data` entre `data_pesquisa − 7 dias` e `data_pesquisa`.
- Diferenças da retrospectiva calculadas sobre os valores arredondados para 2 casas; `|dif| < 0,005` → "igual ao previsto".
- Workflow: cron `0 23 * * 1-5`, `workflow_dispatch`, push na `main`; `TZ: America/Sao_Paulo`; publica só `painel.html`, `painel.css`, `painel.js`, `dados.js`, `dados.json` e `index.html`.
- Repositório `jonatarodrigues/painel-taxas`, público. E-mail de autor: `13991187+jonatarodrigues@users.noreply.github.com`.

## Foco da revisão

1. **Outro site aberto no navegador tenta disparar a atualização local** (CSRF ou DNS rebinding): o servidor responde 403 e nada roda. Teste na Tarefa 1.
2. **Dois cliques, ou clique durante uma atualização:** roda uma única vez e o segundo pedido acompanha a primeira. Teste na Tarefa 1 (409) e verificação na Tarefa 2.
3. **Depois de recarregar os dados, abas e botão de avisos disparam uma vez por clique** (sem listeners duplicados). Verificação na Tarefa 2.
4. **Cache antigo do Focus sem a chave `ha_12m`** (a primeira execução depois da atualização): nada quebra, a comparação só não aparece e não gera aviso. Teste na Tarefa 5.
5. **Primeira execução na nuvem sem cache, com alguma fonte bloqueando IPs de datacenter:** publica mesmo assim, com a série nos avisos, e o job só falha se todas as séries falharem. Conferência na Tarefa 8.

## Mapa de arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `abrir_painel.py` | modificar | `Atualizador` e rotas `/api/*` |
| `tests/test_abrir_painel.py` | criar | Rotas locais com comando falso |
| `painel.html` / `painel.css` / `painel.js` | modificar | Botão, toast, rodapé, recarregar dados, linha prevista há 12 meses |
| `pipeline/focus.py` | modificar | `baixar_ha_12m` e a chave `ha_12m` no bruto |
| `pipeline/sinais.py` | modificar | `dmy`, sinais `acerto` |
| `pipeline/exportar.py` | modificar | `proj_12m` e sinais `acerto` em `previsoes` |
| `atualizar.py` | modificar | `valor_dezembro`, `ultimo_do_ano` e a ligação com `previsoes` |
| `agenda.json` | modificar | Reuniões de nov/dez 2025 |
| `tests/test_focus.py`, `tests/test_sinais.py`, `tests/test_previsoes.py`, `tests/test_atualizar.py` | modificar | Testes |
| `tests/fixtures/focus_bruto.json` | regravar | Com `ha_12m` |
| `.github/workflows/publicar.yml` | criar | Testa, atualiza e publica |
| `site/index.html` | criar | Redireciona para `painel.html` |
| `README.md` | modificar | Link do site, selo, publicação, botão |

---

### Tarefa 1: rotas de atualização no servidor local

**Arquivos:**
- Modificar: `abrir_painel.py`
- Criar: `tests/test_abrir_painel.py`

**Interfaces:**
- Fornece:
  - `Atualizador(comando: list[str], cwd: Path)` com `status() -> dict` e `iniciar() -> bool` (False quando já está rodando);
  - `comando_atualizar(offline: bool) -> list[str]`;
  - `servir(porta: int, atualizador: Atualizador, raiz: Path = RAIZ) -> ThreadingHTTPServer`.
- As rotas são consumidas pela página na Tarefa 2.

- [ ] **Passo 1: escrever os testes que falham**

`tests/test_abrir_painel.py`:

```python
import http.client
import json
import sys
import time

import pytest

import abrir_painel


@pytest.fixture
def servidor(tmp_path):
    (tmp_path / "ola.txt").write_text("oi", encoding="utf-8")
    criados = []

    def criar(codigo=0, espera=0.3, comando=None):
        cmd = comando or [sys.executable, "-c", f"import time, sys; time.sleep({espera}); sys.exit({codigo})"]
        at = abrir_painel.Atualizador(cmd, tmp_path)
        s = abrir_painel.servir(abrir_painel.porta_livre(8900), at, tmp_path)
        criados.append(s)
        return s

    yield criar
    for s in criados:
        s.shutdown()
        s.server_close()


def pedir(s, metodo, caminho, cabecalhos=None, host=None):
    porta = s.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=5)
    c.request(metodo, caminho, headers={"Host": host or f"127.0.0.1:{porta}", **(cabecalhos or {})})
    r = c.getresponse()
    corpo = r.read()
    c.close()
    return r.status, corpo


def esperar_fim(s, limite=10):
    fim = time.time() + limite
    while time.time() < fim:
        st = json.loads(pedir(s, "GET", "/api/status")[1])
        if not st["atualizando"]:
            return st
        time.sleep(0.1)
    raise AssertionError("atualização não terminou")


def test_status_inicial(servidor):
    s = servidor()
    codigo, corpo = pedir(s, "GET", "/api/status")
    assert codigo == 200
    assert json.loads(corpo) == {"local": True, "atualizando": False, "ultimo_codigo": None,
                                 "iniciado_em": None, "terminado_em": None}


def test_post_sem_cabecalho_ou_com_host_estranho_e_proibido(servidor):
    s = servidor()
    assert pedir(s, "POST", "/api/atualizar")[0] == 403
    assert pedir(s, "POST", "/api/atualizar", {"X-Painel": "1"}, host="evil.example")[0] == 403
    assert json.loads(pedir(s, "GET", "/api/status")[1])["iniciado_em"] is None


def test_post_valido_roda_uma_vez_e_registra_codigo(servidor):
    s = servidor(codigo=3)
    codigo, corpo = pedir(s, "POST", "/api/atualizar", {"X-Painel": "1"})
    assert codigo == 202 and json.loads(corpo)["atualizando"] is True
    assert pedir(s, "POST", "/api/atualizar", {"X-Painel": "1"})[0] == 409
    st = esperar_fim(s)
    assert st["ultimo_codigo"] == 3 and st["terminado_em"] is not None


def test_localhost_tambem_aceito(servidor):
    s = servidor()
    porta = s.server_address[1]
    assert pedir(s, "POST", "/api/atualizar", {"X-Painel": "1"}, host=f"localhost:{porta}")[0] == 202
    esperar_fim(s)


def test_comando_inexistente_vira_codigo_menos_1(servidor):
    s = servidor(comando=["comando-que-nao-existe-xyz"])
    assert pedir(s, "POST", "/api/atualizar", {"X-Painel": "1"})[0] == 202
    assert esperar_fim(s)["ultimo_codigo"] == -1


def test_estaticos_e_rota_desconhecida(servidor):
    s = servidor()
    assert pedir(s, "GET", "/ola.txt") == (200, b"oi")
    assert pedir(s, "POST", "/api/outra", {"X-Painel": "1"})[0] == 404


def test_comando_atualizar():
    cmd = abrir_painel.comando_atualizar(offline=True)
    assert cmd[0] == sys.executable and cmd[1].endswith("atualizar.py") and cmd[2:] == ["--offline"]
    assert abrir_painel.comando_atualizar(offline=False)[2:] == []
```

- [ ] **Passo 2: rodar e ver falhar**

Comando: `python -m pytest tests/test_abrir_painel.py -q`
Esperado: FAIL com `AttributeError: module 'abrir_painel' has no attribute 'Atualizador'`.

- [ ] **Passo 3: implementar em `abrir_painel.py`**

Acrescente `import json` e `from datetime import datetime` aos imports (em ordem alfabética com os outros da stdlib).

Troque `atualizar_dados` e `servir` e acrescente as classes. A função `atualizar_dados` passa a usar `comando_atualizar`:

```python
def comando_atualizar(offline: bool) -> list[str]:
    return [sys.executable, str(RAIZ / "atualizar.py")] + (["--offline"] if offline else [])


def atualizar_dados(offline: bool) -> int:
    print("Atualizando os dados" + (" (modo offline)" if offline else "") + "...\n")
    return subprocess.call(comando_atualizar(offline), cwd=RAIZ)


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Atualizador:
    """Roda o atualizar.py em segundo plano, uma execução por vez."""

    def __init__(self, comando: list[str], cwd: Path):
        self.comando, self.cwd = comando, cwd
        self._trava = threading.Lock()
        self.atualizando = False
        self.ultimo_codigo: int | None = None
        self.iniciado_em: str | None = None
        self.terminado_em: str | None = None

    def status(self) -> dict:
        with self._trava:
            return {"local": True, "atualizando": self.atualizando, "ultimo_codigo": self.ultimo_codigo,
                    "iniciado_em": self.iniciado_em, "terminado_em": self.terminado_em}

    def iniciar(self) -> bool:
        with self._trava:
            if self.atualizando:
                return False
            self.atualizando, self.iniciado_em, self.terminado_em = True, agora(), None
        threading.Thread(target=self._rodar, daemon=True).start()
        return True

    def _rodar(self) -> None:
        try:
            codigo = subprocess.call(self.comando, cwd=self.cwd)
        except OSError:
            codigo = -1
        with self._trava:
            self.atualizando, self.ultimo_codigo, self.terminado_em = False, codigo, agora()


class HandlerPainel(HandlerSilencioso):
    """Arquivos estáticos mais as rotas /api/status e /api/atualizar."""

    def do_GET(self):
        if self.path.split("?")[0] == "/api/status":
            return self._json(200, self.server.atualizador.status())
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/api/atualizar":
            return self._json(404, {"erro": "não encontrado"})
        porta = self.server.server_address[1]
        # Um site em outra aba não consegue mandar cabeçalho próprio sem preflight de CORS (não
        # atendido aqui); o Host barra DNS rebinding.
        if self.headers.get("X-Painel") != "1" or self.headers.get("Host") not in {f"127.0.0.1:{porta}", f"localhost:{porta}"}:
            return self._json(403, {"erro": "proibido"})
        at = self.server.atualizador
        return self._json(202 if at.iniciar() else 409, at.status())

    def _json(self, codigo: int, corpo: dict) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)


def servir(porta: int, atualizador: Atualizador, raiz: Path = RAIZ) -> ThreadingHTTPServer:
    handler = functools.partial(HandlerPainel, directory=str(raiz))
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), handler)
    servidor.atualizador = atualizador
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor
```

Em `main`, troque `servidor = servir(porta)` por:

```python
    servidor = servir(porta, Atualizador(comando_atualizar(args.offline), RAIZ))
```

- [ ] **Passo 4: rodar os testes**

Comando: `python -m pytest tests/test_abrir_painel.py -q`, depois `python -m pytest -q`.
Esperado: 7 passed no arquivo novo; a suíte inteira passa.

- [ ] **Passo 5: commit**

Assunto: `feat(abrir_painel): rotas locais para atualizar os dados pelo painel`.

---

### Tarefa 2: botão de atualizar na página

**Arquivos:**
- Modificar: `painel.html`, `painel.css`, `painel.js`

**Interfaces:**
- Usa: as rotas da Tarefa 1; os helpers existentes `carregar()`, `validar()`, `renderKpis()`, `renderAba()`, `fmtData()`, `el()`, `$`.
- Fornece: `aplicarDados(novo)` e a variável `modo` (`'arquivo' | 'local' | 'publico'`).

- [ ] **Passo 1: HTML**

Em `painel.html`, dentro de `.topo-acoes`, **antes** do `#btn-tema`:

```html
    <button id="btn-atualizar" class="btn btn-icone" type="button" aria-label="Atualizar dados" title="Atualizar dados"><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><polyline points="21 3 21 9 15 9"/></svg></button>
```

Logo depois do `</header>`:

```html
<div id="toast" class="toast" role="status" aria-live="polite" hidden></div>
```

Logo depois do `</main>` e antes dos `<script>`:

```html
<footer class="rodape">Conteúdo informativo, gerado automaticamente a partir de fontes públicas (BCB, FRED, Yahoo Finance, IPEA). Não é recomendação de investimento. · <a href="https://github.com/jonatarodrigues/painel-taxas">Código no GitHub</a></footer>
```

- [ ] **Passo 2: CSS**

Acrescente ao final de `painel.css`:

```css
/* Botão de atualizar, aviso flutuante e rodapé */
.btn-icone { display: inline-flex; align-items: center; justify-content: center; padding: 6px 9px; }
.btn-icone:disabled { opacity: .6; cursor: progress; }
.btn-icone.girando svg { animation: girar 1s linear infinite; }
@keyframes girar { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .btn-icone.girando svg { animation-duration: 3s; } }
.toast { position: fixed; right: 16px; bottom: 16px; z-index: 50; background: var(--card); color: var(--text); border: 1px solid var(--border-solid); border-radius: 10px; padding: 10px 14px; box-shadow: var(--sombra); font-size: 13px; max-width: min(420px, calc(100vw - 32px)); }
.toast[hidden] { display: none; }
.rodape { margin-top: 32px; padding-top: 12px; border-top: 1px solid var(--border-solid); font-size: 12px; color: var(--muted); }
.rodape a { color: var(--text-2); }
```

- [ ] **Passo 3: JS**

Em `painel.js`, logo depois de `let D = null;`, acrescente:

```js
  let modo = 'publico';
```

Troque o corpo de `montarControlesBase` para registrar os listeners uma única vez e delegar o conteúdo a funções reaproveitáveis:

```js
  function montarControlesBase() {
    $$('[role=tab]').forEach((b) => b.addEventListener('click', () => ativarAba(b.dataset.aba)));
    $('#btn-avisos').addEventListener('click', () => { const box = $('#avisos'); box.hidden = !box.hidden; });
    $('#btn-atualizar').addEventListener('click', aoClicarAtualizar);
    mostrarAvisos();
    $('#atualizado').textContent = textoAtualizado();
  }
```

Logo depois de `montarControlesBase`, acrescente o bloco:

```js
  // ---------- atualizar ----------
  async function detectarModo() {
    if (location.protocol === 'file:') return 'arquivo';
    try {
      const r = await fetch('api/status', { cache: 'no-store' });
      if (r.ok) { const j = await r.json(); if (j && j.local === true) return 'local'; }
    } catch (e) { /* sem servidor local */ }
    return 'publico';
  }
  function textoAtualizado() {
    const base = 'Atualizado em ' + fmtData(D.gerado_em.slice(0, 10)) + ' às ' + D.gerado_em.slice(11, 16);
    return modo === 'publico' ? base + ' · atualização automática em dias úteis às 20h' : base;
  }
  function mostrarAvisos() {
    const lista = D.avisos || [];
    $('#btn-avisos').hidden = !lista.length;
    $('#n-avisos').textContent = lista.length;
    $('#avisos').replaceChildren(...lista.map((a) => el('div', { text: a })));
    if (!lista.length) $('#avisos').hidden = true;
  }
  function aplicarDados(novo) {
    validar(novo);
    D = novo;
    $('#atualizado').textContent = textoAtualizado();
    mostrarAvisos();
    renderKpis();
    renderAba();
  }
  function toast(msg) {
    const t = $('#toast');
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { t.hidden = true; }, 4000);
  }
  function girando(sim) {
    const b = $('#btn-atualizar');
    b.disabled = sim;
    b.classList.toggle('girando', sim);
  }
  const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
  async function atualizarLocal() {
    girando(true);
    toast('Atualizando… (1 a 3 min)');
    try {
      const r = await fetch('api/atualizar', { method: 'POST', headers: { 'X-Painel': '1' } });
      if (r.status !== 202 && r.status !== 409) { toast(`Não foi possível atualizar (HTTP ${r.status})`); return; }
      let st;
      do {
        await esperar(3000);
        st = await (await fetch('api/status', { cache: 'no-store' })).json();
      } while (st.atualizando);
      // O atualizar.py grava os arquivos mesmo com falhas parciais; o código 1 só vem quando tudo falha.
      try { aplicarDados(await carregar()); } catch (e) { /* mantém os dados na tela */ }
      toast(st.ultimo_codigo === 0 ? 'Dados atualizados' : `A atualização falhou (código ${st.ultimo_codigo}); dados anteriores mantidos`);
    } catch (e) {
      toast('Servidor local indisponível; feche e abra o painel de novo');
    } finally {
      girando(false);
    }
  }
  async function atualizarPublico() {
    girando(true);
    try {
      const novo = await carregar();
      if (novo.gerado_em !== D.gerado_em) { aplicarDados(novo); toast('Dados atualizados'); }
      else toast(`Os dados já são os mais recentes (${fmtData(D.gerado_em.slice(0, 10)).slice(0, 5)} ${D.gerado_em.slice(11, 16)})`);
    } catch (e) {
      toast('Não foi possível buscar os dados: ' + e.message);
    } finally {
      girando(false);
    }
  }
  function aoClicarAtualizar() {
    if (modo === 'arquivo') location.reload();
    else if (modo === 'local') atualizarLocal();
    else atualizarPublico();
  }
```

Em `init`, o trecho atual é:

```js
    } catch (e) { const box = $('#erro'); box.hidden = false; box.textContent = e.message; return; }
    montarControlesBase();
```

Insira uma linha entre os dois, para o modo ser conhecido antes de montar o texto do cabeçalho:

```js
    } catch (e) { const box = $('#erro'); box.hidden = false; box.textContent = e.message; return; }
    modo = await detectarModo();
    montarControlesBase();
```

- [ ] **Passo 4: verificar no navegador**

Use as ferramentas MCP do Playwright. Carregue-as com ToolSearch: `select:mcp__plugin_playwright_playwright__browser_navigate,mcp__plugin_playwright_playwright__browser_evaluate,mcp__plugin_playwright_playwright__browser_take_screenshot,mcp__plugin_playwright_playwright__browser_console_messages,mcp__plugin_playwright_playwright__browser_click`. Nunca dispare `alert` ou `confirm`. Se o navegador servir arquivos velhos, acrescente `?v=N` à URL.

1. **Modo local:** rode `python abrir_painel.py --rapido --sem-navegador --porta 8770` em segundo plano e abra a URL que ele imprimir.
   - `evaluate` de `document.querySelector('#atualizado').textContent` não termina com "dias úteis às 20h".
   - Clique no botão: a seta gira, aparece o toast "Atualizando…", e no fim "Dados atualizados" ou a mensagem de falha. Leva de 1 a 3 minutos com internet.
   - Enquanto a seta gira, `document.querySelector('#btn-atualizar').disabled === true`.
   - Encerre o processo no fim.
2. **Modo público:** rode `python -m http.server 8771` em segundo plano e abra `http://localhost:8771/painel.html`.
   - O texto do `#atualizado` termina com " · atualização automática em dias úteis às 20h".
   - Clique no botão: aparece o toast "Os dados já são os mais recentes (…)".
   - Encerre o servidor.
3. **Listeners não duplicados:** no modo público, depois de clicar no botão de atualizar, rode `evaluate`:
   ```js
   () => { const b = document.querySelector('#btn-avisos'); const box = document.querySelector('#avisos'); const antes = box.hidden; b.click(); const depois = box.hidden; b.click(); return [antes, depois, box.hidden]; }
   ```
   Esperado: `[true, false, true]` (cada clique alterna uma única vez). Clique na aba "Previsões" e confirme que ela abre.
4. O rodapé aparece no fim da página, com o link.
5. O console não tem erros.

- [ ] **Passo 5: suíte e commit**

Comando: `python -m pytest -q`. Esperado: todos passam.

Assunto: `feat(painel): botão de atualizar que roda o pipeline no PC e recarrega os dados no site`.

---

### Tarefa 3: pesquisa Focus de 12 meses atrás

**Arquivos:**
- Modificar: `pipeline/focus.py`, `tests/test_focus.py`, `agenda.json`
- Regravar: `tests/fixtures/focus_bruto.json`

**Interfaces:**
- Fornece:
  - `INDICADORES_12M = ("IPCA", "Câmbio", "PIB Total")`;
  - `baixar_ha_12m(hoje: date) -> dict`, que devolve `{"data_pesquisa": str, "selic": [{"Reuniao": str, "Mediana": float}], "anuais": [{"Indicador": str, "DataReferencia": str, "Mediana": float}]}`;
  - `baixar(hoje)` passa a devolver também `"ha_12m": dict | None` e `"ha_12m_erro": str | None`.

- [ ] **Passo 1: escrever os testes que falham**

Primeiro, ajuste o teste existente `test_baixar_fica_so_com_a_pesquisa_mais_recente_da_selic`. Ele guarda o último filtro de cada entidade em `vistos`, e a consulta retroativa sobrescreveria o filtro de `ExpectativasMercadoAnuais`. Logo depois de `monkeypatch.setattr(focus, "consultar", consultar_falso)` nesse teste, acrescente:

```python
    monkeypatch.setattr(focus, "baixar_ha_12m", lambda hoje: None)  # só a pesquisa atual interessa aqui
```

Depois, acrescente ao final de `tests/test_focus.py` (o helper `linha_selic` já existe no arquivo):

```python
def test_baixar_ha_12m_filtros_e_ultima_linha(monkeypatch):
    vistos = []

    def consultar_falso(entidade, **op):
        vistos.append((entidade, op))
        if entidade == "ExpectativasMercadoSelic":
            return [linha_selic("2025-09-30", "R6/2026", 12.75), linha_selic("2025-09-30", "R7/2025", 15.0),
                    linha_selic("2025-09-26", "R6/2026", 12.5)]
        return [{"Indicador": "IPCA", "Data": "2025-09-26", "DataReferencia": "2025", "Mediana": 4.9},
                {"Indicador": "IPCA", "Data": "2025-09-30", "DataReferencia": "2025", "Mediana": 4.8061},
                {"Indicador": "Câmbio", "Data": "2025-09-30", "DataReferencia": "2025", "Mediana": 5.4555}]

    monkeypatch.setattr(focus, "consultar", consultar_falso)
    h = focus.baixar_ha_12m(date(2026, 9, 30))
    assert h == {"data_pesquisa": "2025-09-30",
                 "selic": [{"Reuniao": "R6/2026", "Mediana": 12.75}, {"Reuniao": "R7/2025", "Mediana": 15.0}],
                 "anuais": [{"Indicador": "Câmbio", "DataReferencia": "2025", "Mediana": 5.4555},
                            {"Indicador": "IPCA", "DataReferencia": "2025", "Mediana": 4.8061}]}
    (_, op_selic), (_, op_anuais) = vistos
    assert op_selic["filter"] == "baseCalculo eq 0 and Data le '2025-09-30'"
    f = op_anuais["filter"]
    assert "Data ge '2025-09-23' and Data le '2025-09-30'" in f
    assert "DataReferencia ge '2025' and DataReferencia le '2027'" in f
    assert all(f"Indicador eq '{i}'" in f for i in focus.INDICADORES_12M) and "Selic" not in f


def test_baixar_ha_12m_sem_selic_levanta(monkeypatch):
    monkeypatch.setattr(focus, "consultar", lambda entidade, **op: [])
    with pytest.raises(fontes.RespostaVazia):
        focus.baixar_ha_12m(date(2026, 9, 30))


def test_baixar_inclui_ha_12m_ou_o_erro(monkeypatch):
    def consultar_falso(entidade, **op):
        if entidade == "ExpectativasMercadoSelic":
            return [linha_selic("2026-09-25", "R7/2026", 13.5)]
        if entidade == "ExpectativasMercadoInflacao12Meses":
            return [{"Data": "2026-09-25", "Mediana": 4.65}]
        return [{"Indicador": "IPCA"}]

    monkeypatch.setattr(focus, "consultar", consultar_falso)
    monkeypatch.setattr(focus, "baixar_ha_12m", lambda hoje: {"data_pesquisa": "2025-09-30", "selic": [], "anuais": []})
    b = focus.baixar(date(2026, 9, 30))
    assert b["ha_12m"]["data_pesquisa"] == "2025-09-30" and b["ha_12m_erro"] is None

    def falha(hoje):
        raise ConnectionError("rede fora")

    monkeypatch.setattr(focus, "baixar_ha_12m", falha)
    b = focus.baixar(date(2026, 9, 30))
    assert b["ha_12m"] is None and b["ha_12m_erro"] == "rede fora"
    assert [r["Reuniao"] for r in b["selic"]] == ["R7/2026"]  # a pesquisa atual continua intacta


def test_fixture_tem_a_pesquisa_de_12_meses_atras():
    ha = json.loads(FIX.read_text(encoding="utf-8"))["ha_12m"]
    assert ha["data_pesquisa"] <= "2025-09-30" and ha["selic"]
    assert {(r["Indicador"], r["DataReferencia"]) for r in ha["anuais"]} >= {("IPCA", "2025"), ("Câmbio", "2025")}
```

- [ ] **Passo 2: rodar e ver falhar**

Comando: `python -m pytest tests/test_focus.py -q`
Esperado: FAIL com `AttributeError: ... 'baixar_ha_12m'` e `KeyError: 'ha_12m'` no teste do fixture.

- [ ] **Passo 3: implementar em `pipeline/focus.py`**

Logo depois de `INDICADORES = (...)`:

```python
INDICADORES_12M = ("IPCA", "Câmbio", "PIB Total")  # a Selic vem por reunião
```

Logo depois de `baixar`:

```python
def baixar_ha_12m(hoje: date) -> dict:
    """Pesquisa de cerca de um ano atrás, para comparar o previsto com o realizado."""
    alvo = (hoje - timedelta(days=365)).isoformat()
    selic = consultar("ExpectativasMercadoSelic", filter=f"baseCalculo eq 0 and Data le '{alvo}'",
                      orderby="Data desc", top=60)
    if not selic:
        raise fontes.RespostaVazia("Focus sem a pesquisa de 12 meses atrás")
    data = selic[0]["Data"]
    inicio = (date.fromisoformat(data) - timedelta(days=7)).isoformat()
    indicadores = " or ".join(f"Indicador eq '{i}'" for i in INDICADORES_12M)
    anuais = consultar(
        "ExpectativasMercadoAnuais",
        filter=(f"Data ge '{inicio}' and Data le '{data}' and baseCalculo eq 0 and ({indicadores}) "
                f"and DataReferencia ge '{hoje.year - 1}' and DataReferencia le '{hoje.year + 1}'"),
        select="Indicador,Data,DataReferencia,Mediana")
    ultimas: dict[tuple[str, str], dict] = {}
    for r in sorted(anuais, key=lambda r: r["Data"]):
        ultimas[(r["Indicador"], str(r["DataReferencia"]))] = r
    return {"data_pesquisa": data,
            "selic": [{"Reuniao": r["Reuniao"], "Mediana": float(r["Mediana"])} for r in selic if r["Data"] == data],
            "anuais": [{"Indicador": ind, "DataReferencia": ano, "Mediana": float(r["Mediana"])}
                       for (ind, ano), r in sorted(ultimas.items())]}
```

Em `baixar`, troque o `return` final por:

```python
    try:
        ha_12m, erro_12m = baixar_ha_12m(hoje), None
    except Exception as e:  # a comparação é opcional: nunca derruba a pesquisa atual
        ha_12m, erro_12m = None, str(e)
    return {"data_pesquisa": data, "selic": selic, "anuais": anuais, "infl12": infl[0],
            "ha_12m": ha_12m, "ha_12m_erro": erro_12m}
```

- [ ] **Passo 4: reuniões de 2025 no `agenda.json`**

Insira no início da lista (a lista continua em ordem de data):

```json
{"data":"2025-10-29","tipo":"fomc","titulo":"FOMC"},
{"data":"2025-11-05","tipo":"copom","titulo":"Copom","reuniao":"R7/2025"},
{"data":"2025-12-10","tipo":"copom","titulo":"Copom","reuniao":"R8/2025"},
{"data":"2025-12-10","tipo":"fomc","titulo":"FOMC"},
```

- [ ] **Passo 5: regravar o fixture e rodar os testes**

Precisa de internet. Se o BCB recusar a chamada, tente de novo.

```bash
python -c "import json; from datetime import date; from pipeline import focus; b = focus.baixar(date(2026, 9, 30)); assert b['ha_12m'], b['ha_12m_erro']; open('tests/fixtures/focus_bruto.json', 'w', encoding='utf-8', newline='\n').write(json.dumps(b, ensure_ascii=False, indent=1))"
python -m pytest -q
```

Esperado: todos passam, incluindo os 4 testes novos.

- [ ] **Passo 6: commit**

Assunto: `feat(focus): pesquisa de 12 meses atrás para comparar previsto e realizado`.

---

### Tarefa 4: sinais de retrospectiva

**Arquivos:**
- Modificar: `pipeline/sinais.py`, `tests/test_sinais.py`

**Interfaces:**
- Usa: `fmt_br`, `EPS` (já existem em `sinais.py`).
- Fornece:
  - `dmy(iso: str) -> str` (`"2025-09-30"` → `"30/09/2025"`);
  - `sinal_acerto_selic(previsto: float, data_reuniao: str, data_pesquisa: str, selic_atual: float) -> dict`;
  - `sinal_acerto_ipca(previsto: float, ano: str, realizado: float) -> dict`;
  - `sinal_acerto_cambio(previsto: float, ano: str, realizado: float) -> dict`.
- Todos devolvem `{"nivel": "info", "tipo": "acerto", "texto": str}`.

- [ ] **Passo 1: escrever os testes que falham**

Acrescente ao final de `tests/test_sinais.py`:

```python
def test_dmy():
    assert sinais.dmy("2025-09-30") == "30/09/2025"


def test_acerto_selic_acima_abaixo_igual():
    s = sinais.sinal_acerto_selic(12.75, "2026-09-16", "2025-09-30", 13.75)
    assert s == {"nivel": "info", "tipo": "acerto",
                 "texto": "Há 12 meses (Focus de 30/09/2025) o mercado esperava a Selic em **12,75%** no Copom de "
                          "16/09/2026; ela está em 13,75% (1,00 p.p. acima)."}
    assert sinais.sinal_acerto_selic(14.0, "2026-09-16", "2025-09-30", 13.75)["texto"].endswith(
        "ela está em 13,75% (0,25 p.p. abaixo).")
    assert sinais.sinal_acerto_selic(13.75, "2026-09-16", "2025-09-30", 13.75)["texto"].endswith("(igual ao previsto).")


def test_acerto_ipca_usa_valores_arredondados():
    s = sinais.sinal_acerto_ipca(4.8061, "2025", 4.2644)
    assert s == {"nivel": "info", "tipo": "acerto",
                 "texto": "Há 12 meses o mercado esperava IPCA de **4,81%** em 2025; fechou em 4,26% (0,55 p.p. abaixo)."}


def test_acerto_cambio():
    s = sinais.sinal_acerto_cambio(5.4555, "2025", 5.5024)
    assert s == {"nivel": "info", "tipo": "acerto",
                 "texto": "Há 12 meses o mercado esperava o dólar a **R$ 5,46** no fim de 2025; fechou em R$ 5,50 (+0,7%)."}
    assert sinais.sinal_acerto_cambio(5.5, "2025", 5.5)["texto"].endswith("fechou em R$ 5,50 (igual ao previsto).")
    assert sinais.sinal_acerto_cambio(5.5, "2025", 5.39)["texto"].endswith("fechou em R$ 5,39 (-2,0%).")
```

- [ ] **Passo 2: rodar e ver falhar**

Comando: `python -m pytest tests/test_sinais.py -q`
Esperado: FAIL com `AttributeError` para `dmy` e para os três `sinal_acerto_*`.

- [ ] **Passo 3: implementar**

Logo depois de `def dm(iso)`, em `pipeline/sinais.py`:

```python
def dmy(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"
```

Ao final do arquivo:

```python
def _comparacao_pp(previsto: float, realizado: float) -> str:
    """Diferença sobre os valores arredondados que aparecem no texto."""
    d = round(realizado, 2) - round(previsto, 2)
    if abs(d) < 0.005:
        return "igual ao previsto"
    return f"{fmt_br(abs(d))} p.p. {'acima' if d > 0 else 'abaixo'}"


def sinal_acerto_selic(previsto: float, data_reuniao: str, data_pesquisa: str, selic_atual: float) -> dict:
    return {"nivel": "info", "tipo": "acerto",
            "texto": (f"Há 12 meses (Focus de {dmy(data_pesquisa)}) o mercado esperava a Selic em "
                      f"**{fmt_br(previsto)}%** no Copom de {dmy(data_reuniao)}; ela está em "
                      f"{fmt_br(selic_atual)}% ({_comparacao_pp(previsto, selic_atual)}).")}


def sinal_acerto_ipca(previsto: float, ano: str, realizado: float) -> dict:
    return {"nivel": "info", "tipo": "acerto",
            "texto": (f"Há 12 meses o mercado esperava IPCA de **{fmt_br(previsto)}%** em {ano}; "
                      f"fechou em {fmt_br(realizado)}% ({_comparacao_pp(previsto, realizado)}).")}


def sinal_acerto_cambio(previsto: float, ano: str, realizado: float) -> dict:
    p, r = round(previsto, 2), round(realizado, 2)
    comparacao = "igual ao previsto" if abs(r - p) < 0.005 else f"{fmt_br((r / p - 1) * 100, 1, sinal=True)}%"
    return {"nivel": "info", "tipo": "acerto",
            "texto": (f"Há 12 meses o mercado esperava o dólar a **R$ {fmt_br(previsto)}** no fim de {ano}; "
                      f"fechou em R$ {fmt_br(realizado)} ({comparacao}).")}
```

- [ ] **Passo 4: rodar os testes**

Comando: `python -m pytest tests/test_sinais.py -q`, depois `python -m pytest -q`.
Esperado: os 4 testes novos passam e a suíte inteira passa.

- [ ] **Passo 5: commit**

Assunto: `feat(sinais): retrospectiva do previsto há 12 meses contra o realizado`.

---

### Tarefa 5: `proj_12m` e sinais de retrospectiva no export

**Arquivos:**
- Modificar: `pipeline/exportar.py` (função `previsoes`), `atualizar.py`, `tests/test_previsoes.py`, `tests/test_atualizar.py`

**Interfaces:**
- Usa: `bruto["ha_12m"]` e `bruto["ha_12m_erro"]` (Tarefa 3); `sinais.sinal_acerto_*` (Tarefa 4).
- Fornece:
  - `exportar.previsoes(..., avisos, *, ipca_dez_anterior: float | None = None, usd_fim_anterior: float | None = None)`;
  - cada `trajetorias[x]` ganha `"proj_12m": {"data_pesquisa": str, "pontos": [[data_iso, mediana, rotulo]]} | None`;
  - `atualizar.valor_dezembro(mensal: pd.Series | None, ano: int) -> float | None`;
  - `atualizar.ultimo_do_ano(serie: pd.Series | None, ano: int) -> float | None`.

- [ ] **Passo 1: escrever os testes que falham**

Acrescente ao final de `tests/test_previsoes.py`:

```python
HA_12M = {"data_pesquisa": "2025-09-30",
          "selic": [{"Reuniao": "R6/2026", "Mediana": 12.75}, {"Reuniao": "R7/2026", "Mediana": 12.5},
                    {"Reuniao": "R1/2027", "Mediana": 12.0}],
          "anuais": [{"Indicador": "Câmbio", "DataReferencia": "2025", "Mediana": 5.4555},
                     {"Indicador": "IPCA", "DataReferencia": "2025", "Mediana": 4.8061},
                     {"Indicador": "IPCA", "DataReferencia": "2026", "Mediana": 4.29}]}


def com_ha(**troca):
    return montar(bruto=dict(BRUTO, ha_12m=HA_12M, ha_12m_erro=None), **troca)


def test_proj_12m_selic_so_reunioes_datadas_e_anual_em_31_12():
    p, _ = com_ha()
    assert p["trajetorias"]["selic"]["proj_12m"] == {
        "data_pesquisa": "2025-09-30",
        "pontos": [["2026-09-16", 12.75, "R6/2026"], ["2026-11-04", 12.5, "R7/2026"]]}  # R1/2027 sem data na AGENDA
    assert p["trajetorias"]["ipca"]["proj_12m"]["pontos"] == [["2025-12-31", 4.8061, "2025"], ["2026-12-31", 4.29, "2026"]]
    assert p["trajetorias"]["cambio"]["proj_12m"]["pontos"] == [["2025-12-31", 5.4555, "2025"]]
    assert p["trajetorias"]["pib"]["proj_12m"] is None


def test_sinais_de_retrospectiva():
    p, _ = com_ha(ipca_dez_anterior=4.2644, usd_fim_anterior=5.5024)
    assert [s["texto"] for s in p["sinais"] if s["tipo"] == "acerto"] == [
        "Há 12 meses (Focus de 30/09/2025) o mercado esperava a Selic em **12,75%** no Copom de 16/09/2026; "
        "ela está em 13,75% (1,00 p.p. acima).",
        "Há 12 meses o mercado esperava IPCA de **4,81%** em 2025; fechou em 4,26% (0,55 p.p. abaixo).",
        "Há 12 meses o mercado esperava o dólar a **R$ 5,46** no fim de 2025; fechou em R$ 5,50 (+0,7%).",
    ]


def test_retrospectiva_sem_realizado_so_selic():
    p, _ = com_ha()
    acertos = [s["texto"] for s in p["sinais"] if s["tipo"] == "acerto"]
    assert len(acertos) == 1 and acertos[0].startswith("Há 12 meses (Focus de 30/09/2025) o mercado esperava a Selic")


def test_retrospectiva_da_selic_usa_a_ancora_quando_a_selic_esta_defasada():
    p, _ = com_ha(selic_data="2026-09-10")  # antes do Copom de 16/09; o Focus traz R6/2026 = 14,00
    texto = next(s["texto"] for s in p["sinais"] if s["tipo"] == "acerto")
    assert "ela está em 14,00% (1,25 p.p. acima)" in texto


def test_sem_ha_12m_cache_antigo_e_falha():
    p, avisos = montar()  # BRUTO sem a chave ha_12m, como um cache antigo
    assert all(t["proj_12m"] is None for t in p["trajetorias"].values())
    assert not any(s["tipo"] == "acerto" for s in p["sinais"])
    assert not any("12 meses atrás" in a for a in avisos)
    p, avisos = montar(bruto=dict(BRUTO, ha_12m=None, ha_12m_erro="rede fora"), avisos=[])
    assert "Focus: sem a pesquisa de 12 meses atrás (rede fora); comparação omitida" in avisos
```

Acrescente ao final de `tests/test_atualizar.py`:

```python
def test_valor_dezembro_e_ultimo_do_ano():
    m = pd.Series([4.1, 4.2644], index=pd.to_datetime(["2025-11-01", "2025-12-01"]))
    assert atualizar.valor_dezembro(m, 2025) == 4.2644
    assert atualizar.valor_dezembro(m, 2024) is None and atualizar.valor_dezembro(None, 2025) is None
    d = pd.Series([5.4, 5.5024, 5.6], index=pd.to_datetime(["2025-12-30", "2025-12-31", "2026-01-02"]))
    assert atualizar.ultimo_do_ano(d, 2025) == 5.5024
    assert atualizar.ultimo_do_ano(d, 2024) is None and atualizar.ultimo_do_ano(None, 2025) is None
```

- [ ] **Passo 2: rodar e ver falhar**

Comando: `python -m pytest tests/test_previsoes.py tests/test_atualizar.py -q`
Esperado: FAIL com `KeyError: 'proj_12m'`, `TypeError` pelos argumentos novos e `AttributeError` para `valor_dezembro`.

- [ ] **Passo 3: implementar em `pipeline/exportar.py`**

Troque a assinatura de `previsoes` por:

```python
def previsoes(bruto: dict | None, agenda_: list[dict], selic_hoje: float | None, selic_data: str | None, usd_hoje: float | None,
              fed_funds: float | None, juro_hist: list[float], hoje: date, avisos: list[str], *,
              ipca_dez_anterior: float | None = None, usd_fim_anterior: float | None = None) -> dict:
```

Logo antes da linha `ipca_ano = semanal.get("IPCA", {}).get(str(hoje.year)) or []` (depois do laço que monta `trajetorias`), insira:

```python
    for t in trajetorias.values():
        t["proj_12m"] = None
    ha = bruto.get("ha_12m")
    if ha is None and bruto.get("ha_12m_erro"):
        avisos.append(f"Focus: sem a pesquisa de 12 meses atrás ({bruto['ha_12m_erro']}); comparação omitida")
    if ha:
        med_ha = {r["Reuniao"]: float(r["Mediana"]) for r in ha.get("selic", [])}
        pontos_selic = [[datas[r], med_ha[r], r] for r in sorted(med_ha, key=sinais.chave_reuniao) if r in datas]
        if pontos_selic:
            trajetorias["selic"]["proj_12m"] = {"data_pesquisa": ha["data_pesquisa"], "pontos": pontos_selic}
        anuais_ha: dict[str, dict[str, float]] = {}
        for r in ha.get("anuais", []):
            anuais_ha.setdefault(r["Indicador"], {})[str(r["DataReferencia"])] = float(r["Mediana"])
        for chave, ind, *_ in TRAJETORIAS:
            if anuais_ha.get(ind):
                trajetorias[chave]["proj_12m"] = {
                    "data_pesquisa": ha["data_pesquisa"],
                    "pontos": [[f"{ano}-12-31", v, ano] for ano, v in sorted(anuais_ha[ind].items())]}
        # Retrospectiva: o que a pesquisa de 12 meses atrás previa para o que já aconteceu.
        feitas = [a for a in agenda_ if a["tipo"] == "copom" and a["data"] <= iso and a["reuniao"] in med_ha]
        if ancora is not None and feitas:
            a = max(feitas, key=lambda a: a["data"])
            lista.append(sinais.sinal_acerto_selic(med_ha[a["reuniao"]], a["data"], ha["data_pesquisa"], ancora))
        ano_anterior = str(hoje.year - 1)
        previsto = anuais_ha.get("IPCA", {}).get(ano_anterior)
        if previsto is not None and ipca_dez_anterior is not None:
            lista.append(sinais.sinal_acerto_ipca(previsto, ano_anterior, ipca_dez_anterior))
        previsto = anuais_ha.get("Câmbio", {}).get(ano_anterior)
        if previsto is not None and usd_fim_anterior is not None:
            lista.append(sinais.sinal_acerto_cambio(previsto, ano_anterior, usd_fim_anterior))
```

(`datas`, `ancora`, `iso` e `lista` já existem na função, e o `return` final já aplica `sinais.ordenar(lista)`.)

- [ ] **Passo 4: implementar em `atualizar.py`**

Logo depois de `status_derivada`:

```python
def valor_dezembro(mensal: pd.Series | None, ano: int) -> float | None:
    """Valor mensal de dezembro de `ano` (o IPCA 12 meses fechado do ano)."""
    if mensal is None:
        return None
    for i, v in mensal.dropna().items():
        if str(i)[:7] == f"{ano}-12":
            return float(v)
    return None


def ultimo_do_ano(serie: pd.Series | None, ano: int) -> float | None:
    """Último valor observado em `ano` (o fechamento do dólar)."""
    if serie is None:
        return None
    s = serie.dropna()
    s = s[s.index.year == ano]
    return float(s.iloc[-1]) if len(s) else None
```

Acrescente `import pandas as pd` aos imports, se ainda não existir. Na chamada de `exportar.previsoes`, acrescente os dois argumentos nomeados:

```python
    prev = exportar.previsoes(bruto_focus, agenda_, ultimo("selic_meta"), selic_data, ultimo("usd_brl"),
                              ultimo("fed_funds"), juro_hist, hoje, avisos,
                              ipca_dez_anterior=valor_dezembro(mensais.get("ipca_12m"), hoje.year - 1),
                              usd_fim_anterior=ultimo_do_ano(brutas.get("usd_brl"), hoje.year - 1))
```

- [ ] **Passo 5: rodar os testes e o pipeline offline**

Comandos: `python -m pytest -q` e `python atualizar.py --offline`.
Esperado: todos os testes passam. O `--offline` roda sem traceback; como o cache ainda não tem `ha_12m`, a retrospectiva não aparece e não há aviso sobre ela.

- [ ] **Passo 6: rodar com dados reais**

Comando: `python atualizar.py` (internet, 1 a 3 min). Depois:

```bash
python -c "import json; p = json.load(open('dados.json', encoding='utf-8'))['previsoes']; print([s['texto'] for s in p['sinais'] if s['tipo'] == 'acerto']); print({k: (v['proj_12m'] or {}).get('data_pesquisa') for k, v in p['trajetorias'].items()})"
```

Esperado: três textos de retrospectiva (Selic, IPCA 2025 e dólar 2025) e `proj_12m` com a data da pesquisa de um ano atrás em selic, ipca, cambio e pib.

- [ ] **Passo 7: commit**

Assunto: `feat(previsoes): previsão de 12 meses atrás e retrospectiva no dados.json`.

---

### Tarefa 6: linha "previsto há 12 meses" no gráfico

**Arquivos:**
- Modificar: `painel.html`, `painel.js`

**Interfaces:**
- Usa: `trajetorias[x].proj_12m` (Tarefa 5); `valorEm(id, iso)`, `fmt`, `fmtData`, `cssVar` (já existentes).

- [ ] **Passo 1: HTML**

Em `painel.html`, logo depois do `<p class="legenda-faixa muted">Linha contínua: histórico. …</p>` do `#card-traj`:

```html
        <p id="leg-prev12" class="legenda-faixa muted" hidden></p>
```

- [ ] **Passo 2: JS**

Em `painel.js`, no `TAG_SINAL`, acrescente `acerto: 'Retrospectiva'`.

Em `renderTrajetoria`, no bloco `if (!t || !t.proj.length) {`, acrescente `$('#leg-prev12').hidden = true;` antes do `return`.

Logo depois da linha `const degrau = ...`, acrescente:

```js
    // O que a pesquisa de ~12 meses atrás previa, partindo do valor real daquela data.
    const p12 = t.proj_12m;
    const ini12 = p12 && t.serie_hist && D.series[t.serie_hist] ? valorEm(t.serie_hist, p12.data_pesquisa) : null;
    const prev12 = p12 ? (ini12 != null ? [[p12.data_pesquisa, ini12, null]] : []).concat(p12.pontos) : [];
    const degrau12 = p12 && p12.pontos.length && String(p12.pontos[0][2]).startsWith('R') ? 'end' : false;
    $('#leg-prev12').hidden = !prev12.length;
    if (prev12.length) $('#leg-prev12').textContent = `Cinza tracejado: o que o Focus previa em ${fmtData(p12.data_pesquisa)}.`;
```

Troque o `formatter` do tooltip por:

```js
        formatter: (ps) => {
          const p = ps.find((q) => q.seriesId === 'proj' && q.data[4] != null) || ps.find((q) => q.seriesId === 'hist');
          const q12 = ps.find((q) => q.seriesId === 'prev12' && q.data[2] != null);
          if (!p && !q12) return '';
          const caixa = el('div', { class: 'tt' });
          if (p) {
            const d = p.data;
            caixa.append(el('div', { class: 'tt-titulo', text: p.seriesId === 'proj' ? `${d[5]} · ${fmtData(d[0])}` : fmtData(String(d[0]).slice(0, 10)) }),
              el('div', {}, el('strong', { text: `${fmt(d[1])} ${t.unidade}` }), el('span', { class: 'tt-nome', text: p.seriesId === 'proj' ? ' mediana' : '' })));
            if (p.seriesId === 'proj') caixa.append(el('div', { class: 'tt-nome', text: `Faixa ${fmt(d[2])} a ${fmt(d[3])} · ${d[4]} respostas` }));
          } else {
            caixa.append(el('div', { class: 'tt-titulo', text: `${q12.data[2]} · ${fmtData(q12.data[0])}` }));
          }
          if (q12) caixa.append(el('div', { class: 'tt-nome', text: `Previsto em ${fmtData(p12.data_pesquisa)}: ${fmt(q12.data[1])} ${t.unidade}` }));
          return caixa;
        },
```

No array `series`, acrescente como **último** elemento:

```js
        { id: 'prev12', type: 'line', data: prev12, step: degrau12, showSymbol: true, symbolSize: 4, z: 1,
          lineStyle: { width: 1.5, type: 'dashed', color: cssVar('--muted') }, itemStyle: { color: cssVar('--muted') } },
```

- [ ] **Passo 3: verificar no navegador**

Suba `python -m http.server 8772` em segundo plano, abra `http://localhost:8772/painel.html` e vá à aba Previsões. Use o `dados.json` gerado com dados reais na Tarefa 5.

1. Os cartões "Retrospectiva" aparecem, com números em vírgula e negrito.
2. Em Selic, IPCA 12m e Dólar aparece a linha cinza tracejada. Ela começa sobre a linha real, perto de 30/09/2025, e a legenda "Cinza tracejado: o que o Focus previa em DD/MM/AAAA." fica visível.
3. Na Selic a linha cinza é em degraus. No PIB a linha cinza aparece sem ponto inicial, porque não há histórico.
4. O tooltip sobre um ponto cinza mostra "Previsto em DD/MM/AAAA: X".
5. A troca de tema e de indicador redesenha sem erro no console.

Encerre o servidor.

- [ ] **Passo 4: suíte e commit**

Comando: `python -m pytest -q`. Esperado: todos passam.

Assunto: `feat(painel): linha do que o Focus previa há 12 meses na trajetória`.

---

### Tarefa 7: workflow de publicação, página inicial e README

**Arquivos:**
- Criar: `.github/workflows/publicar.yml`, `site/index.html`
- Modificar: `README.md`

- [ ] **Passo 1: workflow**

`.github/workflows/publicar.yml`:

```yaml
name: publicar

on:
  schedule:
    - cron: '0 23 * * 1-5'   # 20h em Brasília, dias úteis
  workflow_dispatch:
  push:
    branches: [main]

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

env:
  TZ: America/Sao_Paulo

jobs:
  publicar:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip

      - name: Dependências
        run: pip install -r requirements.txt

      - name: Testes
        run: python -m pytest -q

      - name: Restaurar o cache das fontes
        uses: actions/cache/restore@v4
        with:
          path: cache
          key: dados-${{ github.run_id }}
          restore-keys: dados-

      - name: Atualizar os dados
        run: python atualizar.py

      - name: Guardar o cache das fontes
        if: always() && hashFiles('cache/**') != ''
        uses: actions/cache/save@v4
        with:
          path: cache
          key: dados-${{ github.run_id }}

      - name: Montar o site
        run: |
          mkdir -p _site
          cp painel.html painel.css painel.js dados.js dados.json _site/
          cp site/index.html _site/index.html

      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site

      - id: deploy
        uses: actions/deploy-pages@v4
```

- [ ] **Passo 2: página inicial**

`site/index.html`:

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url=painel.html">
<title>Painel de Taxas</title>
</head>
<body>
<p>Abrindo o <a href="painel.html">Painel de Taxas</a>…</p>
</body>
</html>
```

- [ ] **Passo 3: validar o YAML**

Comando:
```bash
python -c "import yaml, sys; d = yaml.safe_load(open('.github/workflows/publicar.yml', encoding='utf-8')); print(sorted(d[True]), [s.get('name') or s.get('uses') for s in d['jobs']['publicar']['steps']])"
```
Se o módulo `yaml` não existir, rode antes `pip install pyyaml`. É só para esta checagem e não entra no `requirements.txt`.
Esperado: a lista de gatilhos é `['push', 'schedule', 'workflow_dispatch']` (o PyYAML lê a chave `on` como `True`), e os 10 passos saem na ordem acima: checkout, setup-python, Dependências, Testes, Restaurar o cache das fontes, Atualizar os dados, Guardar o cache das fontes, Montar o site, upload-pages-artifact e deploy-pages.

- [ ] **Passo 4: README**

Logo abaixo do título `# Painel de Taxas de Mercado`, insira:

```markdown
[![publicar](https://github.com/jonatarodrigues/painel-taxas/actions/workflows/publicar.yml/badge.svg)](https://github.com/jonatarodrigues/painel-taxas/actions/workflows/publicar.yml)

**Ao vivo:** https://jonatarodrigues.github.io/painel-taxas/
```

Na seção "Abrir com duplo clique", acrescente ao fim da lista:

```markdown
- Com o painel aberto pelo `Abrir Painel.bat`, o botão ⟳ no topo roda a
  atualização de novo sem fechar a janela. No site publicado, o mesmo botão
  só busca os dados mais recentes que já foram publicados.
```

Antes de `## Testes`, acrescente:

```markdown
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
```

- [ ] **Passo 5: commit**

Assunto: `ci: publicação no GitHub Pages com atualização agendada`.

---

### Tarefa 8: publicação (executada pelo controlador)

Esta tarefa faz ações externas e irreversíveis: repositório público e push. Ela roda **depois** da revisão final do branch e do merge na `main`, pelo controlador, sem subagente. Os comandos rodam na raiz do projeto.

- [ ] **Passo 1: juntar na `main` e testar**

```bash
git checkout main && git merge --ff-only publicacao && python -m pytest -q && git branch -d publicacao
```

- [ ] **Passo 2: e-mail privativo em todo o histórico**

```bash
git config user.email "13991187+jonatarodrigues@users.noreply.github.com"
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --env-filter '
if [ "$GIT_AUTHOR_EMAIL" = "<e-mail pessoal>" ]; then GIT_AUTHOR_EMAIL="13991187+jonatarodrigues@users.noreply.github.com"; fi
if [ "$GIT_COMMITTER_EMAIL" = "<e-mail pessoal>" ]; then GIT_COMMITTER_EMAIL="13991187+jonatarodrigues@users.noreply.github.com"; fi
' -- --all
git for-each-ref refs/original --format='%(refname)' | xargs -r -n1 git update-ref -d
git log --all --format='%ae %ce' | sort -u
```

Esperado: uma única linha, com o e-mail privativo nas duas colunas.

- [ ] **Passo 3: conferir o que fica público**

```bash
git ls-files | grep -E '^(cache/|dados\.|\.superpowers/|\.remember/|\.playwright-mcp/|capturas/)' ; echo "fim da lista proibida"
git grep -n -i -E 'token|senha|password|api_key' -- . ':!docs' ':!tests/fixtures' || echo "nenhum segredo"
```

Esperado: nada antes de "fim da lista proibida" e "nenhum segredo", ou só ocorrências inocentes, que devem ser lidas uma a uma.

- [ ] **Passo 4: criar o repositório, configurar o Pages e enviar**

```bash
gh repo create jonatarodrigues/painel-taxas --public --source . --remote origin --description "Painel de taxas de mercado do Brasil e do exterior, com correlações e previsões do Boletim Focus"
gh api -X POST repos/jonatarodrigues/painel-taxas/pages -f build_type=workflow
git push -u origin main
```

- [ ] **Passo 5: acompanhar a primeira publicação**

```bash
gh run watch --repo jonatarodrigues/painel-taxas --exit-status $(gh run list --repo jonatarodrigues/painel-taxas --workflow publicar.yml --limit 1 --json databaseId --jq '.[0].databaseId')
```

Depois, abra `https://jonatarodrigues.github.io/painel-taxas/` no navegador (Playwright) e confira:
- a página redireciona para o painel;
- o texto termina com "atualização automática em dias úteis às 20h" e o horário está no fuso de Brasília;
- os avisos. Anote quais séries falharam na nuvem, porque na primeira execução não há cache.

Se o job falhar, leia o log (`gh run view --log-failed`) e relate. Não force nada.
