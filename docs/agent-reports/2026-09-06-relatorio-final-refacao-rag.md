# Relatório final — Refatoração da camada de RAG

**Data:** 2026-09-06
**Branch:** `refacao-camada-rag`
**Plano executado:** `docs/superpowers/plans/2026-09-01-refacao-camada-rag.md` (13/13 tarefas)
**Spec:** `docs/superpowers/specs/2026-09-01-refacao-camada-rag-design.md`
**Decisões metodológicas:** `docs/DECISIONS.md` (D-001 a D-007)

## Resumo executivo

O objetivo do plano era destravar o RAG-Reviewer: o sistema de recuperação
(retrieval) estava tão ruim que o LLM raramente recebia a norma certa para
avaliar uma violação, o que inviabilizava qualquer medição séria de
precisão/recall de detecção para o TCC. A meta técnica era
**`recall@5 >= 0.95`** no gabarito de 60 linhas do piloto de Seção 5.

Resultado: **`recall@5` foi de 0.15 para 1.0000**, através de uma pilha de
5 configurações cumulativas (L0→L4), cada uma medida isoladamente, incluindo
uma regressão real que foi registrada sem maquiagem. Com o retrieval
corrigido, rodou-se a avaliação oficial de detecção fim-a-fim (LLM real,
30 PRs × 3 repetições) e obteve-se:

| Métrica | Valor (média ± desvio-padrão) | Meta do TCC (§15.3) |
|---|---|---|
| Precisão | 0.6522 ± 0.0000 | ≥ 0.70 — **não atingida** |
| Recall | 1.0000 ± 0.0000 | ≥ 0.65 — atingida |
| F1-Score | 0.7895 ± 0.0000 | ≥ 0.67 — atingida |

O achado central para a seção de discussão do TCC: **o sistema nunca deixa
passar uma violação real** (FN=0 tanto na matriz por linha quanto na matriz
por PR), mas **superssinaliza** — 32 falsos positivos em 300 linhas é o que
derruba a precisão abaixo da meta. Isso não é um bug escondido; é um
resultado medido e reportável.

---

## Parte 1 — Camada de retrieval (Tarefas 1 a 9)

### Tabela de ablação

| Config | O quê | recall@5 | Δ |
|---|---|---|---|
| **L0** | Linha de base (loader/chunker atuais, consulta por arquivo, MiniLM inglês, busca densa, threshold 0.35) | 0.1500 | — |
| **L1** | + loader ciente de cercas de código + chunker estrutural | 0.2167 | +0.0667 |
| **L2** | + consulta por linha (D-001) | 0.0667 | **−0.1500** |
| **L3** | + modelo de embedding multilíngue | 0.7500 | +0.6833 |
| **L4** | + busca híbrida (densa + esparsa BM25, fusão RRF) | **1.0000** | +0.2500 |

Fonte: `docs/agent-reports/2026-09-01-ablacao-retrieval.md`,
`evaluation/retrieval/ablation.py`, `evaluation/retrieval/results_L*.json`.

### O que cada camada corrigiu

