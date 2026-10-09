"""
main.py - Ponto de entrada do GitHub Action: `python -m rag_reviewer.main`.
"""

from __future__ import annotations

import sys

from rich.console import Console

from rag_reviewer.reviewer import RAGReviewer

console = Console()


def main() -> None:
    try:
        RAGReviewer().run()
    except Exception as exc:  # noqa: BLE001 - o job precisa falhar com mensagem clara
        # show_locals=False: os locais podem conter tokens e chaves de API.
        console.print_exception(show_locals=False)
        console.log(f"[bold red]Erro fatal no RAG-Reviewer:[/bold red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
