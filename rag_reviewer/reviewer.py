"""
reviewer.py — Orquestrador principal do RAG-Reviewer (Componente 4, Fase 2).

Responsabilidades:
  1. Instanciar e coordenar todos os módulos do pipeline online.
  2. Executar o fluxo completo: diff → retrieval → LLM → publicação.
  3. Decidir o status final do PR (COMMENT ou REQUEST_CHANGES).

Uso típico (chamado pelo GitHub Actions via __main__.py):
    reviewer = RAGReviewer()
    reviewer.run()
"""

from __future__ import annotations

from typing import List, Tuple

from rich.console import Console

from rag_reviewer.config import get_settings
from rag_reviewer.diff_parser import DiffCollector, FileDiff, PullRequestDiff
from rag_reviewer.embedder import Embedder
from rag_reviewer.llm_client import LLMClient, Violation
from rag_reviewer.retriever import RetrievedContext, Retriever
from rag_reviewer.vector_store import VectorStore

console = Console()

# Tipo alias para a lista de violações com referência ao arquivo de origem
ViolationList = List[Tuple[FileDiff, Violation]]


class RAGReviewer:
    """
    Orquestra todo o fluxo: diff → retrieval → LLM → publicação.

    Cada componente é injetável para facilitar testes de integração.
    Em produção, todos os parâmetros têm defaults que leem de get_settings().
    """

    def __init__(
        self,
        collector: DiffCollector | None = None,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
        retriever: Retriever | None = None,
        llm: LLMClient | None = None,
        publisher=None,  # GitHubPublisher — importado lazy para evitar dependência circular
    ) -> None:
        """
        Inicializa o orquestrador.

        Args:
            collector: Coleta o diff do PR. Default: DiffCollector().
            embedder: Gera embeddings. Default: Embedder().
            store: Interface com Qdrant. Default: VectorStore().
            retriever: Recupera contexto normativo. Default: Retriever().
            llm: Gera revisões via LLM. Default: LLMClient().
            publisher: Publica comentários no GitHub. Default: GitHubPublisher().
        """
        self._collector = collector or DiffCollector()
        _embedder = embedder or Embedder()
        _store = store or VectorStore()
        self._retriever = retriever or Retriever(embedder=_embedder, store=_store)
        self._llm = llm or LLMClient()
        self._publisher = publisher  # resolvido lazy em run() se None

    # ── Interface pública ─────────────────────────────────────────────────

    def run(self) -> ViolationList:
        """
        Executa o pipeline completo de revisão de PR.

        Fluxo:
          1. Coleta o diff do PR via GitHub API.
          2. Recupera contexto normativo do Qdrant para cada arquivo.
          3. Envia cada arquivo ao LLM para identificação de violações.
          4. Publica os comentários no PR via GitHub API.
          5. Solicita changes se houver violações críticas.

        Returns:
            Lista de (FileDiff, Violation) com todas as violações encontradas.
        """
        console.rule("[bold cyan]RAG-Reviewer: iniciando revisão[/bold cyan]")

        # Etapa 1: Coleta do diff
        pr_diff = self._collector.collect()

        if not pr_diff.files:
            console.log("[yellow]⚠️  Nenhum arquivo relevante no PR. Encerrando.[/yellow]")
            self._publish_no_violations()
            return []

        # Etapa 2: Recuperação de contexto normativo
        contexts = self._retriever.retrieve_for_diff(pr_diff)

        if not contexts:
            console.log(
                "[yellow]⚠️  Nenhum contexto normativo encontrado para os arquivos do PR.[/yellow]"
            )
            self._publish_no_violations()
            return []

        # Etapa 3: Geração de violações via LLM
        all_violations = self._review_all_contexts(contexts)

        # Etapa 4: Publicação
        publisher = self._get_publisher()
        publisher.publish(all_violations, pr_diff)

        # Etapa 5: Status do PR
        self._handle_pr_status(all_violations)

        summary = self._build_summary(all_violations)
        console.rule(f"[bold green]RAG-Reviewer concluído — {summary}[/bold green]")

        return all_violations

    def review_context(self, context: RetrievedContext) -> List[Violation]:
        """
        Revisa um único RetrievedContext.

        Ponto de entrada conveniente para testes e depuração sem precisar
        de um PR completo.
        """
        return self._llm.review(context)

    # ── Internos ──────────────────────────────────────────────────────────

    def _review_all_contexts(self, contexts: List[RetrievedContext]) -> ViolationList:
        """Itera sobre os contextos e acumula as violações."""
        all_violations: ViolationList = []
        for context in contexts:
            violations = self._llm.review(context)
            all_violations.extend(
                (context.file_diff, v) for v in violations
            )
        return all_violations

    def _handle_pr_status(self, violations: ViolationList) -> None:
        """
        Solicita changes se houver violações críticas e BLOCK_ON_CRITICAL=true.
        """
        settings = get_settings()
        if not settings.block_on_critical:
            return

        critical = [v for _, v in violations if v.severity == "CRITICAL"]
        if critical:
            publisher = self._get_publisher()
            publisher.request_changes(
                f"⛔ {len(critical)} violação(ões) CRÍTICA(S) detectada(s). "
                "Corrija antes de fazer o merge.\n\n"
                "Verifique os comentários inline acima para detalhes."
            )

    def _publish_no_violations(self) -> None:
        """Publica comentário de aprovação quando não há violações."""
        try:
            publisher = self._get_publisher()
            publisher.post_summary("✅ Nenhuma violação detectada nas normas organizacionais.")
        except Exception:
            # Publisher pode não estar disponível em testes; não bloqueia
            pass

    def _get_publisher(self):
        """Retorna o publisher com lazy initialization."""
        if self._publisher is None:
            from rag_reviewer.github_publisher import GitHubPublisher  # type: ignore
            self._publisher = GitHubPublisher()
        return self._publisher

    @staticmethod
    def _build_summary(violations: ViolationList) -> str:
        """Constrói string de sumário para o log final."""
        if not violations:
            return "nenhuma violação detectada"
        total = len(violations)
        by_severity: dict[str, int] = {}
        for _, v in violations:
            by_severity[v.severity] = by_severity.get(v.severity, 0) + 1
        parts = [f"{count} {sev}" for sev, count in sorted(by_severity.items())]
        return f"{total} violação(ões): {', '.join(parts)}"
