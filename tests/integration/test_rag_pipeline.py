"""
test_rag_pipeline.py — Testes de integração do pipeline completo do RAG-Reviewer.

Valida o fluxo end-to-end:
    DiffCollector → Retriever → LLMClient → GitHubPublisher

Todas as dependências externas (GitHub API, Qdrant, Groq) são mockadas,
garantindo que os testes rodem sem acesso à rede.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from rag_reviewer.diff_parser import FileDiff, PullRequestDiff
from rag_reviewer.llm_client import LLMClient, Violation
from rag_reviewer.retriever import RetrievedContext
from rag_reviewer.reviewer import RAGReviewer


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def sample_file_diff() -> FileDiff:
    """FileDiff representando um arquivo com violação de comparação booleana."""
    return FileDiff(
        filename="auth/validator.py",
        patch=(
            "@@ -0,0 +1,4 @@\n"
            "+def is_user_active(user):\n"
            "+    if user.active == True:\n"
            "+        return user.session_token\n"
            "+    return None"
        ),
        status="modified",
        additions=4,
        deletions=0,
        added_lines=[
            "def is_user_active(user):",
            "    if user.active == True:",
            "        return user.session_token",
            "    return None",
        ],
    )


@pytest.fixture()
def sample_pr_diff(sample_file_diff: FileDiff) -> PullRequestDiff:
    """PullRequestDiff com um único arquivo modificado."""
    return PullRequestDiff(
        pr_number=42,
        repo="org/repo",
        files=[sample_file_diff],
        total_additions=4,
        total_deletions=0,
    )


@pytest.fixture()
def sample_chunks() -> list[dict]:
    """Chunks normativos simulados retornados pelo Qdrant."""
    return [
        {
            "text": (
                "Comparações booleanas: Não compare valores booleanos com "
                "== True ou == False. Use diretamente o valor booleano."
            ),
            "source": "guia_python_pep8.md",
            "section": "Seção 5: Práticas de Código e Idiomas Pythonicos",
            "score": 0.92,
        }
    ]


@pytest.fixture()
def sample_violation() -> Violation:
    """Violation representando a comparação booleana detectada."""
    return Violation(
        line_content="    if user.active == True:",
        violation_description=(
            "Comparação booleana com == True é antipadrão. "
            "Use diretamente o valor booleano."
        ),
        norm_reference="guia_python_pep8.md — Seção 5: Comparações booleanas",
        severity="MEDIUM",
        suggestion="Substituir por: if user.active:",
    )


@pytest.fixture()
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Injeta variáveis de ambiente mínimas para os testes."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("REPO_FULL_NAME", "org/repo")
    monkeypatch.setenv("PR_NUMBER", "42")
    monkeypatch.setenv("PR_HEAD_SHA", "abc123def456")
    monkeypatch.setenv("PR_BASE_SHA", "000000")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    from rag_reviewer.config import get_settings
    get_settings.cache_clear()


# ── Testes do LLMClient ───────────────────────────────────────────────────────


class TestLLMClientIntegration:
    """Testes de integração do LLMClient com mocks da API Groq."""

    def test_review_returns_violations_on_valid_response(
        self,
        mock_env: None,
        sample_file_diff: FileDiff,
        sample_chunks: list[dict],
    ) -> None:
        """LLMClient deve parsear corretamente a resposta JSON do Groq."""
        context = RetrievedContext(
            file_diff=sample_file_diff,
            chunks=sample_chunks,
            query_text="def is_user_active(user): if user.active == True:",
        )

        mock_response_json = json.dumps(
            {
                "violations": [
                    {
                        "line_content": "if user.active == True:",
                        "violation_description": "Comparação com == True é antipadrão.",
                        "norm_reference": "guia_python_pep8.md — Seção 5",
                        "severity": "MEDIUM",
                        "suggestion": "Use: if user.active:",
                    }
                ]
            }
        )

        mock_choice = MagicMock()
        mock_choice.message.content = mock_response_json
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        with patch("groq.Groq") as mock_groq_class:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_completion
            mock_groq_class.return_value = mock_client

            llm = LLMClient()
            violations = llm.review(context)

        assert len(violations) == 1
        assert violations[0].severity == "MEDIUM"
        assert "== True" in violations[0].line_content

    def test_review_returns_empty_list_when_no_violations(
        self,
        mock_env: None,
        sample_file_diff: FileDiff,
        sample_chunks: list[dict],
    ) -> None:
        """LLMClient deve retornar lista vazia quando LLM não encontra violações."""
        context = RetrievedContext(
            file_diff=sample_file_diff,
            chunks=sample_chunks,
            query_text="code without violations",
        )

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({"violations": []})
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        with patch("groq.Groq") as mock_groq_class:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_completion
            mock_groq_class.return_value = mock_client

            llm = LLMClient()
            violations = llm.review(context)

        assert violations == []

    def test_review_handles_json_wrapped_in_markdown(
        self,
        mock_env: None,
        sample_file_diff: FileDiff,
        sample_chunks: list[dict],
    ) -> None:
        """LLMClient deve extrair JSON mesmo quando envolvido em bloco markdown."""
        context = RetrievedContext(
            file_diff=sample_file_diff,
            chunks=sample_chunks,
            query_text="test",
        )

        wrapped_json = (
            "Aqui está a análise:\n\n"
            "```json\n"
            '{"violations": [{"line_content": "x", "violation_description": "desc",'
            ' "norm_reference": "ref", "severity": "LOW", "suggestion": "fix"}]}\n'
            "```"
        )

        mock_choice = MagicMock()
        mock_choice.message.content = wrapped_json
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        with patch("groq.Groq") as mock_groq_class:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_completion
            mock_groq_class.return_value = mock_client

            llm = LLMClient()
            violations = llm.review(context)

        assert len(violations) == 1
        assert violations[0].severity == "LOW"


# ── Testes do RAGReviewer (orquestrador) ──────────────────────────────────────


class TestRAGReviewerIntegration:
    """Testes de integração do orquestrador RAGReviewer."""

    def test_run_publishes_violations_when_found(
        self,
        mock_env: None,
        sample_pr_diff: PullRequestDiff,
        sample_violation: Violation,
        sample_file_diff: FileDiff,
    ) -> None:
        """RAGReviewer.run() deve chamar publisher.publish() com as violações."""
        mock_collector = MagicMock()
        mock_collector.collect.return_value = sample_pr_diff

        mock_retriever = MagicMock()
        mock_retriever.retrieve_for_diff.return_value = [
            RetrievedContext(
                file_diff=sample_file_diff,
                chunks=[{"text": "norm", "source": "guide.md", "section": "S1", "score": 0.9}],
                query_text="query",
            )
        ]

        mock_llm = MagicMock()
        mock_llm.review.return_value = [sample_violation]

        mock_publisher = MagicMock()

        reviewer = RAGReviewer(
            collector=mock_collector,
            retriever=mock_retriever,
            llm=mock_llm,
            publisher=mock_publisher,
        )

        violations = reviewer.run()

        assert len(violations) == 1
        mock_publisher.publish.assert_called_once()
        _, kwargs_or_args = mock_publisher.publish.call_args_list[0], None
        call_args = mock_publisher.publish.call_args
        assert call_args[0][0] == violations  # primeiro argumento = violations

    def test_run_posts_approval_when_no_files(
        self,
        mock_env: None,
    ) -> None:
        """RAGReviewer.run() deve postar aprovação quando PR não tem arquivos relevantes."""
        empty_diff = PullRequestDiff(
            pr_number=1, repo="org/repo", files=[], total_additions=0, total_deletions=0
        )

        mock_collector = MagicMock()
        mock_collector.collect.return_value = empty_diff

        mock_publisher = MagicMock()

        reviewer = RAGReviewer(collector=mock_collector, publisher=mock_publisher)
        violations = reviewer.run()

        assert violations == []
        mock_publisher.post_summary.assert_called_once()

    def test_run_posts_approval_when_no_context_found(
        self,
        mock_env: None,
        sample_pr_diff: PullRequestDiff,
    ) -> None:
        """RAGReviewer.run() deve postar aprovação quando Qdrant não retorna chunks."""
        mock_collector = MagicMock()
        mock_collector.collect.return_value = sample_pr_diff

        mock_retriever = MagicMock()
        mock_retriever.retrieve_for_diff.return_value = []  # Qdrant sem resultados

        mock_publisher = MagicMock()

        reviewer = RAGReviewer(
            collector=mock_collector,
            retriever=mock_retriever,
            publisher=mock_publisher,
        )
        violations = reviewer.run()

        assert violations == []
        mock_publisher.post_summary.assert_called_once()

    def test_run_requests_changes_on_critical_violation(
        self,
        mock_env: None,
        sample_pr_diff: PullRequestDiff,
        sample_file_diff: FileDiff,
    ) -> None:
        """RAGReviewer.run() deve chamar request_changes quando há violação CRITICAL."""
        critical_violation = Violation(
            line_content="from secrets import *",
            violation_description="Import * proibido.",
            norm_reference="guia_python_pep8.md — Seção 3.2",
            severity="CRITICAL",
            suggestion="Importar explicitamente.",
        )

        mock_collector = MagicMock()
        mock_collector.collect.return_value = sample_pr_diff

        mock_retriever = MagicMock()
        mock_retriever.retrieve_for_diff.return_value = [
            RetrievedContext(
                file_diff=sample_file_diff,
                chunks=[{"text": "norm", "source": "g.md", "section": "S1", "score": 0.9}],
                query_text="q",
            )
        ]

        mock_llm = MagicMock()
        mock_llm.review.return_value = [critical_violation]

        mock_publisher = MagicMock()

        reviewer = RAGReviewer(
            collector=mock_collector,
            retriever=mock_retriever,
            llm=mock_llm,
            publisher=mock_publisher,
        )
        reviewer.run()

        mock_publisher.request_changes.assert_called_once()
        call_message = mock_publisher.request_changes.call_args[0][0]
        assert "CRÍTICA" in call_message or "crítica" in call_message.lower()
