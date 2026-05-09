"""Testes unitários para rag_reviewer/llm_client.py e rag_reviewer/reviewer.py.

Todos os testes são isolados via unittest.mock — sem chamadas reais à API.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from rag_reviewer.diff_parser import FileDiff
from rag_reviewer.llm_client import _VALID_SEVERITIES, LLMClient, Violation
from rag_reviewer.retriever import RetrievedContext
from rag_reviewer.reviewer import RAGReviewer

# ── Helpers de fixture ────────────────────────────────────────────────────────


def make_file_diff(
    filename: str = "src/app.py",
    added_lines: list | None = None,
) -> FileDiff:
    if added_lines is None:
        added_lines = ["def foo():", "    return 42"]
    return FileDiff(
        filename=filename,
        patch="",
        status="modified",
        additions=len(added_lines),
        deletions=0,
        added_lines=added_lines,
    )


def make_chunk(
    text: str = "Funções devem ter responsabilidade única.",
    source: str = "coding_standards.md",
    section: str = "3.2 Funções",
    score: float = 0.85,
) -> dict:
    return {
        "text": text,
        "source": source,
        "section": section,
        "page": 0,
        "score": score,
    }


def make_context(
    filename: str = "src/app.py",
    added_lines: list | None = None,
    chunks: list | None = None,
) -> RetrievedContext:
    fd = make_file_diff(filename=filename, added_lines=added_lines)
    return RetrievedContext(
        file_diff=fd,
        chunks=chunks if chunks is not None else [make_chunk()],
        query_text=f"Arquivo: {filename}\n",
    )


def make_violation_dict(
    line_content: str = "    return 42",
    violation_description: str = "Função retorna valor mágico",
    norm_reference: str = "coding_standards.md § 3.2",
    severity: str = "HIGH",
    suggestion: str = "Use uma constante nomeada",
) -> dict:
    return {
        "line_content": line_content,
        "violation_description": violation_description,
        "norm_reference": norm_reference,
        "severity": severity,
        "suggestion": suggestion,
    }


def make_llm_response(violations: list | None = None) -> str:
    """Gera uma resposta JSON simulando a saída do LLM."""
    data = {
        "violations": violations if violations is not None else [make_violation_dict()]
    }
    return json.dumps(data)


def make_llm_client(api_key: str = "sk-test") -> LLMClient:
    """Cria LLMClient com api_key explícita para evitar dependência do .env."""
    with patch.object(LLMClient, "_load_prompt", return_value="prompt mock"):
        client = LLMClient.__new__(LLMClient)
        client._api_key = api_key
        client._model = "groq-test"
        client._max_tokens = 1024
        client._client = None
        client._system_prompt = "system mock"
        client._review_template = "## Arquivo\n{filename}\n## Linhas\n{added_lines}\n## Normas\n{retrieved_chunks}"
    return client


# ══════════════════════════════════════════════════════════════════════════════
# Testes: Violation dataclass
# ══════════════════════════════════════════════════════════════════════════════


class TestViolation:
    def test_construction(self):
        v = Violation(
            line_content="x = 1",
            violation_description="Desc",
            norm_reference="doc § 1",
            severity="HIGH",
            suggestion="Fix it",
        )
        assert v.severity == "HIGH"
        assert v.line_content == "x = 1"

    def test_valid_severities_set(self):
        assert "CRITICAL" in _VALID_SEVERITIES
        assert "HIGH" in _VALID_SEVERITIES
        assert "MEDIUM" in _VALID_SEVERITIES
        assert "LOW" in _VALID_SEVERITIES
        assert len(_VALID_SEVERITIES) == 4


# ══════════════════════════════════════════════════════════════════════════════
# Testes: LLMClient — prompts
# ══════════════════════════════════════════════════════════════════════════════


class TestLLMClientPrompts:
    def test_system_prompt_file_exists(self):
        path = (
            Path(__file__).parent.parent.parent
            / "rag_reviewer"
            / "prompts"
            / "system_prompt.txt"
        )
        assert path.exists(), f"system_prompt.txt não encontrado em {path}"

    def test_review_template_file_exists(self):
        path = (
            Path(__file__).parent.parent.parent
            / "rag_reviewer"
            / "prompts"
            / "review_template.txt"
        )
        assert path.exists(), f"review_template.txt não encontrado em {path}"

    def test_load_prompt_raises_when_file_missing(self):
        with pytest.raises(FileNotFoundError, match="nonexistent.txt"):
            LLMClient._load_prompt("nonexistent.txt")

    def test_review_template_contains_placeholders(self):
        template = LLMClient._load_prompt("review_template.txt")
        assert "{filename}" in template
        assert "{added_lines}" in template
        assert "{retrieved_chunks}" in template


# ══════════════════════════════════════════════════════════════════════════════
# Testes: LLMClient — _validate_api_key
# ══════════════════════════════════════════════════════════════════════════════


class TestLLMClientValidation:
    def test_raises_when_api_key_missing(self):
        client = make_llm_client(api_key="")
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            client._validate_api_key()

    def test_passes_when_api_key_present(self):
        client = make_llm_client(api_key="sk-valid")
        client._validate_api_key()  # não deve levantar


# ══════════════════════════════════════════════════════════════════════════════
# Testes: LLMClient — _build_user_message
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildUserMessage:
    def test_includes_filename(self):
        client = make_llm_client()
        ctx = make_context(filename="src/payment.py")
        msg = client._build_user_message(ctx)
        assert "src/payment.py" in msg

    def test_includes_added_lines(self):
        client = make_llm_client()
        ctx = make_context(added_lines=["amount = price * 1.1"])
        msg = client._build_user_message(ctx)
        assert "amount = price * 1.1" in msg

    def test_includes_chunk_source(self):
        client = make_llm_client()
        ctx = make_context(chunks=[make_chunk(source="clean_code.md")])
        msg = client._build_user_message(ctx)
        assert "clean_code.md" in msg

    def test_includes_chunk_section(self):
        client = make_llm_client()
        ctx = make_context(chunks=[make_chunk(section="4.1 Naming")])
        msg = client._build_user_message(ctx)
        assert "4.1 Naming" in msg

    def test_includes_chunk_text(self):
        client = make_llm_client()
        ctx = make_context(chunks=[make_chunk(text="Nomes devem ser descritivos.")])
        msg = client._build_user_message(ctx)
        assert "Nomes devem ser descritivos." in msg

    def test_multiple_chunks_separated(self):
        client = make_llm_client()
        ctx = make_context(
            chunks=[
                make_chunk(text="Norma A"),
                make_chunk(text="Norma B"),
            ]
        )
        msg = client._build_user_message(ctx)
        assert "Norma A" in msg
        assert "Norma B" in msg
        assert "---" in msg  # separador entre chunks


# ══════════════════════════════════════════════════════════════════════════════
# Testes: LLMClient — _extract_json
# ══════════════════════════════════════════════════════════════════════════════


class TestExtractJson:
    def test_direct_json_parsing(self):
        client = make_llm_client()
        raw = '{"violations": []}'
        assert client._extract_json(raw) == {"violations": []}

    def test_extracts_json_from_code_block(self):
        client = make_llm_client()
        raw = 'Texto antes\n```json\n{"violations": []}\n```\nTexto depois'
        result = client._extract_json(raw)
        assert result == {"violations": []}

    def test_extracts_json_from_plain_code_block(self):
        client = make_llm_client()
        raw = '```\n{"violations": []}\n```'
        result = client._extract_json(raw)
        assert result == {"violations": []}

    def test_raises_when_no_valid_json(self):
        import json as _json

        client = make_llm_client()
        with pytest.raises(_json.JSONDecodeError):
            client._extract_json("Isso não é JSON de jeito nenhum.")

    def test_nested_json_preserved(self):
        client = make_llm_client()
        raw = json.dumps({"violations": [make_violation_dict()]})
        data = client._extract_json(raw)
        assert len(data["violations"]) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Testes: LLMClient — _parse_single_violation
# ══════════════════════════════════════════════════════════════════════════════


class TestParseSingleViolation:
    def test_parses_valid_dict(self):
        client = make_llm_client()
        v = client._parse_single_violation(make_violation_dict())
        assert isinstance(v, Violation)
        assert v.severity == "HIGH"

    def test_severity_normalized_to_uppercase(self):
        client = make_llm_client()
        d = make_violation_dict(severity="critical")
        v = client._parse_single_violation(d)
        assert v.severity == "CRITICAL"

    def test_invalid_severity_defaults_to_low(self):
        client = make_llm_client()
        d = make_violation_dict(severity="BLOCKER")  # não existe
        v = client._parse_single_violation(d)
        assert v.severity == "LOW"

    def test_missing_required_field_raises(self):
        client = make_llm_client()
        d = make_violation_dict()
        del d["line_content"]
        with pytest.raises(KeyError):
            client._parse_single_violation(d)


# ══════════════════════════════════════════════════════════════════════════════
# Testes: LLMClient — _parse_response
# ══════════════════════════════════════════════════════════════════════════════


class TestParseResponse:
    def test_returns_violations_from_json(self):
        client = make_llm_client()
        raw = make_llm_response([make_violation_dict()])
        violations = client._parse_response(raw)
        assert len(violations) == 1
        assert isinstance(violations[0], Violation)

    def test_empty_violations_returns_empty_list(self):
        client = make_llm_client()
        raw = json.dumps({"violations": []})
        violations = client._parse_response(raw)
        assert violations == []

    def test_multiple_violations_parsed(self):
        client = make_llm_client()
        raw = make_llm_response(
            [
                make_violation_dict(line_content="line1"),
                make_violation_dict(line_content="line2"),
            ]
        )
        violations = client._parse_response(raw)
        assert len(violations) == 2

    def test_invalid_violation_entry_is_skipped(self):
        client = make_llm_client()
        bad = {"wrong_key": "no required fields"}
        raw = json.dumps({"violations": [make_violation_dict(), bad]})
        violations = client._parse_response(raw)
        # O inválido deve ser ignorado, o válido deve ser parseado
        assert len(violations) == 1

    def test_missing_violations_key_returns_empty(self):
        client = make_llm_client()
        raw = json.dumps({"other_key": "value"})
        violations = client._parse_response(raw)
        assert violations == []


# ══════════════════════════════════════════════════════════════════════════════
# Testes: LLMClient — review (integração mockada)
# ══════════════════════════════════════════════════════════════════════════════


class TestLLMClientReview:
    def _mock_api_response(self, text: str) -> MagicMock:
        message = MagicMock()
        message.content = text
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        return response

    def test_review_returns_violations(self):
        client = make_llm_client()
        mock_api = MagicMock()
        mock_api.chat.completions.create.return_value = self._mock_api_response(
            make_llm_response([make_violation_dict()])
        )
        client._client = mock_api

        ctx = make_context()
        violations = client.review(ctx)
        assert len(violations) == 1
        assert isinstance(violations[0], Violation)

    def test_review_calls_api_with_model(self):
        client = make_llm_client()
        mock_api = MagicMock()
        mock_api.chat.completions.create.return_value = self._mock_api_response(
            json.dumps({"violations": []})
        )
        client._client = mock_api

        ctx = make_context()
        client.review(ctx)

        call_kwargs = mock_api.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "groq-test"

    def test_review_raises_when_no_api_key(self):
        client = make_llm_client(api_key="")
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            client.review(make_context())

    def test_review_returns_empty_for_no_violations(self):
        client = make_llm_client()
        mock_api = MagicMock()
        mock_api.chat.completions.create.return_value = self._mock_api_response(
            json.dumps({"violations": []})
        )
        client._client = mock_api

        violations = client.review(make_context())
        assert violations == []


# ══════════════════════════════════════════════════════════════════════════════
# Testes: RAGReviewer — _build_summary
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildSummary:
    def _make_violation(self, severity: str) -> Violation:
        return Violation(
            line_content="x",
            violation_description="desc",
            norm_reference="doc",
            severity=severity,
            suggestion="fix",
        )

    def test_no_violations(self):
        assert RAGReviewer._build_summary([]) == "nenhuma violação detectada"

    def test_single_violation(self):
        fd = make_file_diff()
        v = self._make_violation("HIGH")
        result = RAGReviewer._build_summary([(fd, v)])
        assert "1" in result
        assert "HIGH" in result

    def test_multiple_severities(self):
        fd = make_file_diff()
        violations = [
            (fd, self._make_violation("CRITICAL")),
            (fd, self._make_violation("HIGH")),
            (fd, self._make_violation("HIGH")),
            (fd, self._make_violation("LOW")),
        ]
        result = RAGReviewer._build_summary(violations)
        assert "4" in result
        assert "CRITICAL" in result
        assert "HIGH" in result
        assert "LOW" in result


# ══════════════════════════════════════════════════════════════════════════════
# Testes: RAGReviewer — review_context
# ══════════════════════════════════════════════════════════════════════════════


class TestRAGReviewerReviewContext:
    def test_delegates_to_llm(self):
        mock_llm = MagicMock()
        mock_llm.review.return_value = []
        reviewer = RAGReviewer(
            collector=MagicMock(),
            retriever=MagicMock(),
            llm=mock_llm,
        )
        ctx = make_context()
        reviewer.review_context(ctx)
        mock_llm.review.assert_called_once_with(ctx)

    def test_returns_violations_from_llm(self):
        v = Violation("x", "d", "ref", "HIGH", "fix")
        mock_llm = MagicMock()
        mock_llm.review.return_value = [v]
        reviewer = RAGReviewer(
            collector=MagicMock(),
            retriever=MagicMock(),
            llm=mock_llm,
        )
        result = reviewer.review_context(make_context())
        assert result == [v]


# ══════════════════════════════════════════════════════════════════════════════
# Testes: RAGReviewer — run (integração mockada)
# ══════════════════════════════════════════════════════════════════════════════


class TestRAGReviewerRun:
    def _make_pr_diff(self, files=None):
        from rag_reviewer.diff_parser import PullRequestDiff

        if files is None:
            files = [make_file_diff()]
        return PullRequestDiff(
            pr_number=1,
            repo="org/repo",
            files=files,
            total_additions=1,
            total_deletions=0,
        )

    def _make_reviewer(
        self,
        pr_files=None,
        contexts=None,
        violations_per_context=None,
    ) -> tuple[RAGReviewer, MagicMock]:
        mock_collector = MagicMock()
        mock_collector.collect.return_value = self._make_pr_diff(pr_files)

        mock_retriever = MagicMock()
        mock_retriever.retrieve_for_diff.return_value = (
            contexts if contexts is not None else [make_context()]
        )

        v = Violation("x", "d", "ref", "HIGH", "fix")
        mock_llm = MagicMock()
        mock_llm.review.return_value = (
            violations_per_context if violations_per_context is not None else [v]
        )

        mock_publisher = MagicMock()

        reviewer = RAGReviewer(
            collector=mock_collector,
            retriever=mock_retriever,
            llm=mock_llm,
            publisher=mock_publisher,
        )
        return reviewer, mock_publisher

    def test_run_returns_violations(self):
        reviewer, _ = self._make_reviewer()
        result = reviewer.run()
        assert len(result) == 1

    def test_run_calls_publisher_publish(self):
        reviewer, publisher = self._make_reviewer()
        reviewer.run()
        publisher.publish.assert_called_once()

    def test_run_calls_llm_for_each_context(self):
        contexts = [make_context("a.py"), make_context("b.py")]
        reviewer, _ = self._make_reviewer(contexts=contexts)
        reviewer._llm.review.return_value = []
        reviewer.run()
        assert reviewer._llm.review.call_count == len(contexts)
        reviewer._llm.review.assert_has_calls([call(contexts[0]), call(contexts[1])])

    def test_run_returns_empty_when_no_files(self):
        reviewer, publisher = self._make_reviewer(pr_files=[])
        result = reviewer.run()
        assert result == []

    def test_run_returns_empty_when_no_contexts(self):
        reviewer, publisher = self._make_reviewer(contexts=[])
        result = reviewer.run()
        assert result == []

    def test_run_calls_request_changes_for_critical(self):

        v_critical = Violation("x", "d", "ref", "CRITICAL", "fix")

        mock_collector = MagicMock()
        mock_collector.collect.return_value = self._make_pr_diff()
        mock_retriever = MagicMock()
        mock_retriever.retrieve_for_diff.return_value = [make_context()]
        mock_llm = MagicMock()
        mock_llm.review.return_value = [v_critical]
        mock_publisher = MagicMock()

        # Garante que BLOCK_ON_CRITICAL=True
        with patch("rag_reviewer.reviewer.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(block_on_critical=True)
            reviewer = RAGReviewer(
                collector=mock_collector,
                retriever=mock_retriever,
                llm=mock_llm,
                publisher=mock_publisher,
            )
            reviewer.run()

        mock_publisher.request_changes.assert_called_once()
        call_arg = mock_publisher.request_changes.call_args[0][0]
        assert "CRÍTICA" in call_arg or "crítica" in call_arg.lower() or "1" in call_arg

    def test_run_does_not_request_changes_for_non_critical(self):
        v_high = Violation("x", "d", "ref", "HIGH", "fix")

        mock_collector = MagicMock()
        mock_collector.collect.return_value = self._make_pr_diff()
        mock_retriever = MagicMock()
        mock_retriever.retrieve_for_diff.return_value = [make_context()]
        mock_llm = MagicMock()
        mock_llm.review.return_value = [v_high]
        mock_publisher = MagicMock()

        with patch("rag_reviewer.reviewer.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(block_on_critical=True)
            reviewer = RAGReviewer(
                collector=mock_collector,
                retriever=mock_retriever,
                llm=mock_llm,
                publisher=mock_publisher,
            )
            reviewer.run()

        mock_publisher.request_changes.assert_not_called()
