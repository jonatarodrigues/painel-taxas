# Pendências e observações — painel de taxas (execução de 2026-09-25)

Itens não bloqueantes registrados durante a implementação e a revisão final. Nenhum deles impede o uso do painel.

## Pendências menores (deferidas)

- Task 1: minor (deferred): test_catalogo_tem_as_series_da_spec cobre só 8 dos 29 ids (plan-mandated)
- Task 2: minor (deferred): RespostaVazia sem uso em fontes.py (usada em cache.obter na Task 3); _limpar deduplica antes de ordenar (keep=last = ordem do payload)
- Task 3: minor (deferred): parâmetro 'id' sombreia builtin (plan-mandated); Cache.ler re-envolve índice já DatetimeIndex
- Task 4: minor (deferred): para_mensal deduplica antes de ordenar (keep=last posicional)
- Task 5: minor (deferred): mat e cont em duas compreensões separadas
- Task 6: minor (deferred): busca O(n*m) do valor anterior em ciclos_copom (plan-mandated); sem testes para NaN/desordenado/1 ponto
- Task 7: minor (deferred): 'id' como variável de laço; ramo diaria.empty sem teste; dropna duplicado
- Task 9: observação: eventos auto usam a data de vigência da nova meta (dia seguinte à reunião do Copom); minor (deferred): considerar subtrair 1 dia para exibir a data da decisão
- Task 9: minor (deferred): negativo de test_offline_usa_cache é vazio (baixar nunca é chamado em offline)
- Task 9: minor (deferred): status_derivada depende da ordem de inserção de derivadas(); plano ainda cita '2a' (histórico)
- Task 11: minor (deferred): segmentosJanela só é usada pelas Tasks 12–13; zero séries selecionadas mostra gráfico vazio sem mensagem
- Task 12: minor (deferred): ternário de cor por sinal repetido 3x; painel do nó não filtra por grupos desligados (intencional: visão de dados completa)
- Task 12: minor (deferred): rótulos se sobrepõem em canvas estreito (~526px); considerar esconder rótulos de nós de peso baixo quando escala < 1
- Task 13: minor (deferred): cor do rótulo por limiar fixo 0,55; instância ECharts não descartada no caminho 'Sem dados'

## Observações sobre as fontes de dados

- Task 2: observação (dados): IPEA JPM366_EMBI366 termina em 2024-07-30 (série descontinuada na fonte). Continua útil para histórico; KPI não usa. Avaliar substituto (CDS 5y) em etapa futura.
- Task 9: observação: eventos auto usam a data de vigência da nova meta (dia seguinte à reunião do Copom); minor (deferred): considerar subtrair 1 dia para exibir a data da decisão
- Final: observação (dados): BCB deu Read timeout (30 s) na série 432 em 2 de 3 execuções online; fallback funcionou (cache do dia, status desatualizada propagado a juro_real e dif_selic_fed). Candidato a fix: TIMEOUT maior para BCB ou baixar 432 sem janelas (série tem só ~7 mil pontos)
- Final: observação (dados): em 25/09 à noite o BCB devolveu resposta não-JSON para 1178 e 1 ('Expecting value'); fallback para cache do dia funcionou. Fonte instável; considerar retry com espera maior ou verificação de Content-Type em etapa futura

## Deferidos na revisão final

- Final: deferred (não bloqueiam): testes de resumo_serie mensal-only e spy em test_offline; data do evento auto = vigência; IPEA http; T1–T13 minors já listados
