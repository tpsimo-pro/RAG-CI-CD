"""
index_pipeline.py — Orquestrador do pipeline offline de indexação.

Fluxo:
  1. Carrega todos os documentos suportados do diretório docs/
  2. Divide em chunks com sobreposição
  3. Gera embeddings com sentence-transformers
  4. Insere/atualiza no Qdrant

Pode ser executado diretamente:
  python -m indexer.index_pipeline --docs-dir docs/style_guides --recreate

Ou via Makefile:
  make index
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from indexer.chunker import RecursiveChunker
from indexer.document_loader import DocumentLoader
from rag_reviewer.embedder import Embedder
from rag_reviewer.vector_store import VectorStore

# Garante que o pacote raiz está no sys.path ao executar diretamente
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))



console = Console()


def run_indexing(
    docs_dir: str | Path,
    collection_name: str | None = None,
    recreate: bool = False,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> dict:
    """
    Executa o pipeline completo de indexação.

    Args:
        docs_dir:        Diretório com os documentos normativos.
        collection_name: Nome da coleção Qdrant (usa default das configs se None).
        recreate:        Se True, apaga e recria a coleção antes de indexar.
        chunk_size:      Tamanho dos chunks em palavras.
        chunk_overlap:   Sobreposição entre chunks em palavras.

    Returns:
        Dict com estatísticas da indexação: n_documents, n_chunks, elapsed_seconds.
    """
    start_time = time.perf_counter()

    docs_dir = Path(docs_dir)
    if not docs_dir.exists():
        raise FileNotFoundError(f"Diretório não encontrado: {docs_dir}")

    console.print(
        Panel(
            f"[bold cyan]RAG-Reviewer — Pipeline de Indexação[/bold cyan]\n"
            f"Diretório: [green]{docs_dir.resolve()}[/green]\n"
            f"Recriar coleção: [yellow]{recreate}[/yellow]",
            expand=False,
        )
    )

    # ── Etapa 1: Carregar documentos ─────────────────────────────────────
    console.rule("[bold]Etapa 1 — Carregamento de Documentos[/bold]")
    loader = DocumentLoader()
    all_docs = loader.load_directory(docs_dir)

    if not all_docs:
        console.print(
            f"[red]❌ Nenhum documento encontrado em '{docs_dir}'. "
            "Verifique se há arquivos .pdf, .md, .docx ou .txt no diretório.[/red]"
        )
        return {"n_documents": 0, "n_chunks": 0, "elapsed_seconds": 0.0}

    console.print(f"[green]✅ {len(all_docs)} seção(ões) carregada(s).[/green]\n")

    # ── Etapa 2: Chunking ────────────────────────────────────────────────
    console.rule("[bold]Etapa 2 — Chunking[/bold]")
    chunker = RecursiveChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = chunker.split(all_docs)
    console.print(f"[green]✅ {len(chunks)} chunks gerados.[/green]\n")

    # ── Etapa 3: Embeddings ───────────────────────────────────────────────
    console.rule("[bold]Etapa 3 — Geração de Embeddings[/bold]")
    embedder = Embedder()
    texts = [c.text for c in chunks]
    embeddings = embedder.embed(texts)
    console.print(f"[green]✅ Embeddings gerados. Shape: {embeddings.shape}[/green]\n")

    # ── Etapa 4: Inserção no Qdrant ───────────────────────────────────────
    console.rule("[bold]Etapa 4 — Inserção no Qdrant[/bold]")
    store = VectorStore(collection_name=collection_name)

    if recreate:
        store.recreate_collection(vector_size=embedder.vector_size)

    store.upsert(chunks=chunks, embeddings=embeddings)

    # ── Resumo final ─────────────────────────────────────────────────────
    elapsed = time.perf_counter() - start_time

    _print_summary(
        docs_dir=docs_dir,
        n_docs=len(all_docs),
        n_chunks=len(chunks),
        vector_size=embedder.vector_size,
        collection=store.collection_name,
        elapsed=elapsed,
    )

    return {
        "n_documents": len(all_docs),
        "n_chunks": len(chunks),
        "elapsed_seconds": elapsed,
    }


def _print_summary(
    docs_dir: Path,
    n_docs: int,
    n_chunks: int,
    vector_size: int,
    collection: str,
    elapsed: float,
) -> None:
    """Imprime uma tabela de resumo com as estatísticas da indexação."""
    table = Table(
        title="📊 Resumo da Indexação", show_header=True, header_style="bold magenta"
    )
    table.add_column("Parâmetro", style="cyan")
    table.add_column("Valor", style="green")

    table.add_row("Diretório indexado", str(docs_dir.resolve()))
    table.add_row("Seções carregadas", str(n_docs))
    table.add_row("Chunks gerados", str(n_chunks))
    table.add_row("Dimensão dos vetores", str(vector_size))
    table.add_row("Coleção Qdrant", collection)
    table.add_row("Tempo total", f"{elapsed:.1f}s")

    console.print()
    console.print(table)
    console.print(
        "\n[bold green]🎉 Indexação concluída com sucesso![/bold green] "
        "O guia de estilo está pronto para consultas RAG."
    )


# ── CLI ───────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pipeline de indexação do RAG-Reviewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Indexa o diretório padrão e recria a coleção
  python -m indexer.index_pipeline --recreate

  # Indexa um diretório específico sem recriar
  python -m indexer.index_pipeline --docs-dir docs/style_guides

  # Ajusta parâmetros de chunking
  python -m indexer.index_pipeline --chunk-size 256 --chunk-overlap 32 --recreate
        """,
    )
    parser.add_argument(
        "--docs-dir",
        default="docs/style_guides",
        help="Diretório com os documentos normativos (padrão: docs/style_guides)",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Nome da coleção Qdrant (padrão: valor da env QDRANT_COLLECTION)",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Apaga e recria a coleção antes de indexar",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Tamanho dos chunks em palavras (padrão: 512)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=64,
        help="Sobreposição entre chunks em palavras (padrão: 64)",
    )
    return parser


if __name__ == "__main__":
    args = _build_parser().parse_args()

    try:
        run_indexing(
            docs_dir=args.docs_dir,
            collection_name=args.collection,
            recreate=args.recreate,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]❌ Erro: {exc}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Indexação interrompida pelo usuário.[/yellow]")
        sys.exit(0)
