# RAG-Reviewer

Ferramenta de governança de código automatizada que, integrada ao GitHub Actions, é acionada a cada abertura ou atualização de Pull Request. Recupera semanticamente as diretrizes organizacionais relevantes às alterações submetidas e publica comentários de revisão rastreáveis à norma específica violada.

## Documentação

- [Planejamento Detalhado de Implementação](RAG-Reviewer_Planejamento.md)

## Pré-requisitos

- Python 3.11+
- Docker 24+ (para Qdrant local)

## Instalação

```bash
# Clonar o repositório
git clone <url>
cd rag-ci-cd

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Edite o .env com suas credenciais reais
```

## Uso

### 1. Subir Qdrant localmente

```bash
make docker-qdrant
```

### 2. Indexar o guia de estilo

```bash
# Indexa docs/style_guides/ e popula o Qdrant
make index-recreate
```

### 3. Executar testes

```bash
make test        # testes unitários
make test-cov    # testes com cobertura
```

### 4. Qualidade de código

```bash
make lint        # ruff
make format      # black
make typecheck   # mypy
```

## Estrutura do Projeto

```
rag-reviewer/
├── .github/workflows/        # GitHub Actions (Fase 2)
├── rag_reviewer/             # Pacote Python principal
│   ├── config.py             # Configurações centralizadas
│   ├── embedder.py           # Geração de embeddings
│   └── vector_store.py       # Interface com Qdrant
├── indexer/                  # Pipeline offline de indexação
│   ├── document_loader.py    # Leitura de PDF, MD, DOCX
│   ├── chunker.py            # Divisão em chunks
│   └── index_pipeline.py     # Orquestrador
├── docs/style_guides/        # Guias de estilo da organização
├── tests/unit/               # Testes unitários
├── .env.example              # Template de variáveis de ambiente
├── Makefile                  # Atalhos de desenvolvimento
├── requirements.txt
└── requirements-dev.txt
```

## Status de Implementação

| Fase | Status |
|---|---|
| Fase 1 — Pipeline de Indexação | ✅ Concluída |
| Fase 2 — Pipeline de Revisão de PR | 🔜 Pendente |
| Integração GitHub Actions | 🔜 Pendente |
| Avaliação e Métricas | 🔜 Pendente |
