"""
retriever.py — Módulo RAG: Recuperação Semântica (Componente 3, Fase 2).

Responsabilidades:
  1. Receber o FileDiff de um arquivo.
  2. Para cada arquivo relevante, consultar o Qdrant UMA VEZ POR LINHA
     adicionada (a unidade de recuperação é a linha, igual à unidade de
     avaliação de D-001 — consultar por arquivo inteiro produz uma média
     semântica que não representa nenhuma linha).
  3. Unir e deduplicar os chunks recuperados de todas as linhas do arquivo,
     cortando em `max_chunks` (o N da spec §4.3).
  4. Retornar uma lista de RetrievedContext prontos para o LLM (Componente 4).

Uso típico:
    retriever = Retriever(embedder=Embedder(), store=VectorStore())
    ctx = retriever.retrieve_for_file(file_diff)
    if ctx:
        # ctx.file_diff   → arquivo analisado
        # ctx.chunks      → normas recuperadas do Qdrant
        # ctx.query_text  → texto que gerou os embeddings
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console

from rag_reviewer.config import get_settings
from rag_reviewer.diff_parser import FileDiff
from rag_reviewer.embedder import Embedder
from rag_reviewer.sparse_encoder import SparseEncoder
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
      - score   : score de similaridade cosine (0–1)
    """

    query_text: str
    """Texto que foi embedado e enviado ao Qdrant como consulta."""


# ── Retriever ──────────────────────────────────────────────────────────────────


