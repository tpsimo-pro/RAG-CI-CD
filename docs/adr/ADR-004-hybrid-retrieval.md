# ADR-004 — Busca Híbrida Densa + Esparsa com Fusão RRF

**Status:** Aceito
**Data:** 2026-09-03 — Task 9/10 da refação da camada de RAG
**Autor:** Thiago P. Simões
**Contexto:** RAG-Reviewer — TCC, Universidade do Estado do Amazonas (UEA)

---

## Contexto

Mesmo depois de corrigir o loader/chunker (ADR relacionado ao Task 4/5) e
trocar o modelo de embedding para um multilíngue (ADR-002), o retrieval
denso puro atingiu `recall@5 = 0.7500` (configuração L3) — abaixo da meta
de `recall@5 >= 0.95` do plano.

A hipótese testada: `== True` e `!= None` são **padrões lexicais** — strings
literais, não um problema de significado. Um modelo de embedding semântico
não é a ferramenta certa para garantir que uma string exata apareça no
chunk recuperado; ele foi treinado para aproximar *parafraseamentos*, não
para casar tokens exatos. Essa era a evidência por trás dos scores de
similaridade comprimidos entre 0.3 e 0.5 observados na linha de base.

## Decisão

Busca híbrida: vetor **denso** (embedding semântico, ADR-002) + vetor
**esparso BM25** (`Qdrant/bm25` via `fastembed`), combinados por
**Reciprocal Rank Fusion (RRF)** na Query API do Qdrant.

- `rag_reviewer/sparse_encoder.py` — novo módulo, `SparseEncoder.encode()`.
  Sem fallback para "só denso" se o `fastembed` não estiver instalado: o
  encoder falha alto (`ImportError`), nunca degrada a configuração sob
  medição em silêncio.
- `VectorStore.search_hybrid()` — `Prefetch` denso + esparso (limite
  configurável por modalidade antes da fusão), `FusionQuery(fusion=Fusion.RRF)`.
  Sem `score_threshold`: o score pós-fusão é de **posto** (rank), não
  cosseno — um limiar absoluto de 0 a 1 não tem sentido nesse espaço. O
  corte passa a ser só `top_k`, calibrado contra o gabarito.
- `Retriever` — `hybrid=True` é o **default de produção** desde esta
  decisão (parâmetro `hybrid=False` mantido para permitir o caminho
  denso-apenas nos testes e na reprodução das configurações L0–L3 da
  ablação).

## Resultado medido

| Config | recall@1 | recall@3 | recall@5 | MRR |
|---|---|---|---|---|
| L3 (denso multilíngue, sem híbrida) | 0.5333 | 0.6833 | 0.7500 | 0.6103 |
| **L4 (+ híbrida, RRF)** | **0.8333** | **1.0000** | **1.0000** | **0.9167** |

`recall@5` fecha a lacuna até a meta do plano (>= 0.95): **1.0000**, com
`config.hybrid: true` registrado em `results_L4.json` como prova de que a
camada foi de fato exercitada na medição (não apenas implementada e
ignorada pelo harness).

## Teste de remoção: o achado que este ADR precisa registrar sem maquiagem

O contrafactual informativo não é "híbrida sem BM25" (isso é exatamente
L3, já medido). É o oposto: **híbrida sem o modelo multilíngue** — de volta
ao `all-MiniLM-L6-v2`, mantendo BM25 + RRF (detalhe completo em
`docs/agent-reports/2026-09-01-ablacao-retrieval.md`).

| Config | recall@5 |
|---|---|
| L4 (multilíngue + híbrida) | 1.0000 |
| L4_sem_multilingue (inglês + híbrida) | **1.0000** |

**No gabarito específico deste piloto** (30 violações booleanas + 30 de
nulos, todas com padrões lexicais exatos), a camada esparsa sozinha já
resolve o recall — o ganho do modelo multilíngue nesse recorte aparece só
em `recall@1`/MRR (rankeamento mais próximo do topo), não em quem entra no
top-5. Isso **não invalida ADR-002**: o corpus completo tem normas
não-lexicais (nomenclatura de funções, tamanho máximo, docstrings) onde a
paráfrase semântica multilíngue provavelmente segue sendo necessária — só
não foi o fator decisivo *neste* piloto de Seção 5. Registrado para
informar uma decisão futura de custo (o modelo multilíngue soma ~470MB de
download por execução do CI), não para reverter nenhuma decisão aqui.

## Consequências

- **Positivas:** Meta de `recall@5 >= 0.95` atingida; casamento lexical
  exato deixa de depender de um modelo semântico não desenhado para isso;
  falha alta (sem fallback silencioso) se o `fastembed` estiver ausente.
- **Negativas:** Nova dependência (`fastembed>=0.4.0`) e upgrade obrigatório
  do `qdrant-client` (1.9.1 → 1.11.3 — a Query API usada aqui,
  `query_points`/`Prefetch`/`FusionQuery`, não existe na 1.9.1); indexação
  agora gera e armazena dois vetores por chunk (custo de storage e de tempo
  de indexação maior, ainda assim executado offline e fora do caminho
  crítico de revisão de PR).
- **Migração de schema:** a coleção do Qdrant precisou ser recriada — o
  vetor denso passou de anônimo para **nomeado** (`"dense"`), com uma nova
  `sparse_vectors_config` (`"bm25"`). Índices antigos não são compatíveis;
  `make index-recreate` é obrigatório após este ADR.
