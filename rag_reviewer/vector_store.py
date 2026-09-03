"""
vector_store.py — Interface com o banco de vetores Qdrant.

Gerencia criação de coleções, inserção (upsert) e busca por similaridade.
"""

from __future__ import annotations

import uuid

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

    def recreate_collection(self, vector_size: int, embedding_model: str) -> None:
        """
        Recria a coleção do zero.

        Apaga todos os dados existentes e cria uma nova coleção com a
        configuração HNSW otimizada para busca por cosine similarity.

        Args:
            vector_size: Dimensão dos vetores (deve bater com o modelo de embedding).
            embedding_model: Nome do modelo usado para gerar os vetores. Apenas
                registrado no log; quem grava o payload é `upsert`.
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
            console.log(
                f"[yellow]VectorStore:[/yellow] coleção '{self._collection}' removida."
            )

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
            f"[green]✅ Coleção '{self._collection}' criada "
            f"(dim={vector_size}, modelo={embedding_model}).[/green]"
        )

    def upsert(self, chunks: list, embeddings, embedding_model: str) -> None:
        """
        Insere ou atualiza chunks no Qdrant.

        Args:
            chunks: Lista de objetos Chunk (de indexer/chunker.py).
            embeddings: Array numpy (N, D) com os vetores correspondentes.
            embedding_model: Nome do modelo que gerou `embeddings`. Gravado no
                payload de cada ponto — é o que `assert_model_matches` lê para
                impedir buscas com um modelo diferente do indexado.
        """
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
                "embedding_model": embedding_model,
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
    ) -> list[dict]:
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

    def assert_model_matches(self, embedding_model: str) -> None:
        """
        Falha alto se a coleção foi indexada com outro modelo de embedding.

        Os modelos multilíngues candidatos também têm 384 dimensões, então o
        Qdrant ACEITARIA a busca sem reclamar: vetores de consulta do modelo
        novo contra vetores de chunk do modelo antigo. O resultado seria lixo
        silencioso, indistinguível de retrieval ruim (spec §8.1).

        Args:
            embedding_model: Nome do modelo que o chamador pretende usar para
                gerar o vetor de consulta.

        Raises:
            RuntimeError: Se a coleção estiver vazia ou indexada com um
                modelo diferente de `embedding_model`.
        """
        client = self._get_client()
        pontos, _ = client.scroll(
            collection_name=self._collection, limit=1, with_payload=True
        )

        if not pontos:
            raise RuntimeError(
                f"Coleção '{self._collection}' está vazia. "
                f"Execute: make index-recreate"
            )

        indexado = (pontos[0].payload or {}).get("embedding_model")
        if indexado != embedding_model:
            raise RuntimeError(
                f"Divergência de modelo de embedding.\n"
                f"  Indexado na coleção : {indexado!r}\n"
                f"  Configurado agora   : {embedding_model!r}\n"
                f"Buscar com modelos diferentes produz lixo silencioso.\n"
                f"Execute: make index-recreate"
            )

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
