# RAG-Reviewer - Projeto Piloto

Validação ponta a ponta de um pipeline RAG que detecta violações de três regras de estilo nas linhas adicionadas de Pull Requests. O desempenho é medido com matriz de confusão completa, Precisão, Recall e F1-Score.

**Instituição:** Universidade do Estado do Amazonas (UEA) - TCC-2

---

## Escopo do piloto

| Item | Definição |
|---|---|
| Regras | Seção 5 do `guia_python_pep8.md`, comparações: proibido `== True`, `== False`, `== None` e `!= None`, obrigatório `is` / `is not` com `None`. E um recorte da Seção 2, nomenclatura: funções em `snake_case`, classes em `PascalCase`, e `l`, `O`, `I` proibidos como nome de uma letra (D-002 e sua emenda) |
| Unidade de avaliação | A linha adicionada (D-001) |
| Corpus indexado | Os três guias de `docs/style_guides/`: 52 seções, 52 chunks (D-007) |
| Dataset | 75 PRs sintéticos, 2025 linhas adicionadas, com código conforme o corpus inteiro fora a violação rotulada (D-008). 132 positivas (26 booleanas, 26 de nulos, 16 por sub-regra de nomenclatura, 16 por sub-regra de exceção) e 1893 negativas, das quais 132 são negativos difíceis. 54 PRs com violação e 21 de controle. Esquema em `evaluation/dataset/SCHEMA.md` |
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
    -> união por arquivo (chunk repetido fica com o maior score), ordenação, corte em 8 chunks
    -> LLM: uma chamada por arquivo, com o diff e as normas recuperadas
    -> detecções (linha, norma citada)
    -> comparação com o gabarito, linha a linha
    -> matriz de confusão, Precisão, Recall, F1
```

---

## Resultados

> Os resultados de detecção desta seção foram medidos no dataset anterior, de 30 PRs e só a Seção 5, e serão refeitos na rodada oficial de D-008. Os de recuperação já foram refeitos no dataset atual (75 PRs, três regras).
>
> A avaliação de detecção já reporta as métricas **por regra** e o recall **por sub-regra** (`per_rule` e `per_sub_rule_recall` em `results.json`). O recorte de uma regra são as linhas cujo campo `regra` é ela: as positivas mais os negativos difíceis escritos contra ela. Negativos comuns não pertencem a regra alguma e só entram na matriz global, então a precisão por regra não é comparável à global.

### Recuperação (sem LLM)

`recall@k` é a fração das 132 linhas positivas cuja norma correta aparece entre os k primeiros chunks recuperados **para aquela linha**. `context_precision@5` é a fração dos chunks recuperados que carregam a norma correta. Todas as configurações foram medidas sobre o mesmo corpus; L0 a L2 em coleções temporárias com o modelo em inglês, L0 com o loader e o chunker de `1e21350`.

| Config | recall@1 | recall@3 | recall@5 | context_precision@5 |
|---|---|---|---|---|
| L0 - linha de base: consulta por arquivo, MiniLM em inglês, só denso | 0.2273 | 0.5985 | 0.6364 | 0.1828 |
| L1 - loader e chunker que respeitam blocos cercados | 0.3864 | 0.6515 | 0.7045 | 0.2250 |
| L2 - consulta por linha | 0.1136 | 0.1591 | 0.1591 | 0.1114 |
| L3 - modelo multilíngue | 0.4697 | 0.6136 | 0.6742 | 0.2199 |
| L4 - busca híbrida denso + BM25 com RRF | 0.6667 | 0.8182 | 0.8409 | 0.1894 |
| L4 com o MiniLM em inglês | 0.6212 | 0.8712 | 0.8939 | 0.2182 |

Critério do plano: `recall@5 >= 0.95`, não atingido. Em L4, a Seção 5 e a cs 4.1 têm recall@5 de 1.0 (84 de 84 linhas) e os nomes de classe também (16 de 16). As falhas são todas de nomenclatura: 0 de 16 para nomes de função (`def CalculateTax(...)` traz docstrings, tipo de retorno e funções booleanas, nunca a tabela de convenções) e 11 de 16 para `l`/`O`/`I`. Uma violação de nome não tem texto em comum com a norma que a proíbe.

Três leituras mudaram em relação à medição no dataset antigo (só Seção 5, 60 linhas; ver `docs/agent-reports/2026-09-01-ablacao-retrieval.md`):

- A consulta por arquivo (L0, L1) deixou de ser a pior. Com o código de D-008, cada arquivo passou a ser uma consulta rica; a consulta por linha só compensa com o modelo multilíngue e o BM25.
- Com o BM25 ativo, o modelo em inglês supera o multilíngue (0.89 contra 0.84). O ganho do multilíngue não se sustenta no dataset atual.
- O `recall@k` mede cada linha isolada. Ele não passa pela união por arquivo e pelo corte em 8 chunks do `Retriever`, e por isso não viu o defeito corrigido em `fb05820` (D-008).

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
- Com o BM25 ativo, o modelo de embedding em inglês entrega `recall@5` maior que o multilíngue no dataset atual, então o ganho do modelo multilíngue não se sustenta nesse recorte.
- A Precisão fica abaixo da meta mínima. Os 8 PRs de controle foram todos sinalizados no nível de PR.
- Quatro de cada cinco chunks recuperados não carregam a norma correta (`context_precision@5` = 0.19 em L4).

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
|   |-- dataset/              pilot_dataset.json, SCHEMA.md e validador
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
