"""
vector_store.py — Interface com o banco de vetores Qdrant.

Gerencia criação de coleções, inserção (upsert) e busca por similaridade.
"""

from __future__ import annotations

import uuid
from typing import List

from rich.console import Console

from rag_reviewer.config import get_settings

console = Console()


class VectorStore:
    """
    Interface com o Qdrant para armazenamento e consulta de embeddings.

    Suporta tanto Qdrant Cloud (via URL + API key) quanto instância
    local Docker (apenas URL).
    """

    def __init__(self, collection_name: str | None = None) -> None:
        settings = get_settings()
        self._collection = collection_name or settings.qdrant_collection
        self._client = None  # lazy loading

    # ── Propriedades ──────────────────────────────────────────────────────

    @property
    def collection_name(self) -> str:
        return self._collection

    # ── Interface pública ─────────────────────────────────────────────────

    def recreate_collection(self, vector_size: int) -> None:
        """
        Recria a coleção do zero.

        Apaga todos os dados existentes e cria uma nova coleção com a
        configuração HNSW otimizada para busca por cosine similarity.

        Args:
            vector_size: Dimensão dos vetores (deve bater com o modelo de embedding).
        """
        from qdrant_client.models import (  # type: ignore
            Distance,
            HnswConfigDiff,
            VectorParams,
        )

        client = self._get_client()

        # Remove coleção anterior se existir
        existing = [c.name for c in client.get_collections().collections]
        if self._collection in existing:
            client.delete_collection(self._collection)
            console.log(f"[yellow]VectorStore:[/yellow] coleção '{self._collection}' removida.")

        client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
            hnsw_config=HnswConfigDiff(
                m=16,
                ef_construct=100,
            ),
        )
        console.log(
            f"[green]✅ Coleção '{self._collection}' criada com vetores de dim={vector_size}.[/green]"
        )

    def upsert(self, chunks: list, embeddings) -> None:
        """
        Insere ou atualiza chunks no Qdrant.

        Args:
            chunks: Lista de objetos Chunk (de indexer/chunker.py).
            embeddings: Array numpy (N, D) com os vetores correspondentes.
        """
        import numpy as np
        from qdrant_client.models import PointStruct  # type: ignore

        client = self._get_client()

        points = []
        for chunk, vector in zip(chunks, embeddings):
            payload = {
                "text": chunk.text,
                "source": chunk.source,
                "section": chunk.section,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "char_count": len(chunk.text),
                "indexed_at": chunk.indexed_at,
            }
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector.tolist(),
                    payload=payload,
                )
            )

        # Insere em lotes de 100
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            client.upsert(collection_name=self._collection, points=batch)
            console.log(
                f"[cyan]VectorStore:[/cyan] inseridos {min(i + batch_size, len(points))}/{len(points)} pontos..."
            )

        console.log(f"[green]✅ {len(points)} chunks inseridos no Qdrant.[/green]")

    def search(
        self,
        query_vector: list,
        top_k: int = 5,
        score_threshold: float = 0.55,
    ) -> List[dict]:
        """
        Busca os top-K chunks mais similares ao vetor de consulta.

        Args:
            query_vector: Vetor de consulta (lista de floats).
            top_k: Número máximo de resultados.
            score_threshold: Score mínimo de similaridade (0–1).

        Returns:
            Lista de dicts com: text, source, section, score.
        """
        client = self._get_client()

        results = client.search(
            collection_name=self._collection,
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
                "page": r.payload.get("page", 0),
                "score": r.score,
            }
            for r in results
        ]

    def collection_info(self) -> dict:
        """Retorna informações da coleção (contagem de pontos, status, etc.)."""
        client = self._get_client()
        info = client.get_collection(self._collection)
        return {
            "name": self._collection,
            "vectors_count": info.vectors_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "status": info.status,
        }

    # ── Internos ──────────────────────────────────────────────────────────

    def _get_client(self):
        """Retorna cliente Qdrant com lazy initialization."""
        if self._client is None:
            try:
                from qdrant_client import QdrantClient  # type: ignore

                settings = get_settings()
                self._client = QdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key or None,
                    timeout=30,
                )
                console.log(
                    f"[cyan]VectorStore:[/cyan] conectado ao Qdrant em [bold]{settings.qdrant_url}[/bold]"
                )
            except ImportError as exc:
                raise ImportError(
                    "qdrant-client não está instalado. Execute: pip install qdrant-client"
                ) from exc
        return self._client
