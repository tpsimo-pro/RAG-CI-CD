# RAG-Reviewer - Projeto Piloto

Validação ponta a ponta de um pipeline RAG que detecta violações de três regras de estilo nas linhas adicionadas de Pull Requests. O desempenho é medido com matriz de confusão completa, Precisão, Recall e F1-Score.

**Instituição:** Universidade do Estado do Amazonas (UEA) - TCC-2

---

## Escopo do piloto

| Item | Definição |
|---|---|
| Regras | Três regras da PEP 8 (D-002, D-009): comparações (`== True`, `== False`, `== None` e `!= None` são proibidos; use `is` / `is not` com `None`), nomenclatura (funções em `snake_case`, classes em `CapWords`, `l`, `O` e `I` proibidos como nome) e `except:` nu (só é tolerado se o handler registra o traceback ou relança com `raise`) |
| Unidade de avaliação | A linha adicionada (D-001) |
| Corpus indexado | A PEP 8 completa, em inglês, em `docs/style_guides/pep-0008.md`: 40 seções, 43 chunks (D-009) |
| Dataset | 75 PRs sintéticos, 2025 linhas adicionadas, com código conforme a PEP 8 fora a violação rotulada (D-008, D-009). 118 positivas (26 booleanas, 26 de nulos, 16 por sub-regra de nomenclatura, 18 de `except:` nu) e 1907 negativas, das quais 146 são negativos difíceis. 54 PRs com violação e 21 de controle. Esquema em `evaluation/dataset/SCHEMA.md` |
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

> Todos os resultados desta seção são da rodada de D-009: corpus da PEP 8, dataset de 75 PRs, três regras da PEP 8. Relatório completo em `docs/RELATORIO-RESULTADOS.md`, que mantém como anexo a rodada anterior (D-008, corpus de três guias). As duas rodadas não são comparáveis um a um: mudaram o corpus, as regras de exceção e o prompt.
>
> A avaliação de detecção reporta as métricas **por regra** e o recall **por sub-regra** (`per_rule` e `per_sub_rule_recall` em `results_pep8.json`). O recorte de uma regra são as linhas cujo campo `regra` é ela: as positivas mais os negativos difíceis escritos contra ela. Negativos comuns não pertencem a regra alguma e só entram na matriz global, então a precisão por regra não é comparável à global.

### Recuperação (sem LLM)

`recall@k` é a fração das 118 linhas positivas cuja norma correta aparece entre os k primeiros chunks recuperados **para aquela linha**. `context_precision@5` é a fração dos chunks recuperados que carregam a norma correta.

| Config | recall@1 | recall@3 | recall@5 | context_precision@5 |
|---|---|---|---|---|
| Consulta por arquivo, multilíngue, só denso | 0.0169 | 0.0169 | 0.0169 | 0.0169 |
| Consulta por linha, multilíngue, só denso | 0.0424 | 0.0763 | 0.0763 | 0.0458 |
| Busca híbrida denso + BM25 com RRF, multilíngue (produção) | 0.2966 | 0.6186 | 0.7373 | 0.1475 |
| Busca híbrida, MiniLM em inglês | 0.4322 | 0.6610 | 0.7288 | 0.1458 |

Critério do plano: `recall@5 >= 0.95`, não atingido (em D-008, o híbrido multilíngue deu 0.84). A busca híbrida recupera 100% das linhas de comparação com booleano e de `except:` nu, 77% das de `None`, e 0% das de nome de função: a norma é prosa e a consulta é código sem palavra em comum. O `recall@k` mede cada linha isolada, sem a união por arquivo e o corte em 8 chunks do `Retriever`. O chunk de 512 palavras foi o melhor entre os testados (256, 128 e 64 deram recall@5 menor).

### Detecção (1 repetição, temperatura 0.0)

| Métrica | Valor | Meta mínima | Situação |
|---|---|---|---|
| Precisão | 0.9583 | 0.70 | atingida |
| Recall | 0.9746 | 0.65 | atingida |
| F1-Score | 0.9664 | 0.67 | atingida |

Metas de `RAG-Reviewer_Planejamento.md`, seção 15.3. Uma repetição, conforme D-005. Em D-008: 0.8722, 0.8788, 0.8755.

Matriz de confusão por linha (2.025 linhas):

| | Previsto positivo | Previsto negativo |
|---|---|---|
| **Real positivo** | TP = 115 | FN = 3 |
| **Real negativo** | FP = 5 | TN = 1902 |

Por regra: recomendações (comparações) com F1 1.0, nomes com F1 0.98, `except:` nu com F1 0.84. Recall por sub-regra: 1.0 em `booleano`, `nulo`, `nome_classe` e `nome_proibido`; 0.94 em `nome_funcao`; 0.89 em `except_nu` (16 de 18).

Matriz por PR (75 PRs, 54 com violação e 21 de controle): TP = 52, FP = 3, FN = 2, TN = 18.

Taxa de alucinação 0.0. Precisão da referência normativa 0.9478. Resultado completo em `evaluation/results_pep8.json`.

### Limitações

- O dataset é sintético e escrito pelo autor, o que ameaça a validade externa (D-004).
- A PEP 8 é conhecida pelos LLMs. O recall de detecção (0.97) supera o de recuperação (0.74), e não há linha de base sem recuperação, então não se separa a contribuição do RAG da do conhecimento prévio do modelo.
- Quatro dos cinco FPs são de exceção: `except Exception:`, que a PEP 8 recomenda, e os dois casos em que ela tolera o `except:` nu (o handler registra o traceback ou relança).
- Parte da melhora sobre D-008 vem de um corpus mais estreito: normas fora do piloto, que geravam FPs, deixaram de estar no corpus.
- `except_nu` tem 18 positivas; os recortes por sub-regra são pequenos.
- Quatro de cada cinco chunks recuperados não carregam a norma correta (`context_precision@5` = 0.15 na busca híbrida).

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
|   `-- results_pep8.json     Resultado oficial de D-009 (PEP 8)
|-- scripts/                  Conversão do reST da PEP 8 em Markdown
|-- tests/unit/               Testes unitários
|-- docs/
|   |-- style_guides/         Corpus indexado: pep-0008.md
|   |-- adr/                  ADR-001 a ADR-004
|   |-- agent-reports/        Relatórios da refação e da ablação
|   |-- superpowers/          Spec e plano da refação da camada de RAG
|   |-- DECISIONS.md          Decisões D-001 a D-009
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
