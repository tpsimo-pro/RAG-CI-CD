"""
embedder.py — Geração de embeddings de texto usando sentence-transformers.

Suporta modelos locais (all-MiniLM-L6-v2) e OpenAI (text-embedding-3-small/large).
Os embeddings são sempre L2-normalizados para compatibilidade com cosine similarity.
"""

from __future__ import annotations

from typing import List

import numpy as np
from rich.console import Console

from rag_reviewer.config import get_settings

# Importa sentence-transformers no nível do módulo para permitir mocking em testes.
# Se não estiver instalado, SentenceTransformer ficará como None e o erro
# será levantado de forma clara no momento do uso.
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except ImportError:
    SentenceTransformer = None  # type: ignore

console = Console()


class Embedder:
    """
    Gera embeddings de texto utilizando modelos sentence-transformers locais.

    O modelo padrão (all-MiniLM-L6-v2) roda offline, sem custo de API,
    e produz vetores de 384 dimensões adequados para similaridade semântica
    em inglês e português.
    """

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.embedding_model
        self._model = None  # carregado sob demanda (lazy loading)

    # ── Propriedades ──────────────────────────────────────────────────────

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def vector_size(self) -> int:
        """Dimensão dos vetores produzidos pelo modelo carregado."""
        self._ensure_model_loaded()
        return self._model.get_sentence_embedding_dimension()  # type: ignore[union-attr]

    # ── Interface pública ─────────────────────────────────────────────────

    def embed(self, texts: List[str]) -> np.ndarray:
        """
        Gera embeddings para uma lista de textos.

        Args:
            texts: Lista de strings a serem encodadas.

        Returns:
            Matriz numpy de shape (N, D) com embeddings L2-normalizados,
            onde N = len(texts) e D = dimensão do modelo.
        """
        if not texts:
            return np.array([])

        self._ensure_model_loaded()

        console.log(
            f"[cyan]Embedder:[/cyan] gerando embeddings para {len(texts)} texto(s) "
            f"com o modelo '[bold]{self._model_name}[/bold]'..."
        )

        vectors = self._model.encode(  # type: ignore[union-attr]
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=len(texts) > 10,
        )

        return vectors.astype(np.float32)

    def embed_single(self, text: str) -> np.ndarray:
        """Conveniência: embeda um único texto e retorna vetor 1-D."""
        return self.embed([text])[0]

    # ── Internos ──────────────────────────────────────────────────────────

    def _ensure_model_loaded(self) -> None:
        """Carrega o modelo sentence-transformers na primeira chamada."""
        if self._model is None:
            if SentenceTransformer is None:
                raise ImportError(
                    "sentence-transformers não está instalado. "
                    "Execute: pip install sentence-transformers"
                )
            console.log(
                f"[cyan]Embedder:[/cyan] carregando modelo '[bold]{self._model_name}[/bold]'..."
            )
            self._model = SentenceTransformer(self._model_name)
            console.log(
                f"[green]✅ Modelo carregado. Dimensão: {self.vector_size}[/green]"
            )
