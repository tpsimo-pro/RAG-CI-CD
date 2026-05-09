# RAG-Reviewer — Makefile
# Atalhos para tarefas de desenvolvimento

.PHONY: help install install-dev index test test-cov lint lint-fix format typecheck docker-qdrant evaluate clean

# ── Intérprete Python — sempre usa o .venv do projeto ────────────────────────
# Detecta Windows (Scripts/) vs Unix (bin/)
ifeq ($(OS),Windows_NT)
    PYTHON := .venv\Scripts\python.exe
    PIP    := .venv\Scripts\pip.exe
else
    PYTHON := .venv/bin/python
    PIP    := .venv/bin/pip
endif

# ── Ajuda ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "RAG-Reviewer — Comandos disponíveis:"
	@echo ""
	@echo "  make install        Instala dependências de produção"
	@echo "  make install-dev    Instala dependências de desenvolvimento"
	@echo "  make index          Executa o pipeline de indexação (docs/style_guides/)"
	@echo "  make index-recreate Executa a indexação e recria a coleção Qdrant"
	@echo "  make test           Executa os testes unitários e de integração"
	@echo "  make test-cov       Executa testes com relatório de cobertura"
	@echo "  make lint           Verifica qualidade do código com ruff"
	@echo "  make lint-fix       Corrige automaticamente problemas de linting"
	@echo "  make format         Formata o código com black"
	@echo "  make typecheck      Verifica tipos com mypy"
	@echo "  make docker-qdrant  Sobe o Qdrant localmente via Docker"
	@echo "  make evaluate       Avalia o sistema contra o dataset sintético (métricas TCC)"
	@echo "  make clean          Remove arquivos temporários e cache"
	@echo ""

# ── Instalação ────────────────────────────────────────────────────────────────

install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -r requirements-dev.txt

# ── Indexação ─────────────────────────────────────────────────────────────────

index:
	$(PYTHON) -m indexer.index_pipeline --docs-dir docs/style_guides

index-recreate:
	$(PYTHON) -m indexer.index_pipeline --docs-dir docs/style_guides --recreate

# ── Testes ────────────────────────────────────────────────────────────────────

test:
	$(PYTHON) -m pytest tests/ -v

test-unit:
	$(PYTHON) -m pytest tests/unit/ -v

test-integration:
	$(PYTHON) -m pytest tests/integration/ -v

test-cov:
	$(PYTHON) -m pytest tests/ --cov=rag_reviewer --cov=indexer --cov-report=term-missing --cov-report=html -v

# ── Qualidade de código ───────────────────────────────────────────────────────

lint:
	$(PYTHON) -m ruff check rag_reviewer/ indexer/ tests/

lint-fix:
	$(PYTHON) -m ruff check --fix rag_reviewer/ indexer/ tests/

format:
	$(PYTHON) -m black rag_reviewer/ indexer/ tests/

typecheck:
	$(PYTHON) -m mypy rag_reviewer/ indexer/

# ── Infraestrutura local ──────────────────────────────────────────────────────

docker-qdrant:
	docker run -d \
		--name qdrant \
		-p 6333:6333 \
		-p 6334:6334 \
		-v $(shell pwd)/qdrant_storage:/qdrant/storage \
		qdrant/qdrant:latest
	@echo "Qdrant disponível em http://localhost:6333"
	@echo "Dashboard: http://localhost:6333/dashboard"

# ── Avaliação ────────────────────────────────────────────────────────────────

evaluate:
	set PYTHONIOENCODING=utf-8 && $(PYTHON) -m evaluation.run_evaluation

# ── Limpeza ───────────────────────────────────────────────────────────────────

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov"     -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	@echo "Limpeza concluída."
