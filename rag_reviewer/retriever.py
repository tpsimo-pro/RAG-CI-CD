"""
retriever.py — Módulo RAG: Recuperação Semântica (Componente 3, Fase 2).

Responsabilidades:
  1. Receber um PullRequestDiff (saída do diff_parser).
  2. Para cada arquivo relevante, construir o texto de consulta via build_query_text.
  3. Gerar o embedding da consulta usando o Embedder.
  4. Buscar no Qdrant os top-K chunks do guia de estilo mais similares.
  5. Retornar uma lista de RetrievedContext prontos para o LLM (Componente 4).

Uso típico:
    retriever = Retriever(embedder=Embedder(), store=VectorStore())
    contexts  = retriever.retrieve_for_diff(pr_diff)
    for ctx in contexts:
        # ctx.file_diff   → arquivo analisado
        # ctx.chunks      → normas recuperadas do Qdrant
        # ctx.query_text  → texto que gerou os embeddings
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console

from rag_reviewer.config import get_settings
from rag_reviewer.diff_parser import FileDiff, PullRequestDiff, build_query_text
from rag_reviewer.embedder import Embedder
from rag_reviewer.vector_store import VectorStore

console = Console()


# ── Modelo de dados ────────────────────────────────────────────────────────────


@dataclass
class RetrievedContext:
    """
    Agrupa o diff de um arquivo com as normas recuperadas do Qdrant.

    Cada instância representa um único arquivo do PR e os trechos do guia
    de estilo que são semanticamente relevantes para as linhas adicionadas.
    """

    file_diff: FileDiff
    """O diff do arquivo que originou a consulta."""

    chunks: list[dict]
    """
    Chunks recuperados do Qdrant, cada um com as chaves:
      - text    : texto do trecho normativo
      - source  : arquivo de origem do guia de estilo
      - section : seção/título dentro do documento
      - page    : número da página (para PDFs)
      - score   : score de similaridade cosine (0–1)
    """

    query_text: str
    """Texto que foi embedado e enviado ao Qdrant como consulta."""


# ── Retriever ──────────────────────────────────────────────────────────────────


class Retriever:
    """
    Orquestra a recuperação de contexto normativo para cada arquivo do diff.

    Para cada arquivo do PullRequestDiff que contém linhas adicionadas:
      1. Constrói um texto de consulta (arquivo + linhas adicionadas).
      2. Gera o embedding desse texto via Embedder.
      3. Consulta o VectorStore e retorna os top-K chunks relevantes.
      4. Empacota o resultado em um RetrievedContext.

    Arquivos sem linhas adicionadas ou com score abaixo do threshold são
    silenciosamente ignorados.
    """

    def __init__(
        self,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
        top_k: int | None = None,
        score_threshold: float | None = None,
    ) -> None:
        """
        Inicializa o Retriever.

        Todos os parâmetros têm defaults vindos de ``get_settings()``, o que
        permite instanciar com apenas ``Retriever()`` em produção e injetar
        dependências nos testes.

        Args:
            embedder: Instância do Embedder. Usa default se None.
            store: Instância do VectorStore. Usa default se None.
            top_k: Número de chunks recuperados por arquivo.
            score_threshold: Score mínimo de similaridade (0–1).
        """
        settings = get_settings()
        self._embedder = embedder if embedder is not None else Embedder()
        self._store = store if store is not None else VectorStore()
        self._top_k = top_k if top_k is not None else settings.top_k_chunks
        self._score_threshold = (
            score_threshold if score_threshold is not None else settings.score_threshold
        )
        # Falha alto se a coleção foi indexada com outro modelo de embedding
        # (spec §8.1) — buscar com modelos divergentes produz lixo silencioso.
        self._store.assert_model_matches(self._embedder.model_name)

    # ── Propriedades ──────────────────────────────────────────────────────

    @property
    def top_k(self) -> int:
        return self._top_k

    @property
    def score_threshold(self) -> float:
        return self._score_threshold

    # ── Interface pública ─────────────────────────────────────────────────

    def retrieve_for_diff(self, pr_diff: PullRequestDiff) -> list[RetrievedContext]:
        """
        Recupera contexto normativo para cada arquivo relevante do PR.

        Um arquivo é considerado **irrelevante** (e ignorado) quando:
          - Não possui linhas adicionadas (ex.: só remoções ou renomeação sem conteúdo).
          - Nenhum chunk do Qdrant atinge o score_threshold (sem contexto aplicável).

        Args:
            pr_diff: Diff completo do PR, gerado pelo DiffCollector.

        Returns:
            Lista de RetrievedContext, um por arquivo com contexto relevante.
            Pode ser vazia se o PR não alterar código revisável.
        """
        candidates = self._filter_candidates(pr_diff.files)

        console.log(
            f"[cyan]Retriever:[/cyan] {len(candidates)}/{len(pr_diff.files)} "
            f"arquivo(s) com linhas adicionadas para revisar."
        )

        contexts: list[RetrievedContext] = []
        for file_diff in candidates:
            ctx = self._retrieve_for_file(file_diff)
            if ctx is not None:
                contexts.append(ctx)

        console.log(
            f"[green]✅ Retriever:[/green] contexto recuperado para "
            f"{len(contexts)} arquivo(s)."
        )
        return contexts

    def retrieve_for_file(self, file_diff: FileDiff) -> RetrievedContext | None:
        """
        Recupera contexto normativo para um único FileDiff.

        Conveniente para testar um arquivo específico sem precisar de um PR completo.

        Args:
            file_diff: Diff de um único arquivo.

        Returns:
            RetrievedContext se houver chunks relevantes, None caso contrário.
        """
        return self._retrieve_for_file(file_diff)

    # ── Internos ──────────────────────────────────────────────────────────

    def _filter_candidates(self, files: list[FileDiff]) -> list[FileDiff]:
        """
        Filtra apenas arquivos com linhas adicionadas que merecem revisão.

        Arquivos com status 'deleted' já foram filtrados pelo DiffCollector.
        Aqui filtramos os que não têm nenhuma linha adicionada (ex.: só
        remoções de código).
        """
        return [f for f in files if f.added_lines]

    def _retrieve_for_file(self, file_diff: FileDiff) -> RetrievedContext | None:
        """
        Executa o ciclo embed → search para um único arquivo.

        Returns:
            RetrievedContext se houver chunks acima do threshold, None caso contrário.
        """
        query_text = build_query_text(file_diff)

        console.log(
            f"[dim]Retriever:[/dim] buscando normas para "
            f"[bold]{file_diff.filename}[/bold] "
            f"({len(file_diff.added_lines)} linha(s) adicionada(s))..."
        )

        # Gera embedding — retorna array shape (1, D); pegamos a linha 0
        embedding_matrix = self._embedder.embed([query_text])
        query_vector: list = embedding_matrix[0].tolist()

        chunks = self._store.search(
            query_vector=query_vector,
            top_k=self._top_k,
            score_threshold=self._score_threshold,
        )

        if not chunks:
            console.log(
                f"[dim]Retriever:[/dim] nenhum chunk relevante para "
                f"[bold]{file_diff.filename}[/bold] "
                f"(threshold={self._score_threshold})."
            )
            return None

        console.log(
            f"[dim]Retriever:[/dim] {len(chunks)} chunk(s) recuperado(s) para "
            f"[bold]{file_diff.filename}[/bold] "
            f"(top score: {chunks[0]['score']:.3f})."
        )

        return RetrievedContext(
            file_diff=file_diff,
            chunks=chunks,
            query_text=query_text,
        )