**L0 → L1 (correção do loader/chunker, commits `bd2519c`, `62d679b`,
`57a0b60`, `6322385`).** A causa raiz não estava no chunker, e sim no
`document_loader`: comentários `# Correto` / `# Incorreto` dentro de blocos
cercados (```` ```python ````) viravam cabeçalhos Markdown fantasmas,
arrancando os exemplos do corpo da norma. Corrigido em duas frentes: o
loader passou a ignorar cabeçalhos falsos dentro de cercas, e o chunker
passou a tratar blocos cercados como unidades atômicas (nunca corta um
bloco de código ao meio). Ganho real, porém pequeno — granularidade e
idioma ainda dominavam o erro.

**L1 → L2 (consulta por linha, commit `b07e3ac`) — regressão registrada
como está.** A consulta por linha, isoladamente, **piorou** o recall. Uma
linha curta como `if x == True:` carrega pouco sinal semântico sozinha para
um modelo de embedding treinado em inglês, contra um corpus inteiramente em
português — o problema de idioma dominava qualquer ganho de granularidade.
Essa restrição do plano foi cumprida à risca: nenhuma camada teve seu
resultado escondido ou recalibrado para parecer melhor do que é.

**L2 → L3 (modelo de embedding multilíngue, commit `89e0a60`) — maior
ganho isolado.** Escolha por medição, não por intuição: compararam-se
`paraphrase-multilingual-MiniLM-L12-v2` (margem sobre distrator: 0.314,
similaridade PT↔EN: 0.912) e `intfloat/multilingual-e5-small` (margem:
0.045, PT↔EN: 0.954). O e5 vence em similaridade PT↔EN pura, mas colapsa a
margem entre norma/violação e distrator/violação — a métrica que a
ablação realmente precisa. Vencedor: `paraphrase-multilingual-MiniLM-L12-v2`.
Confirma a hipótese da spec: o modelo em inglês era o gargalo dominante do
sistema, não a granularidade da consulta.

**L3 → L4 (busca híbrida densa + esparsa com fusão RRF, commit `23568e8`).**
Padrões como `== True` e `!= None` são casamento lexical exato, não um
problema de significado — um encoder BM25 (`SparseEncoder`, via
`fastembed`, modelo `Qdrant/bm25`) cobre esse lado, enquanto o vetor denso
continua responsável pela paráfrase/tradução. Fusão via Reciprocal Rank
Fusion (Query API do Qdrant: `Prefetch` denso + esparso,
`FusionQuery(fusion=Fusion.RRF)`). Fecha a lacuna: `recall@5` vai de 0.75
para 1.0000, atingindo a meta do plano.

### Teste de remoção (leave-one-out)

Pergunta: a busca híbrida por si só torna a troca de modelo dispensável?
Isso importa porque o modelo multilíngue é a camada mais cara em produção
(~470MB baixados a cada execução do GitHub Actions).

| Config | recall@5 | recall@1 | MRR |
|---|---|---|---|
| L4 (multilíngue + híbrida) | 1.0000 | 0.8333 | 0.9167 |
| L4_sem_multilingue (inglês + híbrida) | **1.0000** | 0.8000 | 0.9000 |

`recall@5` idêntico com o modelo em inglês, no piloto de Seção 5. Isso
acontece porque o gabarito desse piloto (violações de `== True`/`== False`/
`!= None`) é majoritariamente lexical — o BM25 sozinho já encontra a norma
certa; o componente denso ajuda pouco a mais **nesse recorte específico**
(a diferença aparece só em recall@1 e MRR, não em recall@5).

**Isso não invalida a decisão de manter o modelo multilíngue em produção**
— o corpus completo tem normas que não são padrões lexicais exatos
(nomenclatura, tamanho de função, docstrings), onde a paráfrase semântica
multilíngue provavelmente importa mais. A ressalva está registrada no
ADR-002 e no ADR-004; a decisão de manter ou não o modelo em produção fica
a critério do autor, informada por este número. Após o teste, o índice foi
reindexado de volta ao modelo multilíngue antes de rodar a Tarefa 13.

### Guarda de segurança (Tarefa 6, commit `7df6dfc`)

Adicionado `VectorStore.assert_model_matches(embedding_model)`: levanta
`RuntimeError` se a coleção do Qdrant estiver vazia ou se o modelo de
embedding usado na indexação divergir do configurado em tempo de consulta.
Sem essa guarda, uma divergência silenciosa de modelo (reindexar com um
modelo e consultar com outro) degradaria o recall sem qualquer aviso — e
como consultas HNSW por vetor não falham quando os embeddings vêm de
espaços diferentes, o sintoma seria só "os resultados pioraram um pouco",
nunca um erro explícito.

---

## Parte 2 — Ablação, métricas e documentação (Tarefas 10 a 12)

**Tarefa 10 — relatório de ablação** (commit `b244dad`):
`evaluation/retrieval/ablation.py` consolida os 5 (+1 contrafactual)
resultados numa tabela única com Δ por camada; `docs/agent-reports/2026-09-01-ablacao-retrieval.md`
é a análise completa, citada acima.

**Tarefa 11 — bug real corrigido em `evaluation/metrics.py`** (commit
`4101b79`): o regex `_SECTION_5_PATTERN` que deveria detectar citação da
norma de Seção 5 nunca casava com o texto real do corpus ("Seção: 5.
Práticas...") por causa dos dois-pontos — ou seja, a métrica de citação
normativa estava silenciosamente quebrada desde sempre. Corrigido para:

```python
_SECTION_5_PATTERN = re.compile(
    r"se[cç][aã]o[:\s]*5(?!\.\d)\b|section[:\s]*5(?!\.\d)\b", re.IGNORECASE
)
```

(o `(?!\.\d)` evita casar indevidamente com subseções como "5.1"). 43 testes
novos adicionados em `tests/unit/test_metrics.py`, cobrindo classificação
TP/FP/FN/TN, deduplicação, exclusão de alucinações da matriz,
`AggregatedEvaluation` e `check_targets` — `evaluation/metrics.py` não tinha
cobertura de teste alguma antes desta tarefa.

**Tarefa 12 — ADRs reescritos com dados medidos, não suposições** (commit
`51383ae`):
- **ADR-002** (modelo de embedding): documenta o bug de PT↔EN=0.597 da
  reivindicação não-verificada do ADR antigo, a metodologia de margem sobre
  distrator, e o achado do teste de remoção com a ressalva explícita de que
  ele não invalida a decisão para o corpus completo.
- **ADR-003** (modelo de LLM): documenta a descontinuação do
  `llama-3.3-70b-versatile` e a adoção de `qwen/qwen3.8-27b` (D-006), com
  rejeição explícita da família `groq/compound*` (modelos agênticos com
  busca web, que destruiriam a validade interna do estudo de RAG).
- **ADR-004** (novo — busca híbrida): documenta a decisão de RRF
  denso+esparso, o ganho medido L3→L4, e o achado do teste de remoção.
- Cache do modelo de embedding adicionado ao CI (`.github/workflows/rag_reviewer.yml`)
  — o modelo multilíngue pesa ~470MB contra ~90MB do modelo anterior, e o
  workflow tem `timeout-minutes: 10`.

---

## Parte 3 — Avaliação oficial de detecção (Tarefa 13)

### Metodologia (D-005, D-006)

30 PRs do dataset piloto (`evaluation/dataset/pilot_secao5.json`) × 3
repetições, temperatura `0.0`, modelo `qwen/qwen3.8-27b`, sobre o índice de
retrieval na configuração vencedora (L4). Reporte: média ± desvio-padrão de
precisão/recall/F1 entre as 3 repetições; a matriz de confusão publicada é
a da repetição de F1 mediano.

### Resultados

**Métricas primárias (média ± desvio-padrão entre as 3 repetições):**

| Métrica | Valor |
|---|---|
| Precisão | 0.6522 ± 0.0000 |
| Recall | 1.0000 ± 0.0000 |
| F1-Score | 0.7895 ± 0.0000 |

(Desvio-padrão zero nas três métricas: as três repetições, com
temperatura `0.0`, produziram exatamente a mesma matriz de confusão —
apenas o número de detecções brutas variou ligeiramente, 116/117/117, sem
mudar a classificação final linha a linha.)

**Matriz de confusão — nível de linha (repetição de F1 mediano, N=300):**

| | Sistema sinalizou | Sistema não sinalizou |
|---|---|---|
| Linha viola | TP = 60 | FN = 0 |
| Linha não viola | FP = 32 | TN = 208 |

**Matriz de confusão — gate de CI/CD, nível de PR (N=30):**

| | Sistema bloqueia | Sistema não bloqueia |
|---|---|---|
| PR viola | TP = 22 | FN = 0 |
| PR limpo | FP = 8 | TN = 0 |

Os 8 falsos positivos de PR são exatamente os 8 PRs "limpos" do dataset
(PR-023 a PR-030) — nenhum deles passou sem alguma sinalização indevida.

**Métricas secundárias:**
- Acurácia: 0.8933 (marcada como **não-representativa** — conjunto
  desbalanceado, ~80% de linhas negativas, D-004 — não usar para comparar
  desempenho)
- Taxa de alucinação de localização: **0.0000** (0 de 117 detecções
  apontam para uma linha que não existe no diff)
- Precisão de referência normativa entre os TPs: **1.0000** (toda vez que
  o sistema acerta uma violação, ele cita a norma correta)

**Metas do TCC (§15.3):**

| Meta | Resultado |
|---|---|
| Precisão ≥ 0.70 | ❌ Não atingida (0.6522) |
| Recall ≥ 0.65 | ✅ Atingida (1.0000) |
| F1-Score ≥ 0.67 | ✅ Atingida (0.7895) |

### Leitura do resultado

O sistema **nunca deixa passar uma violação real** — FN=0 tanto por linha
quanto por PR. O preço disso é o excesso de sinalização: 32 falsos
positivos em 300 linhas avaliadas, o suficiente para reprovar todos os 8
PRs "limpos" do dataset e derrubar a precisão abaixo da meta de 0.70. Não
há alucinação de localização (o sistema nunca aponta para uma linha
inexistente) nem erro de citação normativa nos acertos — o problema
observado é estritamente de **sobre-sinalização**, não de referência
incorreta ou de invenção de conteúdo. Este é um resultado genuíno para a
seção de discussão do TCC, não uma falha a esconder.

### Como o número foi obtido (nota de auditoria)

A execução real contra a API da Groq levou cerca de 3 dias de tempo-relógio,
não por falha do pipeline, mas pela cota gratuita de 200.000 tokens/dia do
provedor. Três dimensões distintas de rate limit foram encontradas e
tratadas de formas diferentes:

1. **TPM/TPD** (tokens por minuto / por dia): recuperável esperando —
   implementado `_review_with_backoff` em `evaluation/run_evaluation.py`,
   que honra o cabeçalho `Retry-After` da própria API (commit `3f577e3`).
2. **OTPM** (tokens de saída por minuto, teto de 1000 por requisição): não
   recuperável esperando — o `max_tokens=2048` padrão do `LLMClient`
   excedia o teto em toda tentativa, então todos os 5 recuos de espera
   falhavam de forma idêntica. Corrigido passando `max_tokens=900` no
   ponto de instanciação em `run_evaluation.py`, **sem tocar** em
   `rag_reviewer/llm_client.py` (arquivo protegido pelo plano) — commit
   `24bf8fd`.
3. Um `APIConnectionError` (falha de rede pura, sem relação com rate limit)
   derrubou o processo uma vez; não é capturado pelo backoff atual porque
   só trata `groq.RateLimitError`.

Um mecanismo de checkpoint atômico (`evaluation/.eval_checkpoint.json`,
gravação via arquivo temporário + rename, apagado automaticamente ao final
de uma execução bem-sucedida) garantiu que nenhuma das interrupções acima
— nem as duas mortes de processo por causas externas ao código (uma por
suspensão do sistema operacional antes da suspensão ter sido desabilitada
via `powercfg`, outra pelo erro de conexão) — perdesse trabalho já
concluído. Optou-se por manter as 30 PRs completas em vez de reduzir a
amostra para acelerar a execução: os 30 PRs são o próprio gabarito da
D-005, não um parâmetro de repetição ajustável, e reduzir o conjunto
enfraqueceria a validade estatística do número final sem motivo
metodológico.

---

## Arquivos e commits de referência

| Área | Arquivo | Commit(s) |
|---|---|---|
| Loader/chunker | `indexer/document_loader.py`, `indexer/chunker.py` | `bd2519c`, `62d679b`, `57a0b60`, `6322385` |
| Guarda de modelo | `rag_reviewer/vector_store.py` | `7df6dfc` |
| Consulta por linha | `rag_reviewer/retriever.py` | `b07e3ac` |
| Modelo multilíngue | `rag_reviewer/config.py`, `rag_reviewer/embedder.py` | `89e0a60` |
| Busca híbrida RRF | `rag_reviewer/vector_store.py`, `rag_reviewer/retriever.py`, `rag_reviewer/sparse_encoder.py` (novo) | `23568e8` |
| Ablação | `evaluation/retrieval/ablation.py` (novo), `docs/agent-reports/2026-09-01-ablacao-retrieval.md` | `b244dad` |
| Bug de métricas + testes | `evaluation/metrics.py`, `tests/unit/test_metrics.py` (novo) | `4101b79` |
| ADRs | `docs/adr/ADR-002-embedding-model.md`, `ADR-003-llm-choice.md`, `ADR-004-hybrid-retrieval.md` (novo) | `51383ae` |
| Recuo/checkpoint da avaliação | `evaluation/run_evaluation.py` | `3f577e3`, `24bf8fd` |
| **Resultado oficial** | `evaluation/results.json` | **`7c4e77b`** |

## Verificação

Suite de testes completa executada após a Tarefa 13:
`.venv/Scripts/python.exe -m pytest tests/ -q` — todos os testes passam,
exceto uma falha pré-existente e não relacionada
(`test_embedder.py::TestImportError::test_missing_sentence_transformers_raises_import_error`,
um mock que não reflete mais o comportamento real de import, presente desde
antes desta refatoração e fora do escopo do plano).

## Pendências fora de escopo (não é trabalho esquecido)

Registrado no próprio plano e em `docs/TODO-FUTURO.md`: os 30 patches do
dataset são todos diffs de arquivo novo, sem linhas de contexto — então a
regra do `system_prompt.txt` de "não comentar linhas não modificadas" nunca
é exercitada por esta avaliação. Decisão de como (ou se) testar esse caso
fica a critério do autor.

## Conclusão

O plano de 13 tarefas está **100% concluído**. A meta técnica original
(`recall@5 >= 0.95`) foi superada (1.0000). A avaliação oficial de detecção,
rodada contra a API real da Groq sobre o retrieval corrigido, entrega
recall e F1 acima das metas do TCC e uma precisão abaixo da meta — um
resultado honesto, mensurável e defensável, com um mecanismo de causa
identificado (excesso de sinalização, não erro de referência ou
alucinação) para a seção de discussão.
