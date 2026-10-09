# RAG-Reviewer - Projeto Piloto

Validação ponta a ponta de um pipeline RAG que detecta violações de três regras de estilo nas linhas adicionadas de Pull Requests. O desempenho é medido com matriz de confusão completa, Precisão, Recall e F1-Score.

**Instituição:** Universidade do Estado do Amazonas (UEA) - TCC-2

---

## Escopo do piloto

| Item | Definição |
|---|---|
| Regras | 23 normas da PEP 8 em 6 famílias (D-002, D-009, D-010): comparações e `except:` nu (Programming Recommendations), nomenclatura (Naming Conventions), 79 colunas e linhas em branco (Code Lay-out), imports, espaços em expressões e comentário inline. Catálogo em `evaluation/dataset/norms.py` |
| Unidade de avaliação | A linha adicionada (D-001) |
| Corpus indexado | A PEP 8 completa, em inglês, em `docs/style_guides/pep-0008.md`: 40 seções, 43 chunks (D-009) |
| Dataset | 25 PRs sintéticos de 1 a 3 arquivos (35 arquivos: 21 novos e 14 modificados, com `patch` de hunks), 908 linhas adicionadas, ensaio do workflow do GitHub (D-010). 98 linhas positivas, 74 negativos difíceis, 3 ambíguas. 20 PRs com violação e 5 limpos. O ruff é o oráculo do rótulo. Esquema em `evaluation/dataset/SCHEMA.md` |
| LLM | `qwen/qwen3.8-27b` via Groq, temperatura 0.0 (D-005, D-006) |
| Embedding | `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensões) mais BM25 esparso (ADR-002, ADR-004) |
| Banco de vetores | Qdrant (ADR-001) |

---

## Como funciona

```
Indexação (offline)
  docs/style_guides/*.md
    -> document_loader   cabeçalhos (níveis 1 a 4) viram seções; blocos de código cercados ficam intactos
    -> chunker           itens de lista com seus exemplos, sem sobreposição
    -> embedding denso + vetor esparso BM25
    -> Qdrant

Avaliação (para cada PR do dataset)
  linhas adicionadas do arquivo
    -> por linha: embedding denso + BM25
    -> busca híbrida no Qdrant com fusão RRF (top-5 por linha)
    -> união por arquivo (chunk repetido fica com o maior score), ordenação, corte em 8 chunks
    -> LLM: uma chamada por arquivo, com o diff e as normas recuperadas
    -> detecções (linha, norma citada)
    -> comparação com o gabarito, linha a linha
    -> matriz de confusão, Precisão, Recall, F1
```

---

## Resultados

> Os resultados de detecção desta seção são da **rodada 1 de D-010** (dataset realista de 25 PRs e 35 arquivos, 23 normas da PEP 8). Depois dela, 15 dos 40 erros se mostraram erros de rótulo do dataset e foram corrigidos; a **rodada 2**, com o dataset corrigido, deu P 0,86, R 0,79, F1 0,82 (detalhes na seção 0 do relatório). Relatório completo em `docs/RELATORIO-RESULTADOS.md`, que mantém como anexos as rodadas de D-009 (75 PRs, 6 normas) e D-008. Os números não são comparáveis entre rodadas: mudam dataset, normas e gabarito.
>
> A avaliação reporta métricas **por família** (`per_rule`) e o recall **por norma** (`per_sub_rule_recall`) em `results_realista.json`. O recorte de uma família são as linhas cujo campo `regra` é ela: as positivas mais os negativos difíceis escritos contra ela. Negativos comuns não pertencem a família alguma e só entram na matriz global.

### Recuperação (sem LLM)

`recall@k` é a fração das 98 linhas positivas cuja norma correta aparece entre os k primeiros chunks recuperados **para aquela linha**. `context_precision@5` é a fração dos chunks recuperados que carregam a norma correta.

| Config | recall@1 | recall@3 | recall@5 | context_precision@5 |
|---|---|---|---|---|
| Só denso, multilíngue | 0.1327 | 0.1939 | 0.1939 | 0.0827 |
| Busca híbrida denso + BM25 com RRF, multilíngue (produção) | 0.3367 | 0.5816 | 0.6837 | 0.1367 |
| Busca híbrida, MiniLM em inglês | 0.3469 | 0.5714 | 0.6327 | 0.1265 |

Critério do plano: `recall@5 >= 0.95`, não atingido. O LLM não recebe o top-5 por linha, e sim o contexto de 8 chunks por arquivo. Nele, a norma da linha positiva está presente em 54% das linhas (`evaluation/retrieval/context_coverage.py`); com chunks de 256 e de 128 palavras a cobertura cai para 38% e 29%, então o `chunk_size` fica em 512 (D-010).

### Detecção, rodada 1 (1 repetição, temperatura 0.0)

| Métrica | Valor | Meta mínima | Situação |
|---|---|---|---|
| Precisão | 0.8021 | 0.70 | atingida |
| Recall | 0.7857 | 0.65 | atingida |
| F1-Score | 0.7938 | 0.67 | atingida |

Metas de `RAG-Reviewer_Planejamento.md`, seção 15.3. Uma repetição, conforme D-005.

Matriz de confusão por linha (796 linhas): TP = 77, FP = 19, FN = 21, TN = 679. Gate por PR (25 PRs): TP = 19, FP = 5, FN = 1, TN = 0, ou seja, os 5 PRs limpos foram bloqueados. Alucinação de localização 0.0. Precisão da referência normativa 0.78.

Por família, F1: espaços 0.96, nomes 0.91, imports 0.87, recomendações 0.82, layout 0.57, comentários 0.29. Por norma, 13 das 23 têm recall 100% e `import_ordem` (0 de 4, rótulo que se mostrou errado), `comentario_inline` (1 de 6), `lambda_atribuido` e `linha_longa` (1 de 4 cada) são as mais fracas.

Origem dos 40 erros, lidos contra o texto da PEP 8 e o contexto entregue ao LLM: 15 são erro de rótulo do dataset (docstring pública exigida pela PEP 8 e não rotulada, dois negativos que a PEP 8 lista como errados, uma norma de ordem alfabética que a PEP 8 não exige, literais globais ambíguos), 15 são norma ausente do contexto de 8 chunks, 8 são falhas do modelo (aceita `except Exception:` e o `except:` tolerado como violação, não conta colunas) e 2 são acusações duplas benignas.

### Limitações

- O dataset é sintético e escrito pelo autor, o que ameaça a validade externa (D-004). Os erros de rótulo só foram achados depois de ver o resultado; a correção seguiu o texto da PEP 8 e foi registrada em D-010.
- Cerca de 4 positivas por norma: a cobertura por norma é indicação, não estatística.
- A norma chega ao LLM em apenas 54% das linhas positivas; a recuperação é o principal limite do recall.
- A PEP 8 é conhecida pelo LLM, e não há linha de base sem recuperação para separar a contribuição do RAG do conhecimento prévio do modelo.
- Não são medidos a `suggestion` de correção, a `severity` e o comentário publicado no PR; o gate conta qualquer sinalização como bloqueio.

---

## Workflow do GitHub

O GitHub Action `.github/workflows/rag_reviewer.yml` roda em cada PR (`opened`,
`synchronize`, `reopened`) que altere arquivos `.py`. O fluxo (`rag_reviewer/main.py`):

1. `DiffCollector` lista os arquivos do PR pela API e monta o diff de cada `.py`.
2. `Retriever.retrieve_for_diff` recupera as normas da PEP 8 por arquivo (busca
   por linha, união, corte em 8 chunks).
3. O LLM é chamado uma vez por arquivo.
4. `GitHubPublisher` publica uma review `COMMENT` com um comentário inline por
   violação: severidade (`HIGH`, `MEDIUM`, `LOW`), norma da PEP 8 citada e como
   corrigir. Se a PEP 8 não decide o caso, o comentário avisa da ambiguidade.

A PEP 8 é estilo, então o revisor **nunca bloqueia** o PR. Um arquivo cuja chamada
ao LLM falha aparece no sumário como "não revisado". A cada push o Action não
repete comentários que já existem.

Secrets do repositório: `GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`
(`GITHUB_TOKEN` é automático). A coleção usada é `pep8_chunks`. PRs de fork não
recebem secrets, então o Action não roda neles.

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
# esperado: 40 seções e 43 chunks
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

O padrão é 1 repetição, inclusive na execução oficial (D-005): com temperatura 0.0 as 3 repetições anteriores deram desvio-padrão 0. Ele grava `evaluation/results.json` por padrão, sobrescrito a cada execução; use `--output` para não perdê-lo (o resultado de D-009 foi gravado com `--output evaluation/results_pep8.json`, com `QDRANT_COLLECTION=pep8_chunks`). `--repeticoes 3` reproduz a execução com média e desvio-padrão. Se o limite diário da Groq interromper a execução, o progresso fica em `evaluation/.eval_checkpoint.json` e a execução seguinte retoma dele.

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
|   |-- dataset/              pilot_dataset.json, SCHEMA.md e validador
|   |-- retrieval/            Harness de recuperação, ablação L0-L4, resultados congelados
|   |-- metrics.py            Matriz de confusão, Precisão, Recall, F1
|   |-- run_evaluation.py     Avaliação de detecção
|   |-- results.json          Resultado oficial de D-008 (corpus de três guias)
|   |-- results_pep8.json     Resultado oficial de D-009 (PEP 8)
|   `-- results_realista.json Resultado da rodada 1 de D-010 (dataset realista)
|-- scripts/                  Conversão do reST da PEP 8 em Markdown
|-- tests/unit/               Testes unitários
|-- docs/
|   |-- style_guides/         Corpus indexado: pep-0008.md
|   |-- adr/                  ADR-001 a ADR-004
|   |-- agent-reports/        Relatórios da refação e da ablação
|   |-- superpowers/          Spec e plano da refação da camada de RAG
|   |-- DECISIONS.md          Decisões D-001 a D-010
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
