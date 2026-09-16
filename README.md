# RAG-Reviewer

> Ferramenta de governança de código automatizada integrada ao GitHub Actions.
> A cada abertura ou atualização de Pull Request, recupera semanticamente as
> diretrizes organizacionais relevantes às alterações e publica comentários de
> revisão rastreáveis à norma específica violada.

**Artigo:** *RAG-Reviewer: Automação de Governança de Código via GitHub Actions e IA Generativa*  
**Instituição:** Universidade do Estado do Amazonas (UEA)

---

## Como Funciona

```
Desenvolvedor abre PR
       ↓
GitHub Actions dispara o workflow
       ↓
Coleta o diff do PR via GitHub API
       ↓
Gera embedding do diff (all-MiniLM-L6-v2, local)
       ↓
Consulta Qdrant — recupera top-5 chunks do guia de estilo
       ↓
LLM (Groq/Llama 3.3) analisa diff + normas → identifica violações
       ↓
Publica comentários inline no PR com referência à norma violada
       ↓
Se violações CRÍTICAS → emite REQUEST_CHANGES
```

---

## Pré-requisitos

| Ferramenta | Versão | Uso |
|---|---|---|
| Python | 3.11+ | Runtime principal |
| Docker | 24+ | Qdrant local (desenvolvimento) |
| Git | 2.40+ | Controle de versão |

---

## Instalação e Configuração

```bash
# 1. Clonar o repositório
git clone https://github.com/tpsimo-pro/RAG-CI-CD.git
cd RAG-CI-CD

# 2. Criar e ativar ambiente virtual
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. Instalar dependências de produção
make install

# 4. Instalar dependências de desenvolvimento (testes, linting)
make install-dev

# 5. Configurar variáveis de ambiente
cp .env.example .env
# Edite o .env com suas credenciais reais
```

### Variáveis de Ambiente Necessárias

| Variável | Onde obter |
|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) (gratuito) |
| `QDRANT_URL` | [cloud.qdrant.io](https://cloud.qdrant.io) (free tier 1GB) |
| `QDRANT_API_KEY` | Painel do Qdrant Cloud |
| `GITHUB_TOKEN` | Injetado automaticamente pelo GitHub Actions |

---

## Uso

### 1. Subir Qdrant localmente (desenvolvimento)

```bash
make docker-qdrant
# Qdrant disponível em http://localhost:6333
# Dashboard em http://localhost:6333/dashboard
```

### 2. Indexar o guia de estilo

```bash
# Indexa docs/style_guides/ e popula o Qdrant
make index-recreate

# Saída esperada:
# ✅ Indexados N chunks de M documentos.
```

### 3. Executar testes

```bash
make test           # unitários + integração
make test-unit      # somente unitários
make test-integration  # somente integração
make test-cov       # com relatório de cobertura HTML
```

### 4. Avaliação científica (TCC)

```bash
make evaluate
# Executa o reviewer contra o dataset sintético
# Calcula e exibe Precision, Recall e F1-Score
# Salva resultados em evaluation/results.json
```

### 5. Qualidade de código

```bash
make lint           # ruff — verificação de estilo
make lint-fix       # ruff --fix — correção automática
make format         # black — formatação
make typecheck      # mypy — checagem de tipos
```

---

## Estrutura do Projeto

```
RAG-CI-CD/
├── .github/workflows/
│   └── rag_reviewer.yml      # Workflow GitHub Actions (online)
│
├── rag_reviewer/             # Pacote Python principal
│   ├── config.py             # Configurações centralizadas (Pydantic)
│   ├── diff_parser.py        # Coleta e parse do diff via GitHub API
│   ├── embedder.py           # Geração de embeddings (sentence-transformers)
│   ├── vector_store.py       # Interface com Qdrant
│   ├── retriever.py          # Lógica de recuperação RAG
│   ├── llm_client.py         # Interface com Groq API
│   ├── reviewer.py           # Orquestrador do pipeline online
│   ├── github_publisher.py   # Publicação de comentários no PR
│   └── prompts/
│       ├── system_prompt.txt
│       └── review_template.txt
│
├── indexer/                  # Pipeline offline de indexação
│   ├── document_loader.py    # Leitura de Markdown e texto plano
│   ├── chunker.py            # Divisão em chunks com sobreposição
│   └── index_pipeline.py     # Orquestrador: load → chunk → embed → upsert
│
├── evaluation/               # Avaliação científica
│   ├── dataset/
│   │   └── prs_with_violations.json  # Dataset de PRs sintéticos
│   ├── metrics.py            # Cálculo de Precision, Recall, F1
│   └── run_evaluation.py     # Script principal de avaliação
│
├── tests/
│   ├── unit/                 # Testes unitários por módulo
│   └── integration/          # Testes de integração end-to-end
│
├── docs/
│   ├── style_guides/         # Guias de estilo indexados
│   │   └── guia_python_pep8.md
│   └── adr/                  # Architecture Decision Records
│       ├── ADR-001-vector-db.md
│       ├── ADR-002-embedding-model.md
│       └── ADR-003-llm-choice.md
│
├── .env.example              # Template de variáveis de ambiente
├── Makefile                  # Atalhos de desenvolvimento
├── requirements.txt          # Dependências de produção
└── requirements-dev.txt      # Dependências de desenvolvimento
```

---

## Configuração no GitHub Actions

O workflow em `.github/workflows/rag_reviewer.yml` é disparado automaticamente em eventos de Pull Request sobre arquivos `*.py`.

**Secrets necessários no repositório** (`Settings → Secrets → Actions`):

| Secret | Descrição |
|---|---|
| `GROQ_API_KEY` | Chave da API Groq |
| `QDRANT_URL` | URL do cluster Qdrant |
| `QDRANT_API_KEY` | Chave do Qdrant Cloud |

> `GITHUB_TOKEN` é injetado automaticamente pelo Actions — não requer configuração manual.

---

## Decisões Arquiteturais

| Decisão | Escolha | Documento |
|---|---|---|
| Banco de Vetores | Qdrant | [ADR-001](docs/adr/ADR-001-vector-db.md) |
| Modelo de Embedding | `all-MiniLM-L6-v2` | [ADR-002](docs/adr/ADR-002-embedding-model.md) |
| Modelo de Linguagem | Groq / Llama 3.3 70B | [ADR-003](docs/adr/ADR-003-llm-choice.md) |

---

## Status de Implementação

| Componente | Status |
|---|---|
| Pipeline Offline (Indexação) | ✅ Implementado |
| Componente 1 — GitHub Actions Workflow | ✅ Implementado |
| Componente 2 — Diff Parser | ✅ Implementado |
| Componente 3 — RAG (Embedder + VectorStore + Retriever) | ✅ Implementado |
| Componente 4 — LLM Client + Reviewer | ✅ Implementado |
| Componente 5 — GitHub Publisher | ✅ Implementado |
| Testes Unitários | ✅ Implementado |
| Testes de Integração | ✅ Implementado |
| Módulo de Avaliação (Precision/Recall/F1) | ✅ Implementado |
| ADRs de Decisão Arquitetural | ✅ Implementado |

---

## Métricas de Qualidade

```bash
make test-cov    # cobertura de testes (meta: ≥ 80%)
make lint        # linting com ruff (meta: 0 erros)
make evaluate    # métricas científicas (meta: F1 ≥ 0.67)
```
