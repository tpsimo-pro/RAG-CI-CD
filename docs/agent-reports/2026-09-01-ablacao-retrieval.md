# Ablação da camada de RAG — L0 a L4

**Data:** 2026-09-03
**Território:** `evaluation/retrieval/`, `indexer/document_loader.py`,
`indexer/chunker.py`, `rag_reviewer/vector_store.py`, `rag_reviewer/retriever.py`,
`rag_reviewer/embedder.py`, `rag_reviewer/sparse_encoder.py`, `rag_reviewer/config.py`.

## Objetivo

Medir o ganho isolado de cada mudança na camada de recuperação até atingir
`recall@5 >= 0.95` nas 60 linhas positivas do gabarito (`pilot_secao5.json`),
sem chamar o LLM (avaliação offline, determinística, custo zero de API).

## Tabela de ablação

| Config | recall@1 | recall@3 | recall@5 | context_precision@5 | Δ recall@5 |
|---|---|---|---|---|---|
| **L0** — loader/chunker atuais, consulta por arquivo, MiniLM inglês, denso, threshold 0.35 | 0.0833 | 0.1500 | 0.1500 | 0.1000 | — |
| **L1** — + loader ciente de cercas + chunker estrutural | 0.0833 | 0.1500 | 0.2167 | 0.1133 | +0.0667 |
| **L2** — + consulta por linha (D-001) | 0.0667 | 0.0667 | 0.0667 | 0.0667 | **−0.1500** |
| **L3** — + modelo de embedding multilíngue | 0.5333 | 0.6833 | 0.7500 | 0.2053 | +0.6833 |
| **L4** — + busca híbrida (denso + esparso BM25, fusão RRF) | 0.8333 | 1.0000 | **1.0000** | 0.2000 | +0.2500 |

Gerada por `python -m evaluation.retrieval.ablation`, consumindo
`evaluation/retrieval/results_{L0..L4}.json`.

**Critério do plano (`recall@5 >= 0.95`): atingido em L4 — 1.0000.**

## Leitura por camada

### L0 → L1: correção do loader/chunker (+0.0667)

A causa raiz não era o chunker, era o `document_loader`: comentários
`# Correto` / `# Incorreto` dentro de blocos ```python``` viravam cabeçalhos
Markdown fantasma, arrancando os exemplos do enunciado da norma. Corrigido em
duas frentes — loader ignora cabeçalhos falsos dentro de cercas
(`fix(indexer): loader ignora cabecalhos falsos dentro de blocos cercados`),
chunker nunca parte um bloco cercado ao meio (`fix(indexer): blocos cercados
sao atomicos no chunking`). Ganho real, mas pequeno — a granularidade e o
idioma ainda dominavam o erro.

### L1 → L2: consulta por linha (**−0.1500**, regressão registrada como está)

A consulta por linha por si só **piorou** o recall. Uma linha curta como
`if x == True:` carrega menos sinal semântico isolada do que a concatenação
arquivo+linhas para um modelo treinado em inglês contra um corpus
integralmente em português — o problema de idioma (spec §1.2) dominava
qualquer ganho de granularidade. Registrado sem maquiagem, conforme a
restrição do plano: nenhuma camada tem seu resultado escondido ou
recalibrado para parecer melhor.

### L2 → L3: modelo de embedding multilíngue (+0.6833 — maior ganho isolado)

Escolha por medição, não por intuição (Task 8, Step 1): comparados
`paraphrase-multilingual-MiniLM-L12-v2` (margem sobre distrator: **0.314**,
PT↔EN: 0.912) e `intfloat/multilingual-e5-small` (margem: **0.045**, PT↔EN:
0.954). O e5 vence em similaridade PT↔EN pura, mas colapsa a margem entre
norma/violação e distrator/violação — a métrica que a ablação realmente
precisa. Vencedor: `paraphrase-multilingual-MiniLM-L12-v2`, sem necessidade
dos prefixos `query:`/`passage:` que a família e5 exigiria. Confirma a
hipótese da spec §1.2: o modelo em inglês era o gargalo dominante do
sistema, não a granularidade da consulta.