class Retriever:
    """
    Orquestra a recuperação de contexto normativo para cada arquivo do diff.

    Para cada arquivo (FileDiff) com linhas adicionadas:
      1. Para cada linha, gera o embedding via Embedder e consulta o
         VectorStore pelos top-K chunks daquela linha.
      2. Une os chunks de todas as linhas, deduplicados por (source, section)
         e cortados em `max_chunks`.
      3. Empacota o resultado em um RetrievedContext.

    Arquivos sem linhas adicionadas ou com score abaixo do threshold são
    silenciosamente ignorados.
    """

    def __init__(
        self,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
        top_k: int | None = None,
        score_threshold: float | None = None,
        max_chunks: int | None = None,
        sparse_encoder: SparseEncoder | None = None,
        hybrid: bool = True,
    ) -> None:
        """
        Inicializa o Retriever.

        Todos os parâmetros têm defaults vindos de ``get_settings()``, o que
        permite instanciar com apenas ``Retriever()`` em produção e injetar
        dependências nos testes.

        Args:
            embedder: Instância do Embedder. Usa default se None.
            store: Instância do VectorStore. Usa default se None.
            top_k: Número de chunks recuperados por LINHA de consulta.
            score_threshold: Score mínimo de similaridade (0–1). Ignorado
                quando `hybrid=True` — a fusão RRF produz um score de posto,
                não cosseno (spec §4.4).
            max_chunks: Teto de chunks entregues ao LLM por arquivo, após
                deduplicar a união das buscas por linha (o N da spec §4.3).
                Contexto excedente comprovadamente induz alucinação. Default 8.
            sparse_encoder: Instância do SparseEncoder. Usa default se None.
            hybrid: Se True (default), cada busca por linha usa
                `store.search_hybrid_batch` (denso + esparso BM25 com fusão RRF,
                L4). Se False, usa `store.search_batch` (só denso, L0–L3).
        """
        settings = get_settings()
        self._embedder = embedder if embedder is not None else Embedder()
        self._store = store if store is not None else VectorStore()
        self._top_k = top_k if top_k is not None else settings.top_k_chunks
        self._score_threshold = (
            score_threshold if score_threshold is not None else settings.score_threshold
        )
        self._max_chunks = max_chunks if max_chunks is not None else 8
        self._hybrid = hybrid
        self._sparse_encoder = (
            sparse_encoder if sparse_encoder is not None else SparseEncoder()
        )
        # A guarda (spec §8.1) só dispara ao primeiro uso real de busca — ver
        # `_ensure_model_guard`. Checá-la aqui, no __init__, forçaria uma
        # conexão de rede com o Qdrant mesmo quando o PR não tem nenhum
        # arquivo revisável (ex.: diff vazio), o que nunca chega a buscar.
        self._guarda_verificada = False

    # ── Propriedades ──────────────────────────────────────────────────────

    @property
    def top_k(self) -> int:
        return self._top_k

    @property
    def score_threshold(self) -> float:
        return self._score_threshold

    # ── Interface pública ─────────────────────────────────────────────────

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

    def _ensure_model_guard(self) -> None:
        """
        Falha alto, uma única vez, se a coleção foi indexada com outro
        modelo de embedding (spec §8.1) — buscar com modelos divergentes
        produz lixo silencioso.

        Verificada sob demanda (na primeira busca real), não no `__init__`:
        checar ali forçaria uma conexão de rede com o Qdrant mesmo para um
        PR sem nenhum arquivo revisável.
        """
        if self._guarda_verificada:
            return
        self._store.assert_model_matches(self._embedder.model_name)
        self._guarda_verificada = True

    def _retrieve_for_file(self, file_diff: FileDiff) -> RetrievedContext | None:
        """
        Consulta o Qdrant uma vez POR LINHA ADICIONADA e une os resultados.

        A unidade de recuperação é a linha, igual à unidade de avaliação de
        D-001. Consultar por arquivo concatenava linhas heterogêneas numa
        média semântica que não representava nenhuma delas — a causa dos
        scores comprimidos entre 0.3 e 0.5 (spec §3).

        A granularidade da chamada ao LLM NÃO muda: continua uma por arquivo,
        sobre a união deduplicada.

        Returns:
            RetrievedContext se houver chunks acima do threshold, None caso contrário.
        """
        self._ensure_model_guard()

        linhas = file_diff.added_lines

        console.log(
            f"[dim]Retriever:[/dim] buscando normas para "
            f"[bold]{file_diff.filename}[/bold] ({len(linhas)} linha(s))..."
        )

        # Uma passada de inferência e uma ida ao Qdrant para o arquivo inteiro.
        # Embedar linha a linha desperdiçava o `batch_size` do Embedder (lote de
        # tamanho 1 por linha) e gastava uma requisição de rede por linha. A
        # unidade de CONSULTA continua sendo a linha (D-001): o lote não mistura
        # as linhas, só as envia juntas.
        vetores_densos = [v.tolist() for v in self._embedder.embed(linhas)]

        if self._hybrid:
            # Denso + esparso BM25 com fusão RRF (L4): o esparso cobre o
            # casamento lexical (`== True`, `!= None`) que o denso sozinho
            # erra por ser um problema de string, não de significado.
            resultados_por_linha = self._store.search_hybrid_batch(
                dense=vetores_densos,
                sparse=self._sparse_encoder.encode_batch(linhas),
                top_k=self._top_k,
            )
        else:
            resultados_por_linha = self._store.search_batch(
                query_vectors=vetores_densos,
                top_k=self._top_k,
                score_threshold=self._score_threshold,
            )

        vistos: set[tuple[str, str]] = set()
        unidos: list[dict] = []

        for resultados in resultados_por_linha:
            for chunk in resultados:
                chave = (chunk["source"], chunk["section"])
                if chave in vistos:
                    continue
                vistos.add(chave)
                unidos.append(chunk)

        if not unidos:
            console.log(
                f"[dim]Retriever:[/dim] nenhum chunk relevante para "
                f"[bold]{file_diff.filename}[/bold] "
                f"(threshold={self._score_threshold})."
            )
            return None

        # Maior score primeiro, depois corta em max_chunks (o N da spec §4.3):
        # contexto excedente comprovadamente induz alucinação.
        unidos.sort(key=lambda c: c["score"], reverse=True)
        unidos = unidos[: self._max_chunks]

        console.log(
            f"[dim]Retriever:[/dim] {len(unidos)} chunk(s) para "
            f"[bold]{file_diff.filename}[/bold] "
            f"(top score: {unidos[0]['score']:.3f})."
        )

        return RetrievedContext(
            file_diff=file_diff,
            chunks=unidos,
            query_text="\n".join(linhas),
        )
