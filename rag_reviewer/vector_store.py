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
            SparseVectorParams,
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

        # O vetor denso passa a ser NOMEADO ("dense"): a Query API precisa
        # endereçar as duas modalidades (densa e esparsa "bm25") por nome
        # em `search_hybrid` (spec — busca híbrida, L4).
        client.create_collection(
            collection_name=self._collection,
            vectors_config={
                "dense": VectorParams(size=vector_size, distance=Distance.COSINE)
            },
            sparse_vectors_config={"bm25": SparseVectorParams()},
            hnsw_config=HnswConfigDiff(
                m=16,
                ef_construct=100,
            ),
        )
        console.log(
            f"[green]✅ Coleção '{self._collection}' criada "
            f"(dim={vector_size}, modelo={embedding_model}).[/green]"
        )

    def upsert(
        self,
        chunks: list,
        embeddings,
        sparse: list[tuple[list[int], list[float]]],
        embedding_model: str,
    ) -> None:
        """
        Insere ou atualiza chunks no Qdrant, com vetor denso E esparso.

        Args:
            chunks: Lista de objetos Chunk (de indexer/chunker.py).
            embeddings: Array numpy (N, D) com os vetores densos correspondentes.
            sparse: Lista paralela de (índices, valores) esparsos BM25, uma
                por chunk — ver `SparseEncoder.encode_batch`.
            embedding_model: Nome do modelo que gerou `embeddings`. Gravado no
                payload de cada ponto — é o que `assert_model_matches` lê para
                impedir buscas com um modelo diferente do indexado.
        """
        from qdrant_client.models import PointStruct, SparseVector  # type: ignore

        client = self._get_client()

        points = []
        for chunk, vector, (idx, vals) in zip(chunks, embeddings, sparse):
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
                    vector={
                        "dense": vector.tolist(),
                        "bm25": SparseVector(indices=idx, values=vals),
                    },
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
        Busca apenas densa. Mantida para as configurações L0–L3.

        Args:
            query_vector: Vetor de consulta denso (lista de floats).
            top_k: Número máximo de resultados.
            score_threshold: Score mínimo de similaridade cosine (0–1).

        Returns:
            Lista de dicts com: text, source, section, score.
        """
        client = self._get_client()

        results = client.query_points(
            collection_name=self._collection,
            query=query_vector,
            using="dense",
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        ).points

        return [self._to_dict(r) for r in results]

    def search_hybrid(
        self,
        dense: list,
        sparse: tuple[list[int], list[float]],
        top_k: int = 5,
        prefetch_limit: int = 20,
    ) -> list[dict]:
        """
        Busca híbrida densa + esparsa com fusão Reciprocal Rank Fusion (L4).

        `== True` e `!= None` são padrões lexicais que um modelo semântico
        não deveria ter que casar sozinho (spec §1.3) — o vetor esparso BM25
        cobre esse lado, o denso cobre a paráfrase/tradução.

        Após a fusão o score é POSTO (RRF), não cosseno — por isso o
        `score_threshold` absoluto não se aplica aqui e foi removido do
        caminho híbrido (spec §4.4). O corte passa a ser `top_k`, calibrado
        contra o gabarito.

        Args:
            dense: Vetor de consulta denso.
            sparse: (índices, valores) do vetor de consulta esparso BM25.
            top_k: Número de resultados após a fusão.
            prefetch_limit: Quantos candidatos cada modalidade contribui
                antes da fusão.

        Returns:
            Lista de dicts com: text, source, section, score (RRF).
        """
        from qdrant_client import models  # type: ignore

        client = self._get_client()
        indices, values = sparse
        results = client.query_points(
            collection_name=self._collection,
            prefetch=[
                models.Prefetch(query=dense, using="dense", limit=prefetch_limit),
                models.Prefetch(
                    query=models.SparseVector(indices=indices, values=values),
                    using="bm25",
                    limit=prefetch_limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        ).points

        return [self._to_dict(r) for r in results]

    def search_batch(
        self,
        query_vectors: list[list],
        top_k: int = 5,
        score_threshold: float = 0.55,
    ) -> list[list[dict]]:
        """
        Versão em lote de `search`: uma única ida ao Qdrant para N consultas.

        Args:
            query_vectors: Vetores de consulta densos, um por linha.
            top_k: Número máximo de resultados por consulta.
            score_threshold: Score mínimo de similaridade cosine (0–1).

        Returns:
            Uma lista de resultados por consulta, NA ORDEM de `query_vectors`.
        """
        if not query_vectors:
            return []

        from qdrant_client import models  # type: ignore

        client = self._get_client()
        respostas = client.query_batch_points(
            collection_name=self._collection,
            requests=[
                models.QueryRequest(
                    query=v,
                    using="dense",
                    limit=top_k,
                    score_threshold=score_threshold,
                    with_payload=True,
                )
                for v in query_vectors
            ],
        )

        return [[self._to_dict(p) for p in r.points] for r in respostas]

    def search_hybrid_batch(
        self,
        dense: list[list],
        sparse: list[tuple[list[int], list[float]]],
        top_k: int = 5,
        prefetch_limit: int = 20,
    ) -> list[list[dict]]:
        """
        Versão em lote de `search_hybrid`: uma única ida ao Qdrant para N
        consultas, cada uma com sua própria fusão RRF.

        Consultar linha a linha custava uma requisição de rede por linha
        adicionada do PR. O lote não muda o resultado de nenhuma consulta —
        a fusão continua por consulta, não entre elas.

        Args:
            dense: Vetores densos, um por linha.
            sparse: (índices, valores) esparsos, um por linha, na mesma ordem.
            top_k: Número de resultados por consulta, após a fusão.
            prefetch_limit: Candidatos que cada modalidade contribui antes
                da fusão.

        Returns:
            Uma lista de resultados por consulta, NA ORDEM de `dense`.
        """
        if len(dense) != len(sparse):
            raise ValueError(
                f"dense e sparse precisam ter o mesmo tamanho: "
                f"{len(dense)} != {len(sparse)}"
            )
        if not dense:
            return []

        from qdrant_client import models  # type: ignore

        client = self._get_client()
        respostas = client.query_batch_points(
            collection_name=self._collection,
            requests=[
                models.QueryRequest(
                    prefetch=[
                        models.Prefetch(query=d, using="dense", limit=prefetch_limit),
                        models.Prefetch(
                            query=models.SparseVector(indices=idx, values=vals),
                            using="bm25",
                            limit=prefetch_limit,
                        ),
                    ],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    limit=top_k,
                    with_payload=True,
                )
                for d, (idx, vals) in zip(dense, sparse)
            ],
        )

        return [[self._to_dict(p) for p in r.points] for r in respostas]

    @staticmethod
    def _to_dict(point) -> dict:
        return {
            "text": point.payload["text"],
            "source": point.payload["source"],
            "section": point.payload.get("section", ""),
            "page": point.payload.get("page", 0),
            "score": point.score,
        }

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
