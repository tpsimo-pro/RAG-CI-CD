# RAG-Reviewer: Planejamento Detalhado de Implementação

> **Documento de Planejamento Técnico**  
> Baseado no artigo: *RAG-Reviewer: Automação de Governança de Código via GitHub Actions e Inteligência Artificial Generativa*  
> Universidade do Estado do Amazonas (UEA)

---

## Sumário

1. [Visão Geral do Projeto](#1-visão-geral-do-projeto)
2. [Arquitetura do Sistema](#2-arquitetura-do-sistema)
3. [Pré-requisitos e Ambiente](#3-pré-requisitos-e-ambiente)
4. [Estrutura de Diretórios](#4-estrutura-de-diretórios)
5. [Fase 1 — Indexação do Guia de Estilo (Pipeline Offline)](#5-fase-1--indexação-do-guia-de-estilo-pipeline-offline)
6. [Fase 2 — Pipeline de Revisão de PR (Pipeline Online)](#6-fase-2--pipeline-de-revisão-de-pr-pipeline-online)
7. [Componente 1 — Workflow GitHub Actions](#7-componente-1--workflow-github-actions)
8. [Componente 2 — Coleta e Pré-processamento do Diff](#8-componente-2--coleta-e-pré-processamento-do-diff)
9. [Componente 3 — Módulo RAG (Recuperação Semântica)](#9-componente-3--módulo-rag-recuperação-semântica)
10. [Componente 4 — Módulo de Geração com LLM](#10-componente-4--módulo-de-geração-com-llm)
11. [Componente 5 — Publicação de Comentários via GitHub API](#11-componente-5--publicação-de-comentários-via-github-api)
12. [Banco de Vetores — Qdrant](#12-banco-de-vetores--qdrant)
13. [Modelo de Dados](#13-modelo-de-dados)
14. [Segredos e Configurações](#14-segredos-e-configurações)
15. [Avaliação e Métricas](#15-avaliação-e-métricas)
16. [Cronograma de Desenvolvimento](#16-cronograma-de-desenvolvimento)
17. [Riscos e Mitigações](#17-riscos-e-mitigações)
18. [Checklist de Entrega](#18-checklist-de-entrega)

---

## 1. Visão Geral do Projeto

### 1.1 Objetivo

O **RAG-Reviewer** é uma ferramenta de governança de código automatizada que, integrada ao GitHub Actions, é acionada a cada abertura ou atualização de Pull Request. Ela recupera semanticamente as diretrizes organizacionais relevantes às alterações submetidas e publica comentários de revisão rastreáveis à norma específica violada.

### 1.2 Problema Endereçado

| Situação Atual | Situação Desejada |
|---|---|
| Revisores humanos gastam tempo identificando violações já documentadas | Sistema automatizado detecta violações antes da revisão humana |
| Guias de estilo em PDFs/Wikis nunca são consultados no momento do PR | Normas são recuperadas semanticamente e aplicadas a cada PR |
| Linters só verificam regras sintáticas predefinidas | Sistema interpreta diretrizes em linguagem natural |
| LLMs genéricos (Copilot, CodeRabbit) ignoram normas internas | LLM contextualizado com o acervo normativo da organização |

### 1.3 Fluxo de Alto Nível

```
Desenvolvedor abre/atualiza PR
         │
         ▼
GitHub Actions dispara o workflow
         │
         ▼
Coleta o diff do PR via GitHub API
         │
         ▼
Converte diff em vetor de embeddings
         │
         ▼
Consulta banco de vetores Qdrant
(recupera top-K trechos do guia de estilo)
         │
         ▼
LLM compara diff + normas recuperadas
(identifica violações)
         │
         ▼
Publicação de comentários inline no PR
(via GitHub API / Octokit)
         │
         ▼
Se violações críticas → request_changes
```

---

## 2. Arquitetura do Sistema

### 2.1 Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────┐
│                        GitHub                                │
│  ┌──────────────┐    ┌──────────────────────────────────┐   │
│  │  Pull Request │───▶│      GitHub Actions Runner        │   │
│  └──────────────┘    │  ┌────────────────────────────┐  │   │
│                       │  │   rag_reviewer.yml (YAML)  │  │   │
│                       │  └────────────┬───────────────┘  │   │
│                       └───────────────┼──────────────────┘   │
└───────────────────────────────────────┼──────────────────────┘
                                        │
                    ┌───────────────────▼───────────────────────┐
                    │          RAG-Reviewer Core (Python)         │
                    │                                             │
                    │  ┌─────────────┐   ┌─────────────────┐   │
                    │  │ diff_parser │   │  embedder        │   │
                    │  │ .py         │──▶│  (sentence-      │   │
                    │  └─────────────┘   │  transformers)   │   │
                    │                    └────────┬────────┘   │
                    │                             │             │
                    │                    ┌────────▼────────┐   │
                    │                    │  Qdrant Client   │   │
                    │                    │  (vector search) │   │
                    │                    └────────┬────────┘   │
                    │                             │             │
                    │                    ┌────────▼────────┐   │
                    │                    │  LLM Client      │   │
                    │                    │  (Claude/OpenAI) │   │
                    │                    └────────┬────────┘   │
                    │                             │             │
                    │                    ┌────────▼────────┐   │
                    │                    │  GitHub API      │   │
                    │                    │  (Octokit/REST)  │   │
                    │                    └─────────────────┘   │
                    └─────────────────────────────────────────┘
                                        │
                    ┌───────────────────▼───────────────────────┐
                    │              Qdrant (Vector DB)             │
                    │   Collection: style_guide_chunks            │
                    │   [ chunk_text | embedding | metadata ]     │
                    └─────────────────────────────────────────────┘
```

### 2.2 Pipelines

O sistema possui **dois pipelines distintos**:

| Pipeline | Quando executa | Responsabilidade |
|---|---|---|
| **Offline (Indexação)** | Manualmente ou ao atualizar o guia de estilo | Processa o guia de estilo, gera embeddings e popula o Qdrant |
| **Online (Revisão)** | A cada abertura/atualização de PR | Coleta diff, consulta Qdrant, gera revisão, publica comentários |

---

## 3. Pré-requisitos e Ambiente

### 3.1 Ferramentas Necessárias

| Ferramenta | Versão Mínima | Propósito |
|---|---|---|
| Python | 3.11+ | Linguagem principal do core |
| Docker | 24+ | Executar Qdrant localmente em dev |
| Node.js | 20 LTS | Scripts auxiliares com Octokit (opcional) |
| Git | 2.40+ | Controle de versão |

### 3.2 Dependências Python

```txt
# requirements.txt

# Embeddings e NLP
sentence-transformers==3.0.1
torch==2.3.0

# Banco de vetores
qdrant-client==1.9.1

# Orquestração LLM
langchain==0.2.6
langchain-openai==0.1.14        # ou langchain-anthropic
openai==1.35.0                  # se usar OpenAI/Claude via API compatível
anthropic==0.28.0               # se usar Anthropic SDK diretamente

# Processamento de documentos
pypdf==4.2.0                    # leitura de PDFs
python-docx==1.1.0              # leitura de .docx
markdown==3.6                   # leitura de .md

# GitHub API
PyGithub==2.3.0
requests==2.32.3

# Utilitários
python-dotenv==1.0.1
pydantic==2.7.4
tiktoken==0.7.0                 # contagem de tokens
rich==13.7.1                    # logging formatado
```

### 3.3 Serviços Externos

| Serviço | Plano gratuito suficiente? | Configuração necessária |
|---|---|---|
| **Qdrant Cloud** | Sim (1 GB free) | `QDRANT_URL` + `QDRANT_API_KEY` |
| **OpenAI API** | Não (pay-as-you-go) | `OPENAI_API_KEY` |
| **Anthropic API** | Não (pay-as-you-go) | `ANTHROPIC_API_KEY` |
| **GitHub** | Sim | `GITHUB_TOKEN` (gerado automaticamente pelo Actions) |

> **Alternativa local/gratuita:** usar Qdrant em Docker + modelo de embedding local (`all-MiniLM-L6-v2`) + LLM local via Ollama (`codellama`, `mistral`).

---

## 4. Estrutura de Diretórios

```
rag-reviewer/
│
├── .github/
│   └── workflows/
│       └── rag_reviewer.yml          # Workflow principal do GitHub Actions
│
├── rag_reviewer/                     # Pacote Python principal
│   ├── __init__.py
│   ├── config.py                     # Configurações centralizadas (env vars, defaults)
│   ├── diff_parser.py                # Coleta e parse do diff do PR
│   ├── embedder.py                   # Geração de embeddings
│   ├── vector_store.py               # Interface com Qdrant
│   ├── retriever.py                  # Lógica de recuperação RAG
│   ├── llm_client.py                 # Interface com LLM (OpenAI/Anthropic)
│   ├── reviewer.py                   # Orquestra diff → retrieval → LLM → comentários
│   ├── github_publisher.py           # Publicação de comentários via GitHub API
│   └── prompts/
│       ├── system_prompt.txt         # Prompt de sistema do LLM
│       └── review_template.txt       # Template do prompt de revisão
│
├── indexer/                          # Pipeline offline de indexação
│   ├── __init__.py
│   ├── document_loader.py            # Leitura de PDF, MD, DOCX
│   ├── chunker.py                    # Divisão de documentos em chunks
│   └── index_pipeline.py            # Orquestrador: carrega → chunka → indexa
│
├── evaluation/                       # Scripts de avaliação (Fase 5 da DSR)
│   ├── dataset/
│   │   ├── prs_with_violations.json  # Dataset de PRs com violações catalogadas
│   │   └── ground_truth.json         # Gabarito: violações esperadas por PR
│   ├── metrics.py                    # Cálculo de Precision, Recall, F1
│   ├── lead_time_analysis.py         # Análise de lead time
│   └── run_evaluation.py             # Script principal de avaliação
│
├── docs/
│   ├── style_guides/                 # Guias de estilo da organização (fonte de verdade)
│   │   ├── coding_standards.md
│   │   ├── clean_code_guide.pdf
│   │   └── architecture_patterns.md
│   └── adr/                          # Architecture Decision Records
│       ├── ADR-001-vector-db.md
│       ├── ADR-002-embedding-model.md
│       └── ADR-003-llm-choice.md
│
├── tests/
│   ├── unit/
│   │   ├── test_diff_parser.py
│   │   ├── test_chunker.py
│   │   ├── test_embedder.py
│   │   └── test_retriever.py
│   └── integration/
│       ├── test_rag_pipeline.py
│       └── test_github_publisher.py
│
├── scripts/
│   ├── run_indexer.sh                # Executa a pipeline de indexação
│   └── run_local_review.sh           # Testa o reviewer localmente com um PR fake
│
├── .env.example                      # Template de variáveis de ambiente
├── Makefile                          # Atalhos de dev (make index, make test, etc.)
├── requirements.txt
├── requirements-dev.txt              # pytest, black, ruff, mypy
└── README.md
```

---

## 5. Fase 1 — Indexação do Guia de Estilo (Pipeline Offline)

Esta fase é executada **uma única vez** ao configurar o sistema, e novamente sempre que o guia de estilo for atualizado.

### 5.1 Etapa 1 — Carregamento de Documentos

**Arquivo:** `indexer/document_loader.py`

```python
"""
Suporte a múltiplos formatos de documentos normativos.
Retorna lista de objetos Document(text, metadata).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List

@dataclass
class Document:
    text: str
    source: str          # caminho do arquivo de origem
    page: int = 0        # número da página (para PDFs)
    section: str = ""    # título da seção (para Markdown)

class DocumentLoader:
    """Carrega documentos de PDF, Markdown ou DOCX."""

    def load(self, path: str | Path) -> List[Document]:
        path = Path(path)
        if path.suffix == ".pdf":
            return self._load_pdf(path)
        elif path.suffix in (".md", ".txt"):
            return self._load_markdown(path)
        elif path.suffix == ".docx":
            return self._load_docx(path)
        else:
            raise ValueError(f"Formato não suportado: {path.suffix}")

    def _load_pdf(self, path: Path) -> List[Document]: ...
    def _load_markdown(self, path: Path) -> List[Document]: ...
    def _load_docx(self, path: Path) -> List[Document]: ...
```

**Lógica de carregamento:**
- **PDF:** usar `pypdf.PdfReader`, iterar por páginas, extrair texto por página, preservar número da página como metadado.
- **Markdown:** usar `markdown` + `BeautifulSoup` para extrair seções por cabeçalho (`##`, `###`), preservar título da seção como metadado.
- **DOCX:** usar `python-docx`, iterar parágrafos, agrupar por estilo de cabeçalho.

### 5.2 Etapa 2 — Chunking

**Arquivo:** `indexer/chunker.py`

O chunking é crítico para a qualidade da recuperação. Chunks muito grandes reduzem a precisão do retrieval; chunks muito pequenos perdem contexto.

```python
"""
Estratégia de chunking: janela deslizante com sobreposição.
"""

class RecursiveChunker:
    def __init__(
        self,
        chunk_size: int = 512,    # tokens por chunk
        chunk_overlap: int = 64,  # tokens de sobreposição
    ): ...

    def split(self, documents: List[Document]) -> List[Chunk]:
        """
        Divide cada Document em Chunks menores.
        Preserva os metadados do documento pai em cada chunk.
        Usa fronteiras naturais: parágrafos > frases > palavras.
        """
        ...
```

**Parâmetros recomendados:**

| Parâmetro | Valor | Justificativa |
|---|---|---|
| `chunk_size` | 512 tokens | Balanceia contexto e precisão de retrieval |
| `chunk_overlap` | 64 tokens | Evita quebra de regras que cruzam fronteiras de chunk |
| Separadores | `\n\n`, `\n`, `. ` | Respeita estrutura natural do documento |

### 5.3 Etapa 3 — Geração de Embeddings

**Arquivo:** `rag_reviewer/embedder.py`

**Modelos de embedding recomendados:**

| Modelo | Dimensões | Custo | Melhor para |
|---|---|---|---|
| `all-MiniLM-L6-v2` | 384 | Gratuito (local) | Prototipagem, sem custo |
| `text-embedding-3-small` | 1536 | ~$0.02/1M tokens | Produção com OpenAI |
| `text-embedding-3-large` | 3072 | ~$0.13/1M tokens | Alta precisão |

```python
from sentence_transformers import SentenceTransformer
from typing import List
import numpy as np

class Embedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def embed(self, texts: List[str]) -> np.ndarray:
        """Retorna matriz (N, D) de embeddings normalizados."""
        return self.model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=True,
        )
```

### 5.4 Etapa 4 — Inserção no Qdrant

**Arquivo:** `indexer/index_pipeline.py`

```python
"""
Pipeline completo: load → chunk → embed → upsert no Qdrant.
"""

def run_indexing(
    docs_dir: str,
    collection_name: str = "style_guide_chunks",
    recreate: bool = False,
):
    loader = DocumentLoader()
    chunker = RecursiveChunker(chunk_size=512, chunk_overlap=64)
    embedder = Embedder()
    store = VectorStore(collection_name=collection_name)

    if recreate:
        store.recreate_collection(vector_size=embedder.vector_size)

    all_docs = []
    for path in Path(docs_dir).rglob("*"):
        if path.suffix in (".pdf", ".md", ".docx", ".txt"):
            all_docs.extend(loader.load(path))

    chunks = chunker.split(all_docs)
    texts = [c.text for c in chunks]
    embeddings = embedder.embed(texts)

    store.upsert(chunks=chunks, embeddings=embeddings)
    print(f"✅ Indexados {len(chunks)} chunks de {len(all_docs)} documentos.")
```

---

## 6. Fase 2 — Pipeline de Revisão de PR (Pipeline Online)

Esta é a pipeline principal, executada **automaticamente** a cada evento de PR.

### 6.1 Sequência de Execução

```
1. GitHub Actions dispara o job ao detectar evento pull_request
2. Runner faz checkout do repositório
3. Script Python principal é chamado com variáveis de ambiente do PR
4. diff_parser.py coleta o diff via GitHub API
5. embedder.py converte o diff em vetor
6. retriever.py consulta o Qdrant e retorna top-K chunks
7. llm_client.py envia (diff + chunks) ao LLM e recebe lista de violações
8. github_publisher.py publica comentários inline no PR
9. Se violações críticas → chama GitHub API para "request changes"
```

---

## 7. Componente 1 — Workflow GitHub Actions

**Arquivo:** `.github/workflows/rag_reviewer.yml`

```yaml
name: RAG-Reviewer

on:
  pull_request:
    types: [opened, synchronize, reopened]
    # Filtra apenas alterações em arquivos de código relevantes
    paths:
      - "src/**"
      - "lib/**"
      - "app/**"
      - "*.py"
      - "*.js"
      - "*.ts"
      - "*.java"

permissions:
  contents: read
  pull-requests: write   # necessário para postar comentários

jobs:
  review:
    runs-on: ubuntu-latest
    timeout-minutes: 10   # evita execuções travadas

    steps:
      - name: Checkout do repositório
        uses: actions/checkout@v4
        with:
          fetch-depth: 0   # necessário para acessar o histórico completo do diff

      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Instalar dependências
        run: pip install -r requirements.txt

      - name: Executar RAG-Reviewer
        env:
          GITHUB_TOKEN:       ${{ secrets.GITHUB_TOKEN }}
          OPENAI_API_KEY:     ${{ secrets.OPENAI_API_KEY }}
          QDRANT_URL:         ${{ secrets.QDRANT_URL }}
          QDRANT_API_KEY:     ${{ secrets.QDRANT_API_KEY }}
          PR_NUMBER:          ${{ github.event.pull_request.number }}
          REPO_FULL_NAME:     ${{ github.repository }}
          PR_BASE_SHA:        ${{ github.event.pull_request.base.sha }}
          PR_HEAD_SHA:        ${{ github.event.pull_request.head.sha }}
        run: |
          python -m rag_reviewer.main
```

**Pontos de atenção no workflow:**
- `fetch-depth: 0` é obrigatório para que o diff entre `base.sha` e `head.sha` esteja disponível.
- `pull-requests: write` é necessário para publicar comentários; sem essa permissão, a API retornará 403.
- `timeout-minutes: 10` previne custo excessivo em caso de loops ou chamadas de API travadas.
- O filtro `paths` evita disparo desnecessário em alterações de documentação ou configuração.

---

## 8. Componente 2 — Coleta e Pré-processamento do Diff

**Arquivo:** `rag_reviewer/diff_parser.py`

### 8.1 Coleta do Diff

```python
"""
Coleta o diff do PR via GitHub REST API e estrutura para uso no RAG.
"""

import os
import requests
from dataclasses import dataclass, field
from typing import List

@dataclass
class FileDiff:
    filename: str         # ex: "src/services/user_service.py"
    patch: str            # texto bruto do diff (linhas +/-)
    status: str           # "added" | "modified" | "deleted"
    additions: int = 0
    deletions: int = 0
    added_lines: List[str] = field(default_factory=list)   # só linhas adicionadas

@dataclass
class PullRequestDiff:
    pr_number: int
    repo: str
    files: List[FileDiff]
    total_additions: int
    total_deletions: int

class DiffCollector:
    """Coleta e estrutura o diff de um PR via GitHub API."""

    def __init__(self):
        self.token = os.environ["GITHUB_TOKEN"]
        self.repo = os.environ["REPO_FULL_NAME"]
        self.pr_number = int(os.environ["PR_NUMBER"])
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def collect(self) -> PullRequestDiff:
        url = f"https://api.github.com/repos/{self.repo}/pulls/{self.pr_number}/files"
        files_data = self._paginate(url)

        files = []
        for f in files_data:
            patch = f.get("patch", "")
            added_lines = [
                line[1:]  # remove o prefixo "+"
                for line in patch.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            ]
            files.append(FileDiff(
                filename=f["filename"],
                patch=patch,
                status=f["status"],
                additions=f["additions"],
                deletions=f["deletions"],
                added_lines=added_lines,
            ))

        return PullRequestDiff(
            pr_number=self.pr_number,
            repo=self.repo,
            files=files,
            total_additions=sum(f.additions for f in files),
            total_deletions=sum(f.deletions for f in files),
        )

    def _paginate(self, url: str) -> list:
        """Coleta todas as páginas da API."""
        results = []
        while url:
            response = requests.get(url, headers=self.headers, params={"per_page": 100})
            response.raise_for_status()
            results.extend(response.json())
            url = response.links.get("next", {}).get("url")
        return results
```

### 8.2 Pré-processamento do Diff para Consulta Vetorial

O diff bruto é muito "ruidoso" para ser embedado diretamente. É necessário:

1. **Filtrar apenas linhas adicionadas** — linhas removidas (`-`) não precisam de revisão.
2. **Remover metadados do diff** (`@@` hunks, `---`, `+++`).
3. **Agrupar por arquivo** — criar um texto de consulta por arquivo, incluindo o nome do arquivo como contexto.
4. **Truncar se necessário** — se o diff de um arquivo exceder o limite de tokens do modelo de embedding (geralmente 512 tokens), truncar com resumo.

```python
def build_query_text(file_diff: FileDiff) -> str:
    """Constrói o texto de consulta para o RAG a partir de um FileDiff."""
    header = f"Arquivo: {file_diff.filename}\n"
    body = "\n".join(file_diff.added_lines)
    return (header + body)[:2000]  # limita para evitar tokens excessivos
```

---

## 9. Componente 3 — Módulo RAG (Recuperação Semântica)

**Arquivo:** `rag_reviewer/retriever.py`

### 9.1 Interface com o Qdrant

**Arquivo:** `rag_reviewer/vector_store.py`

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams,
    PointStruct, SearchRequest,
)
import os

class VectorStore:
    def __init__(self, collection_name: str = "style_guide_chunks"):
        self.client = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ.get("QDRANT_API_KEY"),
        )
        self.collection_name = collection_name

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        score_threshold: float = 0.55,
    ) -> list[dict]:
        """
        Retorna os top-K chunks mais similares à consulta.
        score_threshold filtra resultados com baixa similaridade.
        """
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return [
            {
                "text": r.payload["text"],
                "source": r.payload["source"],
                "section": r.payload.get("section", ""),
                "score": r.score,
            }
            for r in results
        ]
```

### 9.2 Estratégia de Recuperação

```python
from dataclasses import dataclass
from typing import List

@dataclass
class RetrievedContext:
    file_diff: FileDiff
    chunks: List[dict]        # chunks recuperados do Qdrant
    query_text: str           # texto usado como consulta

class Retriever:
    """Orquestra a recuperação de contexto normativo para cada arquivo do diff."""

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        top_k: int = 5,
    ):
        self.embedder = embedder
        self.store = store
        self.top_k = top_k

    def retrieve_for_diff(self, pr_diff: PullRequestDiff) -> List[RetrievedContext]:
        contexts = []
        for file_diff in pr_diff.files:
            if file_diff.status == "deleted":
                continue  # arquivos deletados não precisam de revisão
            if not file_diff.added_lines:
                continue  # sem linhas adicionadas, nada a revisar

            query_text = build_query_text(file_diff)
            embedding = self.embedder.embed([query_text])[0].tolist()
            chunks = self.store.search(embedding, top_k=self.top_k)

            if chunks:  # só adiciona se houver contexto relevante
                contexts.append(RetrievedContext(
                    file_diff=file_diff,
                    chunks=chunks,
                    query_text=query_text,
                ))
        return contexts
```

**Parâmetros da recuperação:**

| Parâmetro | Valor recomendado | Efeito |
|---|---|---|
| `top_k` | 5 | Número de chunks recuperados por arquivo |
| `score_threshold` | 0.55 | Remove resultados irrelevantes (cosine similarity) |
| Métrica de distância | Cosine | Padrão para embeddings de texto normalizados |

---

## 10. Componente 4 — Módulo de Geração com LLM

**Arquivo:** `rag_reviewer/llm_client.py` e `rag_reviewer/reviewer.py`

### 10.1 Design do Prompt

O prompt é a parte mais crítica do sistema. Um prompt mal estruturado produzirá comentários genéricos, irrelevantes ou alucinados.

**Arquivo:** `rag_reviewer/prompts/system_prompt.txt`

```
Você é um revisor de código especializado que verifica conformidade com os
padrões e guias de estilo da organização. Sua função é analisar as alterações
submetidas em um Pull Request e identificar APENAS violações às normas
organizacionais fornecidas como contexto.

REGRAS ESTRITAS:
1. Comente APENAS violações documentadas nas normas fornecidas.
2. Cite SEMPRE a norma específica violada (fonte e seção).
3. NÃO faça sugestões genéricas de boas práticas não documentadas.
4. NÃO comente linhas não modificadas pelo PR.
5. Se não houver violações, responda com lista vazia.
6. Classifique cada violação como CRÍTICA, ALTA, MÉDIA ou BAIXA.
7. Responda SOMENTE em JSON, sem texto adicional.
```

**Arquivo:** `rag_reviewer/prompts/review_template.txt`

```
## Arquivo em revisão
{filename}

## Linhas adicionadas no PR
```
{added_lines}
```

## Normas organizacionais relevantes recuperadas
{retrieved_chunks}

## Tarefa
Analise as linhas adicionadas e identifique violações às normas acima.

Responda em JSON com o seguinte schema:
{
  "violations": [
    {
      "line_content": "trecho da linha violada",
      "violation_description": "descrição clara da violação",
      "norm_reference": "nome do documento + seção/página",
      "severity": "CRITICAL | HIGH | MEDIUM | LOW",
      "suggestion": "como corrigir"
    }
  ]
}
```

### 10.2 Cliente LLM

```python
import os
import json
from anthropic import Anthropic
from typing import List
from dataclasses import dataclass

@dataclass
class Violation:
    line_content: str
    violation_description: str
    norm_reference: str
    severity: str             # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    suggestion: str

class LLMClient:
    def __init__(self):
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = "claude-sonnet-4-20250514"
        self.system_prompt = open("rag_reviewer/prompts/system_prompt.txt").read()
        self.review_template = open("rag_reviewer/prompts/review_template.txt").read()

    def review(self, context: RetrievedContext) -> List[Violation]:
        chunks_text = "\n\n---\n\n".join(
            f"[Fonte: {c['source']} | Seção: {c['section']}]\n{c['text']}"
            for c in context.chunks
        )

        user_message = self.review_template.format(
            filename=context.file_diff.filename,
            added_lines="\n".join(context.file_diff.added_lines),
            retrieved_chunks=chunks_text,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        raw = response.content[0].text.strip()
        data = json.loads(raw)
        return [Violation(**v) for v in data.get("violations", [])]
```

### 10.3 Orquestrador Principal

**Arquivo:** `rag_reviewer/reviewer.py`

```python
class RAGReviewer:
    """Orquestra todo o fluxo: diff → retrieval → LLM → publicação."""

    def __init__(self):
        self.collector = DiffCollector()
        self.embedder = Embedder()
        self.store = VectorStore()
        self.retriever = Retriever(self.embedder, self.store)
        self.llm = LLMClient()
        self.publisher = GitHubPublisher()

    def run(self):
        pr_diff = self.collector.collect()
        contexts = self.retriever.retrieve_for_diff(pr_diff)

        all_violations = []
        for context in contexts:
            violations = self.llm.review(context)
            all_violations.extend(
                (context.file_diff, v) for v in violations
            )

        self.publisher.publish(all_violations, pr_diff)
        self._handle_pr_status(all_violations)

    def _handle_pr_status(self, violations):
        critical = [v for _, v in violations if v.severity == "CRITICAL"]
        if critical:
            self.publisher.request_changes(
                f"⛔ {len(critical)} violações críticas detectadas. "
                "Corrija antes de fazer o merge."
            )
```

---

## 11. Componente 5 — Publicação de Comentários via GitHub API

**Arquivo:** `rag_reviewer/github_publisher.py`

### 11.1 Estratégia de Comentários

O GitHub suporta dois tipos de comentário em PRs:

| Tipo | API Endpoint | Quando usar |
|---|---|---|
| **Review comment** (inline) | `POST /repos/{owner}/{repo}/pulls/{pull_number}/comments` | Comentário em linha específica do diff |
| **PR comment** (geral) | `POST /repos/{owner}/{repo}/issues/{issue_number}/comments` | Comentário geral no PR (ex: resumo) |

A estratégia adotada:
1. Para cada violação com `line_content` identificável → **comentário inline** na linha mais próxima do diff.
2. Ao final → **comentário geral** com resumo de todas as violações encontradas.
3. Se houver violações críticas → **review com `REQUEST_CHANGES`**.

### 11.2 Implementação

```python
import os
import re
import requests
from typing import List, Tuple

class GitHubPublisher:
    """Publica comentários de revisão no PR via GitHub REST API."""

    def __init__(self):
        self.token = os.environ["GITHUB_TOKEN"]
        self.repo = os.environ["REPO_FULL_NAME"]
        self.pr_number = int(os.environ["PR_NUMBER"])
        self.head_sha = os.environ["PR_HEAD_SHA"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def publish(self, violations: List[Tuple[FileDiff, Violation]], pr_diff: PullRequestDiff):
        if not violations:
            self._post_summary("✅ Nenhuma violação detectada nas normas organizacionais.")
            return

        review_comments = []
        for file_diff, violation in violations:
            line_number = self._find_line_number(file_diff, violation.line_content)
            if line_number:
                review_comments.append({
                    "path": file_diff.filename,
                    "position": line_number,
                    "body": self._format_inline_comment(violation),
                })

        severity_counts = self._count_by_severity(violations)
        self._create_review(review_comments, severity_counts)

    def _format_inline_comment(self, v: Violation) -> str:
        severity_emoji = {
            "CRITICAL": "⛔", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵"
        }
        emoji = severity_emoji.get(v.severity, "ℹ️")
        return (
            f"{emoji} **[{v.severity}]** {v.violation_description}\n\n"
            f"📖 **Norma violada:** `{v.norm_reference}`\n\n"
            f"💡 **Sugestão:** {v.suggestion}"
        )

    def _create_review(self, comments: list, severity_counts: dict):
        """Cria uma review com todos os comentários inline de uma vez."""
        has_critical = severity_counts.get("CRITICAL", 0) > 0
        event = "REQUEST_CHANGES" if has_critical else "COMMENT"

        total = sum(severity_counts.values())
        body = self._build_summary_body(total, severity_counts)

        payload = {
            "commit_id": self.head_sha,
            "body": body,
            "event": event,
            "comments": comments,
        }
        url = f"https://api.github.com/repos/{self.repo}/pulls/{self.pr_number}/reviews"
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()

    def _build_summary_body(self, total: int, counts: dict) -> str:
        lines = [
            f"## 🤖 RAG-Reviewer: {total} violação(ões) detectada(s)\n",
            "| Severidade | Quantidade |",
            "|---|---|",
        ]
        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if counts.get(severity, 0) > 0:
                lines.append(f"| {severity} | {counts[severity]} |")
        lines.append("\n> *Comentários gerados com base nas normas organizacionais indexadas.*")
        return "\n".join(lines)

    def request_changes(self, message: str):
        """Cria uma review de REQUEST_CHANGES sem comentários inline."""
        url = f"https://api.github.com/repos/{self.repo}/pulls/{self.pr_number}/reviews"
        payload = {"body": message, "event": "REQUEST_CHANGES"}
        requests.post(url, headers=self.headers, json=payload).raise_for_status()
```

---

## 12. Banco de Vetores — Qdrant

### 12.1 Configuração da Collection

```python
from qdrant_client.models import Distance, VectorParams, HnswConfigDiff

def create_collection(client, collection_name: str, vector_size: int):
    client.recreate_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=vector_size,
            distance=Distance.COSINE,
        ),
        hnsw_config=HnswConfigDiff(
            m=16,               # conectividade do grafo HNSW
            ef_construct=100,   # qualidade do índice na inserção
        ),
        optimizers_config={
            "indexing_threshold": 20000,  # indexar após 20k vetores
        },
    )
```

### 12.2 Schema do Payload (Metadados por Chunk)

```json
{
  "id": "uuid-v4",
  "vector": [0.023, -0.145, ...],
  "payload": {
    "text": "Texto do chunk normalizado",
    "source": "docs/style_guides/coding_standards.md",
    "section": "3.2 Nomenclatura de Funções",
    "page": 0,
    "chunk_index": 12,
    "char_count": 487,
    "indexed_at": "2025-01-15T10:00:00Z"
  }
}
```

### 12.3 Execução Local com Docker

```bash
# Subir o Qdrant localmente para desenvolvimento
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant:latest

# Verificar se está rodando
curl http://localhost:6333/healthz
```

---

## 13. Modelo de Dados

### 13.1 Entidades Principais

```
┌──────────────────┐       ┌──────────────────┐
│   PullRequestDiff│       │    FileDiff       │
│─────────────────│       │──────────────────│
│ pr_number: int   │1    N│ filename: str     │
│ repo: str        │───────│ patch: str        │
│ files: List      │       │ status: str       │
│ total_additions  │       │ additions: int    │
│ total_deletions  │       │ deletions: int    │
└──────────────────┘       │ added_lines: List │
                            └──────────────────┘
                                     │
                                     │ 1:N
                                     ▼
┌──────────────────┐       ┌──────────────────┐
│ RetrievedContext │       │    Violation      │
│─────────────────│       │──────────────────│
│ file_diff        │       │ line_content: str │
│ chunks: List     │       │ description: str  │
│ query_text: str  │       │ norm_reference    │
└──────────────────┘       │ severity: str     │
                            │ suggestion: str   │
                            └──────────────────┘
```

---

## 14. Segredos e Configurações

### 14.1 Variáveis de Ambiente

**Arquivo:** `.env.example`

```bash
# GitHub (injetado automaticamente pelo GitHub Actions)
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# LLM (escolha um)
OPENAI_API_KEY=sk-xxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx

# Qdrant
QDRANT_URL=https://xxxx.qdrant.io:6333
QDRANT_API_KEY=xxxxxxxxxxxx
QDRANT_COLLECTION=style_guide_chunks

# Configurações do Reviewer
EMBEDDING_MODEL=all-MiniLM-L6-v2
LLM_MODEL=claude-sonnet-4-20250514
TOP_K_CHUNKS=5
SCORE_THRESHOLD=0.55
MAX_DIFF_TOKENS=3000
BLOCK_ON_CRITICAL=true      # se true, emite REQUEST_CHANGES para violações críticas
```

### 14.2 Configuração dos Secrets no GitHub

```
Repositório → Settings → Secrets and variables → Actions → New repository secret

Secrets necessários:
- OPENAI_API_KEY      (ou ANTHROPIC_API_KEY)
- QDRANT_URL
- QDRANT_API_KEY
```

> **Nota:** `GITHUB_TOKEN` é injetado automaticamente pelo GitHub Actions — não é necessário configurar manualmente.

---

## 15. Avaliação e Métricas

### 15.1 Construção do Dataset de Avaliação

**Arquivo:** `evaluation/dataset/prs_with_violations.json`

```json
[
  {
    "pr_id": "PR-001",
    "description": "Função com nome em snake_case em módulo que exige camelCase",
    "diff": "...",
    "expected_violations": [
      {
        "norm_reference": "coding_standards.md#3.2",
        "severity": "HIGH",
        "line_contains": "def process_user_data"
      }
    ]
  }
]
```

O dataset deve conter **no mínimo 30 PRs** com violações catalogadas manualmente, cobrindo:
- Violações de nomenclatura
- Violações de estrutura arquitetural
- Violações de tratamento de exceções
- Violações de documentação/comentários
- PRs sem violações (para medir falsos positivos)

### 15.2 Cálculo das Métricas

**Arquivo:** `evaluation/metrics.py`

```python
from dataclasses import dataclass
from typing import List

@dataclass
class EvaluationResult:
    true_positives: int    # violações reais corretamente identificadas
    false_positives: int   # comentários que não correspondem a violações reais
    false_negatives: int   # violações reais não identificadas

    @property
    def precision(self) -> float:
        if self.true_positives + self.false_positives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_positives)

    @property
    def recall(self) -> float:
        if self.true_positives + self.false_negatives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_negatives)

    @property
    def f1_score(self) -> float:
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * (self.precision * self.recall) / (self.precision + self.recall)
```

### 15.3 Métricas-Alvo

| Métrica | Meta mínima | Meta ideal |
|---|---|---|
| Precision | ≥ 0.70 | ≥ 0.85 |
| Recall | ≥ 0.65 | ≥ 0.80 |
| F1-Score | ≥ 0.67 | ≥ 0.82 |
| Lead time médio de revisão | Redução de 20% | Redução de 40% |
| Tempo de execução da pipeline | ≤ 3 minutos | ≤ 90 segundos |

### 15.4 Questionário de Utilidade Percebida (Escala Likert)

O questionário deve ser aplicado a **desenvolvedores participantes** após interação com pelo menos 3 PRs revisados pelo sistema.

| # | Afirmação | Escala |
|---|---|---|
| Q1 | Os comentários gerados eram relevantes para o código que eu submeti | 1–5 |
| Q2 | A referência à norma citada nos comentários era correta | 1–5 |
| Q3 | Os comentários foram úteis para melhorar meu código | 1–5 |
| Q4 | Prefiro ter o RAG-Reviewer como primeiro revisor do que aguardar revisão humana | 1–5 |
| Q5 | Os comentários continham informações que eu desconhecia | 1–5 |

---

## 16. Cronograma de Desenvolvimento

### 16.1 Sprints

| Sprint | Duração | Entregáveis |
|---|---|---|
| **Sprint 0** — Setup | 1 semana | Repositório configurado, dependências instaladas, Qdrant rodando localmente, `.env.example` documentado |
| **Sprint 1** — Pipeline Offline | 2 semanas | `document_loader.py`, `chunker.py`, `embedder.py`, `index_pipeline.py` funcionais; collection populada no Qdrant |
| **Sprint 2** — Pipeline Online (core) | 2 semanas | `diff_parser.py`, `vector_store.py`, `retriever.py` funcionais; testes unitários com cobertura ≥ 80% |
| **Sprint 3** — Integração LLM | 2 semanas | `llm_client.py`, prompts refinados, `reviewer.py` orquestrando o fluxo completo |
| **Sprint 4** — Publicação e Actions | 1 semana | `github_publisher.py`, `rag_reviewer.yml`, teste end-to-end em repositório de sandbox |
| **Sprint 5** — Avaliação | 2 semanas | Dataset de avaliação construído, métricas calculadas, questionário aplicado |
| **Sprint 6** — Refinamento | 1 semana | Ajuste de prompts baseado nos resultados, correções de bugs, documentação final |

**Total estimado: ~11 semanas**

### 16.2 Marcos (Milestones)

```
Semana 1  ──── M0: Ambiente configurado e Qdrant rodando
Semana 3  ──── M1: Guia de estilo indexado com sucesso
Semana 5  ──── M2: Retrieval funcionando (top-K corretos)
Semana 7  ──── M3: LLM gerando comentários contextualizados
Semana 8  ──── M4: Sistema completo funcionando em sandbox
Semana 10 ──── M5: Avaliação concluída (métricas calculadas)
Semana 11 ──── M6: Versão final documentada e publicada
```

---

## 17. Riscos e Mitigações

| # | Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|---|
| R1 | LLM produz alucinações (inventa normas não documentadas) | Alta | Alto | Prompt com instrução explícita de não inventar; validar referências contra o payload do Qdrant |
| R2 | Score threshold muito baixo → falsos positivos excessivos | Média | Médio | Calibrar threshold empiricamente nos primeiros 10 PRs |
| R3 | Score threshold muito alto → recall baixo (perde violações) | Média | Alto | Monitorar F1 e ajustar; usar hybrid search (BM25 + dense) |
| R4 | Diff muito grande → excede contexto do LLM | Média | Médio | Truncar diff por arquivo; priorizar arquivos com mais adições |
| R5 | Custo de API do LLM fora do orçamento | Baixa | Alto | Usar modelo menor em dev; definir limite de tokens por PR |
| R6 | Guia de estilo desatualizado → revisões incorretas | Baixa | Alto | Automatizar re-indexação via CI ao atualizar docs/ |
| R7 | Latência total > 10 min → timeout do Actions | Baixa | Médio | Cache de embeddings; processar arquivos em paralelo |
| R8 | Desenvolvedores ignoram comentários automáticos | Alta | Médio | Configurar `BLOCK_ON_CRITICAL=true`; escalar severidade corretamente |

---

## 18. Checklist de Entrega

### 18.1 Implementação

- [ ] Pipeline de indexação funcional para PDF, Markdown e DOCX
- [ ] Collection Qdrant criada e populada com o guia de estilo
- [ ] Diff collector funcionando para PRs com múltiplos arquivos
- [ ] Retriever retornando chunks com score ≥ threshold
- [ ] LLM gerando violações em JSON válido
- [ ] Publisher postando comentários inline nas linhas corretas
- [ ] Review `REQUEST_CHANGES` sendo acionada para violações críticas
- [ ] Workflow YAML disparando corretamente em eventos `pull_request`

### 18.2 Qualidade

- [ ] Cobertura de testes unitários ≥ 80%
- [ ] Testes de integração cobrindo o fluxo completo
- [ ] Linter (`ruff`) sem warnings
- [ ] Type checking (`mypy`) sem erros
- [ ] Tempo de execução ≤ 3 minutos em 90% dos PRs testados

### 18.3 Avaliação

- [ ] Dataset com ≥ 30 PRs catalogados
- [ ] F1-Score ≥ 0.67 atingido
- [ ] Redução de lead time mensurada
- [ ] Questionário Likert aplicado a ≥ 5 desenvolvedores
- [ ] Resultados documentados na Seção 5 do artigo

### 18.4 Documentação

- [ ] `README.md` com instruções de instalação e configuração
- [ ] `.env.example` atualizado com todas as variáveis
- [ ] ADRs escritos para escolhas arquiteturais principais
- [ ] Guia de contribuição (`CONTRIBUTING.md`)
- [ ] Guia de atualização do guia de estilo e re-indexação

---

## Apêndice A — ADR-001: Escolha do Banco de Vetores

**Decisão:** Qdrant

**Contexto:** O sistema precisa de um banco de vetores que suporte busca por similaridade semântica com baixa latência, seja auto-hospedável (privacidade dos dados normativos) e tenha SDK Python maduro.

**Opções consideradas:**

| Opção | Prós | Contras |
|---|---|---|
| **Qdrant** | Gratuito, self-hosted, SDK Python excelente, filtros de payload | Requer infraestrutura própria ou Qdrant Cloud |
| Pinecone | Gerenciado, sem ops | Custo em produção, dados fora da org |
| ChromaDB | Simples, embedded | Não recomendado para produção com escala |
| Weaviate | Recursos avançados | Maior complexidade de setup |

**Decisão final:** Qdrant Cloud (free tier para desenvolvimento; self-hosted para produção corporativa).

---

## Apêndice B — ADR-002: Escolha do Modelo de Embedding

**Decisão:** `all-MiniLM-L6-v2` em desenvolvimento; `text-embedding-3-small` em produção.

**Justificativa:** O `all-MiniLM-L6-v2` é gratuito, roda localmente e tem boa performance em tarefas de similaridade semântica de código. Para produção, `text-embedding-3-small` da OpenAI oferece melhor qualidade com custo razoável (~$0.02/1M tokens).

---

## Apêndice C — ADR-003: Escolha do LLM

**Decisão:** Claude Sonnet (`claude-sonnet-4-20250514`) como padrão.

**Justificativa:** O Claude Sonnet oferece excelente desempenho em tarefas de análise de código, resposta estruturada em JSON confiável e contexto de 200K tokens (suficiente para diffs grandes). Alternativa: `gpt-4o` da OpenAI com desempenho comparável.

---

*Documento gerado como planejamento técnico para implementação do RAG-Reviewer.*  
*Última atualização: Maio de 2026*
