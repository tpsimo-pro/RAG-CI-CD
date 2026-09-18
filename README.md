# RAG-Reviewer - Projeto Piloto

Validação ponta a ponta de um pipeline RAG que detecta violações de uma regra de estilo nas linhas adicionadas de Pull Requests. O desempenho é medido com matriz de confusão completa, Precisão, Recall e F1-Score.

**Instituição:** Universidade do Estado do Amazonas (UEA) - TCC-2

---

## Escopo do piloto

| Item | Definição |
|---|---|
| Regra | Seção 5 do `guia_python_pep8.md`, comparações. Proibido `== True`, `== False`, `== None` e `!= None`. Obrigatório `is` / `is not` com `None` (D-002) |
| Unidade de avaliação | A linha adicionada (D-001) |
| Corpus indexado | Os três guias de `docs/style_guides/`: 52 seções, 52 chunks (D-007) |
| Dataset | 30 PRs sintéticos, 300 linhas adicionadas. 60 positivas (30 booleanas, 30 de nulos) e 240 negativas, das quais 60 são negativos difíceis. 22 PRs com violação e 8 de controle (D-004) |
| LLM | `qwen/qwen3.8-27b` via Groq, temperatura 0.0 (D-005, D-006) |
| Embedding | `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensões) mais BM25 esparso (ADR-002, ADR-004) |
| Banco de vetores | Qdrant (ADR-001) |

---

## Como funciona

```
Indexação (offline)
  docs/style_guides/*.md
    -> document_loader   cabeçalhos viram seções; blocos de código cercados são atômicos
    -> chunker
    -> embedding denso + vetor esparso BM25
    -> Qdrant

Avaliação (para cada PR do dataset)
  linhas adicionadas do arquivo
    -> por linha: embedding denso + BM25
    -> busca híbrida no Qdrant com fusão RRF (top-5 por linha)
    -> união por arquivo, deduplicação, ordenação por score, corte em 8 chunks
    -> LLM: uma chamada por arquivo, com o diff e as normas recuperadas
    -> detecções (linha, norma citada)
    -> comparação com o gabarito, linha a linha
    -> matriz de confusão, Precisão, Recall, F1
```

---

## Resultados

### Recuperação (sem LLM)

`recall@k` é a fração das 60 linhas positivas cuja norma correta aparece entre os k primeiros chunks. `context_precision@5` é a fração dos chunks entregues ao LLM que carregam a norma correta.

| Config | recall@1 | recall@3 | recall@5 | context_precision@5 |
|---|---|---|---|---|
| L0 - linha de base: consulta por arquivo, MiniLM em inglês, só denso | 0.0833 | 0.1500 | 0.1500 | 0.1000 |
| L1 - loader e chunker que respeitam blocos cercados | 0.0833 | 0.1500 | 0.2167 | 0.1133 |
| L2 - consulta por linha | 0.0667 | 0.0667 | 0.0667 | 0.0667 |
| L3 - modelo multilíngue | 0.5333 | 0.6833 | 0.7500 | 0.2053 |
| L4 - busca híbrida denso + BM25 com RRF | 0.8333 | 1.0000 | 1.0000 | 0.2000 |

Critério do plano: `recall@5 >= 0.95`, atingido em L4. Detalhes em `docs/agent-reports/2026-09-01-ablacao-retrieval.md`.

### Detecção (3 repetições, temperatura 0.0)

| Métrica | Média | Desvio-padrão | Meta mínima | Situação |
|---|---|---|---|---|
| Precisão | 0.6522 | 0.0 | 0.70 | não atingida |
| Recall | 1.0000 | 0.0 | 0.65 | atingida |
| F1-Score | 0.7895 | 0.0 | 0.67 | atingida |

Metas de `RAG-Reviewer_Planejamento.md`, seção 15.3.

Matriz de confusão por linha (300 linhas):

| | Previsto positivo | Previsto negativo |
|---|---|---|
| **Real positivo** | TP = 60 | FN = 0 |
| **Real negativo** | FP = 32 | TN = 208 |

Matriz por PR (30 PRs, 22 com violação e 8 de controle): TP = 22, FP = 8, FN = 0, TN = 0.

Taxa de alucinação 0.0 (nenhuma detecção aponta uma linha que não existe no diff). Precisão da referência normativa 1.0 (todo verdadeiro positivo cita a Seção 5). Resultado completo em `evaluation/results.json`.

### Limitações

- O dataset é sintético e escrito pelo autor, o que ameaça a validade externa (D-004).
- Todas as violações do gabarito são lexicais. Com o BM25 ativo, o modelo de embedding em inglês entrega o mesmo `recall@5`, então o ganho do modelo multilíngue não está isolado nesse recorte.
- A Precisão fica abaixo da meta mínima. Os 8 PRs de controle foram todos sinalizados no nível de PR.
- Quatro de cada cinco chunks entregues ao LLM não carregam a norma correta (`context_precision@5` = 0.20).

---

## Pré-requisitos

| Ferramenta | Versão | Uso |
|---|---|---|
| Python | 3.11+ | Runtime |
| Git | 2.40+ | Controle de versão |
| Conta Groq | - | LLM ([console.groq.com](https://console.groq.com)) |
| Qdrant | Cloud (free tier) ou Docker 24+ | Banco de vetores ([cloud.qdrant.io](https://cloud.qdrant.io)) |

---

## Instalação

```bash
git clone https://github.com/tpsimo-pro/RAG-CI-CD.git
cd RAG-CI-CD

python -m venv .venv
.venv\Scripts\activate         # Windows
source .venv/bin/activate      # Linux/macOS

make install
make install-dev
```

Crie um arquivo `.env` na raiz:

```
GROQ_API_KEY=sua_chave
QDRANT_URL=https://seu-cluster.qdrant.io:6333
QDRANT_API_KEY=sua_chave
```

As demais variáveis têm padrão em `rag_reviewer/config.py`: `QDRANT_COLLECTION`, `EMBEDDING_MODEL`, `LLM_MODEL`, `LLM_TEMPERATURE`, `TOP_K_CHUNKS`.

---

## Uso

### 1. Qdrant local (opcional)

```bash
make docker-qdrant
# defina QDRANT_URL=http://localhost:6333 no .env
```

### 2. Indexar o corpus

```bash
make index-recreate
# esperado: 52 seções e 52 chunks
```

A coleção guarda o nome do modelo de embedding. Trocar `EMBEDDING_MODEL` exige reindexar, senão a busca falha em vez de devolver resultado errado.

### 3. Validar o dataset

```bash
python -m evaluation.dataset.validate_pilot_dataset
```

### 4. Medir a recuperação

```bash
python -m evaluation.retrieval.run_retrieval_eval --label MEU_TESTE --per-line --hybrid
python -m evaluation.retrieval.ablation
```

Cada execução grava `evaluation/retrieval/results_<label>.json`. Use um rótulo novo: `L0` a `L4` são as medições congeladas da ablação. No Windows, defina `PYTHONIOENCODING=utf-8` antes de rodar a tabela de ablação.

### 5. Medir a detecção

```bash
make evaluate
python -m evaluation.run_evaluation --output evaluation/results_dev.json
```

O padrão é 1 repetição, inclusive na execução oficial (D-005): com temperatura 0.0 as 3 repetições anteriores deram desvio-padrão 0. Ele grava `evaluation/results.json`, sobrescrito a cada execução; use `--output` para não perdê-lo. `--repeticoes 3` reproduz a execução com média e desvio-padrão. Se o limite diário da Groq interromper a execução, o progresso fica em `evaluation/.eval_checkpoint.json` e a execução seguinte retoma dele.

### 6. Testes e qualidade

```bash
make test-unit
make test-cov
make lint
make format
make typecheck
```

---

## Estrutura do projeto

```
RAG-CI-CD/
|-- rag_reviewer/
|   |-- config.py             Configurações (Pydantic)
|   |-- embedder.py           Embedding denso (sentence-transformers)
|   |-- sparse_encoder.py     Vetores esparsos BM25 (fastembed)
|   |-- vector_store.py       Interface com o Qdrant, busca híbrida com RRF
|   |-- retriever.py          Recuperação por linha adicionada
|   |-- llm_client.py         Cliente da API Groq
|   |-- diff_parser.py        FileDiff, a estrutura do diff de um arquivo
|   `-- prompts/              Prompt de sistema e template de revisão
|-- indexer/
|   |-- document_loader.py    Leitura de Markdown e texto plano
|   |-- chunker.py            Divisão em chunks
|   `-- index_pipeline.py     load -> chunk -> embed -> upsert
|-- evaluation/
|   |-- dataset/              pilot_secao5.json e validador
|   |-- retrieval/            Harness de recuperação, ablação L0-L4, resultados congelados
|   |-- metrics.py            Matriz de confusão, Precisão, Recall, F1
|   |-- run_evaluation.py     Avaliação de detecção
|   `-- results.json          Resultado oficial
|-- tests/unit/               Testes unitários
|-- docs/
|   |-- style_guides/         Corpus indexado
|   |-- adr/                  ADR-001 a ADR-004
|   |-- agent-reports/        Relatórios da refação e da ablação
|   |-- superpowers/          Spec e plano da refação da camada de RAG
|   |-- DECISIONS.md          Decisões D-001 a D-007
|   `-- TODO-FUTURO.md        Backlog
|-- .github/workflows/
|   `-- keep_alive.yml        Consulta periódica ao Qdrant Cloud
|-- todo-asap.txt             Requisitos do TCC-2 que originaram o piloto
|-- Makefile
`-- requirements.txt, requirements-dev.txt
```

---

## Decisões

| Decisão | Escolha | Documento |
|---|---|---|
| Banco de vetores | Qdrant | [ADR-001](docs/adr/ADR-001-vector-db.md) |
| Modelo de embedding | `paraphrase-multilingual-MiniLM-L12-v2` | [ADR-002](docs/adr/ADR-002-embedding-model.md) |
| Modelo de linguagem | `qwen/qwen3.8-27b` via Groq | [ADR-003](docs/adr/ADR-003-llm-choice.md) |
| Recuperação | Híbrida, denso + BM25 com RRF | [ADR-004](docs/adr/ADR-004-hybrid-retrieval.md) |

As decisões metodológicas D-001 a D-007 (unidade de avaliação, regra do piloto, composição do dataset, determinismo do LLM, escopo) estão em [docs/DECISIONS.md](docs/DECISIONS.md).
