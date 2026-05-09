"""
main.py — Ponto de entrada principal do RAG-Reviewer.

Este script é o que o GitHub Actions executará.
Ele instancia o orquestrador (RAGReviewer) e inicia o processo.
"""

from __future__ import annotations

import sys

from rich.console import Console

from rag_reviewer.reviewer import RAGReviewer

console = Console()


def main() -> None:
    try:
        reviewer = RAGReviewer()
        reviewer.run()
    except Exception as exc:
        console.print_exception(show_locals=True)
        console.log(
            f"[bold red]Erro fatal durante a execução do RAG-Reviewer:[/bold red] {exc}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