### L3 → L4: busca híbrida densa + esparsa com fusão RRF (+0.2500)

`== True` e `!= None` são padrões lexicais — strings literais, não um
problema de significado. Um encoder BM25 (`SparseEncoder`, via `fastembed`,
modelo `Qdrant/bm25`) cobre esse lado; o vetor denso continua responsável
pela paráfrase/tradução. Fusão via Reciprocal Rank Fusion (Query API do
Qdrant: `Prefetch` denso + esparso, `FusionQuery(fusion=Fusion.RRF)`).
Fecha a lacuna: `recall@5` vai de 0.75 para 1.0000.

## Teste de remoção (leave-one-out do meio da pilha)

O contrafactual "L4 sem a camada esparsa" é redundante com a própria tabela
— é exatamente L3. O contrafactual que informa é o oposto: **busca híbrida
sem o modelo multilíngue** (volta ao `all-MiniLM-L6-v2`, mantendo BM25 +
RRF). Ele responde à pergunta que a tabela cumulativa não responde: *o
casamento lexical exato torna a troca de modelo dispensável?* Isso importa
porque o modelo multilíngue é a camada mais cara em produção — ~470MB
baixados a cada execução do GitHub Actions.

```bash
EMBEDDING_MODEL=all-MiniLM-L6-v2 python -m indexer.index_pipeline --docs-dir docs/style_guides --recreate
EMBEDDING_MODEL=all-MiniLM-L6-v2 python -m evaluation.retrieval.run_retrieval_eval --label L4_sem_multilingue --per-line --hybrid
```

| Config | recall@1 | recall@3 | recall@5 | context_precision@5 |
|---|---|---|---|---|
| L4 (multilíngue + híbrida) | 0.8333 | 1.0000 | 1.0000 | 0.2000 |
| **L4_sem_multilingue** (inglês + híbrida) | 0.8000 | 1.0000 | **1.0000** | 0.2000 |

**Resultado: recall@5 idêntico (1.0000) com o modelo em inglês.** No gabarito
do piloto (30 violações booleanas + 30 de nulos, todas com padrões lexicais
exatos — `== True`, `== False`, `!= None`), o casamento BM25 por token
sozinho já encontra a norma certa; o componente denso (seja ele inglês ou
multilíngue) contribui pouco a mais nesse recorte específico. A única
diferença aparece em `recall@1` (0.80 vs 0.8333) —
o multilíngue ainda ajuda a colocar a norma certa mais perto do topo do
ranking, só não muda quem entra no top-5.

**Implicação para produção — não decidida por este relatório, registrada
para o ADR-002/004 (Task 12):** se o piloto de Seção 5 for representativo do
padrão de violações que o sistema precisa cobrir (majoritariamente lexicais),
a busca híbrida por si só pode dispensar o download do modelo multilíngue
(~470MB por execução do CI, spec §10.1) sem perda de `recall@5`. Isso **não**
foi decidido aqui — o corpus completo tem normas que não são padrões
lexicais exatos (nomenclatura, tamanho de função, docstrings), onde a
paráfrase semântica multilíngue provavelmente importa mais. A decisão de
manter ou trocar o modelo em produção cabe ao autor, informada por este
número.

Após o teste de remoção, o índice foi **reindexado de volta ao modelo
multilíngue** (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`)
e a guarda da Task 6 (`assert_model_matches`) confirmada contra o índice
restaurado — a Task 13 depende de rodar contra a configuração vencedora, não
contra o contrafactual.

## Critério de sucesso

`recall@5 >= 0.95` — **atingido** na configuração L4 (1.0000). Nenhuma
redução de corpus, nenhum abaixamento de barra (D-007): a meta foi atingida
pela pilha completa de correções, na ordem em que a spec previu maior
impacto.

## Arquivos

- `evaluation/retrieval/ablation.py` (novo) — script de consolidação.
- `evaluation/retrieval/results_{L0,L1,L2,L3,L4,L4_sem_multilingue}.json` —
  resultados brutos por configuração.
