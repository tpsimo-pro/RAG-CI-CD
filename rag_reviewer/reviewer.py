"""
reviewer.py - Orquestrador do RAG-Reviewer (o que o GitHub Action executa).

Fluxo: diff do PR -> recuperação de normas -> LLM por arquivo -> publicação.
A revisão nunca bloqueia o PR (D-011): a PEP 8 é estilo.
"""

from __future__ import annotations

import time

from rich.console import Console

from rag_reviewer.diff_parser import DiffCollector, FileDiff
from rag_reviewer.embedder import Embedder
from rag_reviewer.llm_client import LLMClient, Violation
from rag_reviewer.retriever import RetrievedContext, Retriever
from rag_reviewer.vector_store import VectorStore

console = Console()

ViolationList = list[tuple[FileDiff, Violation]]

_ESPERA_RATE_LIMIT_PADRAO = 20.0
_ESPERA_RATE_LIMIT_MAXIMA = 30.0  # o Action tem timeout de 10 minutos


class RAGReviewer:
    """Coordena coleta, recuperação, LLM e publicação. Dependências injetáveis."""

    def __init__(
        self,
        collector: DiffCollector | None = None,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
        retriever: Retriever | None = None,
        llm: LLMClient | None = None,
        publisher=None,
    ) -> None:
        self._collector = collector or DiffCollector()
        self._retriever = retriever or Retriever(
            embedder=embedder or Embedder(), store=store or VectorStore()
        )
        self._llm = llm or LLMClient()
        self._publisher = publisher  # GitHubPublisher, criado sob demanda

    def run(self) -> ViolationList:
        """Revisa o PR e publica o resultado. Devolve as violações encontradas."""
        console.rule("[bold cyan]RAG-Reviewer: iniciando revisão[/bold cyan]")

        pr_diff = self._collector.collect()
        if not pr_diff.files:
            self._get_publisher().post_summary(
                "Nenhum arquivo Python com linhas adicionadas para revisar."
            )
            return []

        contextos = self._retriever.retrieve_for_diff(pr_diff)
        if not contextos:
            self._get_publisher().post_summary(
                "Nenhuma norma da PEP 8 foi recuperada para as linhas adicionadas."
            )
            return []

        violacoes, nao_revisados = self._review_all_contexts(contextos)
        self._get_publisher().publish(
            violacoes, pr_diff, unreviewed=nao_revisados, model=self._llm.model
        )
        if nao_revisados and len(nao_revisados) == len(contextos):
            raise RuntimeError(
                "Nenhum arquivo foi revisado: a chamada ao LLM falhou em todos."
            )

        console.rule(
            f"[bold green]RAG-Reviewer concluído: "
            f"{self._build_summary(violacoes)}[/bold green]"
        )
        return violacoes

    # ── Internos ──────────────────────────────────────────────────────────

    def _review_all_contexts(
        self, contextos: list[RetrievedContext]
    ) -> tuple[ViolationList, list[str]]:
        """Uma chamada ao LLM por arquivo. Falha num arquivo não derruba os demais."""
        violacoes: ViolationList = []
        nao_revisados: list[str] = []
        for contexto in contextos:
            try:
                encontradas = self._review_with_retry(contexto)
            except Exception as exc:  # noqa: BLE001 - registra e segue com os demais
                console.log(
                    f"[red]Falha ao revisar {contexto.file_diff.filename}:[/red] {exc}"
                )
                nao_revisados.append(contexto.file_diff.filename)
                continue
            violacoes.extend((contexto.file_diff, v) for v in encontradas)
        return violacoes, nao_revisados

    def _review_with_retry(self, contexto: RetrievedContext) -> list[Violation]:
        """Chama o LLM; num rate limit (429) espera pouco e tenta uma única vez de novo."""
        try:
            return self._llm.review(contexto)
        except Exception as exc:
            if type(exc).__name__ != "RateLimitError":
                raise
            espera = _espera_rate_limit(exc)
            console.log(
                f"[yellow]Rate limit da Groq; aguardando {espera:.0f}s "
                "e tentando uma vez de novo.[/yellow]"
            )
            time.sleep(espera)
            return self._llm.review(contexto)

    def _get_publisher(self):
        if self._publisher is None:
            from rag_reviewer.github_publisher import GitHubPublisher

            self._publisher = GitHubPublisher()
        return self._publisher

    @staticmethod
    def _build_summary(violacoes: ViolationList) -> str:
        if not violacoes:
            return "nenhuma violação detectada"
        por_severidade: dict[str, int] = {}
        for _, v in violacoes:
            por_severidade[v.severity] = por_severidade.get(v.severity, 0) + 1
        partes = [f"{n} {sev}" for sev, n in sorted(por_severidade.items())]
        return f"{len(violacoes)} violação(ões): {', '.join(partes)}"


def _espera_rate_limit(exc: Exception) -> float:
    """Segundos de espera sugeridos pelo cabeçalho `retry-after`, no máximo 30."""
    cabecalhos = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        return min(float(cabecalhos.get("retry-after")), _ESPERA_RATE_LIMIT_MAXIMA)
    except (TypeError, ValueError):
        return _ESPERA_RATE_LIMIT_PADRAO
