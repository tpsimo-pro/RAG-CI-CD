"""Testes unitários para rag_reviewer/github_publisher.py.

Todos os testes são isolados via unittest.mock — sem chamadas reais à GitHub API.
"""

from __future__ import annotations

from typing import List, Tuple
from unittest.mock import MagicMock, patch, call

import pytest
import requests as req

from rag_reviewer.diff_parser import FileDiff, PullRequestDiff
from rag_reviewer.github_publisher import (
    GitHubPublisher,
    _build_summary_body,
    _count_by_severity,
    _find_diff_position,
    _format_inline_comment,
    _SEVERITY_EMOJI,
)
from rag_reviewer.llm_client import Violation


# ── Helpers de fixture ────────────────────────────────────────────────────────


def make_file_diff(
    filename: str = "src/app.py",
    patch: str = "@@ -1,3 +1,4 @@\n context\n+added line\n-removed",
    status: str = "modified",
    additions: int = 1,
) -> FileDiff:
    return FileDiff(
        filename=filename,
        patch=patch,
        status=status,
        additions=additions,
        deletions=0,
        added_lines=["added line"],
    )


def make_violation(
    line_content: str = "added line",
    description: str = "Viola norma X",
    norm_ref: str = "coding_standards.md § 3.2",
    severity: str = "HIGH",
    suggestion: str = "Corrija assim",
) -> Violation:
    return Violation(
        line_content=line_content,
        violation_description=description,
        norm_reference=norm_ref,
        severity=severity,
        suggestion=suggestion,
    )


def make_pr_diff(files: list | None = None) -> PullRequestDiff:
    return PullRequestDiff(
        pr_number=42,
        repo="org/repo",
        files=files or [make_file_diff()],
        total_additions=1,
        total_deletions=0,
    )


def make_publisher(
    token: str = "gh-token",
    repo: str = "org/repo",
    pr_number: int = 42,
    head_sha: str = "abc123",
) -> GitHubPublisher:
    return GitHubPublisher(
        token=token,
        repo=repo,
        pr_number=pr_number,
        head_sha=head_sha,
    )


def make_violations(n: int = 1, severity: str = "HIGH") -> List[Tuple[FileDiff, Violation]]:
    fd = make_file_diff()
    return [(fd, make_violation(severity=severity)) for _ in range(n)]


# ══════════════════════════════════════════════════════════════════════════════
# Testes: _find_diff_position
# ══════════════════════════════════════════════════════════════════════════════


class TestFindDiffPosition:
    def test_finds_added_line(self):
        patch = "@@ -1,2 +1,3 @@\n context\n+added line\n-removed"
        pos = _find_diff_position(patch, "added line")
        assert pos is not None
        assert pos > 0

    def test_returns_none_for_missing_content(self):
        patch = "@@ -1,2 +1,2 @@\n context\n+other line"
        pos = _find_diff_position(patch, "this line does not exist")
        assert pos is None

    def test_returns_none_for_empty_patch(self):
        assert _find_diff_position("", "anything") is None

    def test_returns_none_for_empty_line_content(self):
        patch = "@@ -1 +1,2 @@\n+added"
        assert _find_diff_position(patch, "") is None

    def test_does_not_match_removed_lines(self):
        patch = "@@ -1,2 +1,1 @@\n context\n-removed line"
        pos = _find_diff_position(patch, "removed line")
        assert pos is None

    def test_does_not_match_context_lines(self):
        patch = "@@ -1,2 +1,2 @@\n context only\n+added"
        pos = _find_diff_position(patch, "context only")
        assert pos is None

    def test_hunk_header_increments_position(self):
        """O cabeçalho @@ conta como posição 1."""
        patch = "@@ -1 +1,2 @@\n+first added"
        pos = _find_diff_position(patch, "first added")
        assert pos == 2  # @@ = 1, +first = 2

    def test_position_counts_context_lines(self):
        """Linhas de contexto incrementam a posição."""
        patch = "@@ -1,3 +1,4 @@\n ctx1\n ctx2\n+target line\n ctx3"
        pos = _find_diff_position(patch, "target line")
        assert pos == 4  # @@ = 1, ctx1 = 2, ctx2 = 3, +target = 4

    def test_partial_match_is_found(self):
        """Busca por substring — não precisa ser linha completa."""
        patch = "@@ -1 +1,2 @@\n+    def my_function(self):"
        pos = _find_diff_position(patch, "my_function")
        assert pos is not None

    def test_whitespace_stripped_before_comparison(self):
        """Espaços extras no line_content não devem impedir o match."""
        patch = "@@ -1 +1,2 @@\n+    indented = True"
        pos = _find_diff_position(patch, "  indented = True  ")
        assert pos is not None

    def test_multiple_hunks_correct_position(self):
        """Em múltiplos hunks, a posição é contínua."""
        patch = (
            "@@ -1,2 +1,2 @@\n ctx\n+hunk1 line\n"
            "@@ -10,2 +10,2 @@\n ctx2\n+hunk2 line"
        )
        pos1 = _find_diff_position(patch, "hunk1 line")
        pos2 = _find_diff_position(patch, "hunk2 line")
        assert pos1 is not None
        assert pos2 is not None
        assert pos2 > pos1  # segunda ocorrência tem posição maior


# ══════════════════════════════════════════════════════════════════════════════
# Testes: _format_inline_comment
# ══════════════════════════════════════════════════════════════════════════════


class TestFormatInlineComment:
    def test_includes_severity(self):
        v = make_violation(severity="HIGH")
        result = _format_inline_comment(v)
        assert "HIGH" in result

    def test_includes_description(self):
        v = make_violation(description="Nome muito curto")
        result = _format_inline_comment(v)
        assert "Nome muito curto" in result

    def test_includes_norm_reference(self):
        v = make_violation(norm_ref="clean_code.md § 2.1")
        result = _format_inline_comment(v)
        assert "clean_code.md § 2.1" in result

    def test_includes_suggestion(self):
        v = make_violation(suggestion="Use nome descritivo")
        result = _format_inline_comment(v)
        assert "Use nome descritivo" in result

    @pytest.mark.parametrize("severity,emoji", [
        ("CRITICAL", "⛔"),
        ("HIGH", "🔴"),
        ("MEDIUM", "🟡"),
        ("LOW", "🔵"),
    ])
    def test_correct_emoji_per_severity(self, severity: str, emoji: str):
        v = make_violation(severity=severity)
        result = _format_inline_comment(v)
        assert emoji in result

    def test_unknown_severity_uses_fallback_emoji(self):
        v = make_violation(severity="UNKNOWN")
        result = _format_inline_comment(v)
        assert "ℹ️" in result

    def test_markdown_bold_formatting(self):
        v = make_violation()
        result = _format_inline_comment(v)
        assert "**" in result


# ══════════════════════════════════════════════════════════════════════════════
# Testes: _count_by_severity
# ══════════════════════════════════════════════════════════════════════════════


class TestCountBySeverity:
    def test_single_violation(self):
        fd = make_file_diff()
        violations = [(fd, make_violation(severity="HIGH"))]
        counts = _count_by_severity(violations)
        assert counts == {"HIGH": 1}

    def test_multiple_same_severity(self):
        fd = make_file_diff()
        violations = [(fd, make_violation(severity="LOW"))] * 3
        counts = _count_by_severity(violations)
        assert counts == {"LOW": 3}

    def test_mixed_severities(self):
        fd = make_file_diff()
        violations = [
            (fd, make_violation(severity="CRITICAL")),
            (fd, make_violation(severity="HIGH")),
            (fd, make_violation(severity="HIGH")),
            (fd, make_violation(severity="LOW")),
        ]
        counts = _count_by_severity(violations)
        assert counts["CRITICAL"] == 1
        assert counts["HIGH"] == 2
        assert counts["LOW"] == 1

    def test_empty_violations(self):
        assert _count_by_severity([]) == {}


# ══════════════════════════════════════════════════════════════════════════════
# Testes: _build_summary_body
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildSummaryBody:
    def test_includes_total(self):
        body = _build_summary_body(3, {"HIGH": 2, "LOW": 1})
        assert "3" in body

    def test_includes_severity_in_table(self):
        body = _build_summary_body(2, {"HIGH": 2})
        assert "HIGH" in body

    def test_zero_count_severities_omitted(self):
        body = _build_summary_body(1, {"CRITICAL": 0, "HIGH": 1})
        # CRITICAL com 0 não deve aparecer como linha da tabela
        lines = [l for l in body.splitlines() if "CRITICAL" in l and "|" in l]
        assert len(lines) == 0

    def test_includes_markdown_table_headers(self):
        body = _build_summary_body(1, {"HIGH": 1})
        assert "Severidade" in body
        assert "Quantidade" in body

    def test_includes_rastreability_footer(self):
        body = _build_summary_body(1, {"HIGH": 1})
        assert "RAG-Reviewer" in body

    def test_severity_order_critical_first(self):
        body = _build_summary_body(3, {"LOW": 1, "CRITICAL": 1, "HIGH": 1})
        pos_critical = body.find("CRITICAL")
        pos_high = body.find("HIGH")
        pos_low = body.find("LOW")
        assert pos_critical < pos_high < pos_low


# ══════════════════════════════════════════════════════════════════════════════
# Testes: GitHubPublisher.__init__
# ══════════════════════════════════════════════════════════════════════════════


class TestGitHubPublisherInit:
    def test_explicit_params_stored(self):
        p = make_publisher(token="t", repo="o/r", pr_number=7, head_sha="sha1")
        assert p._token == "t"
        assert p._repo == "o/r"
        assert p._pr_number == 7
        assert p._head_sha == "sha1"

    def test_headers_include_token(self):
        p = make_publisher(token="mytoken")
        assert p._headers["Authorization"] == "Bearer mytoken"

    def test_headers_include_api_version(self):
        p = make_publisher()
        assert p._headers["X-GitHub-Api-Version"] == "2022-11-28"

    def test_headers_include_accept(self):
        p = make_publisher()
        assert "application/vnd.github+json" in p._headers["Accept"]


# ══════════════════════════════════════════════════════════════════════════════
# Testes: GitHubPublisher.post_summary
# ══════════════════════════════════════════════════════════════════════════════


class TestPostSummary:
    def test_calls_issues_endpoint(self):
        p = make_publisher(repo="org/repo", pr_number=42)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp) as mock_post:
            p.post_summary("✅ OK")
        url = mock_post.call_args.args[0]
        assert "/issues/42/comments" in url
        assert "org/repo" in url

    def test_sends_message_body(self):
        p = make_publisher()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp) as mock_post:
            p.post_summary("My message")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["body"] == "My message"

    def test_raises_on_http_error(self):
        p = make_publisher()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("403")
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(req.HTTPError):
                p.post_summary("msg")


# ══════════════════════════════════════════════════════════════════════════════
# Testes: GitHubPublisher.request_changes
# ══════════════════════════════════════════════════════════════════════════════


class TestRequestChanges:
    def test_calls_reviews_endpoint(self):
        p = make_publisher(repo="org/repo", pr_number=42)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp) as mock_post:
            p.request_changes("Fix required")
        url = mock_post.call_args.args[0]
        assert "/pulls/42/reviews" in url

    def test_event_is_request_changes(self):
        p = make_publisher()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp) as mock_post:
            p.request_changes("msg")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["event"] == "REQUEST_CHANGES"

    def test_includes_message_in_body(self):
        p = make_publisher()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp) as mock_post:
            p.request_changes("Critical issue found")
        payload = mock_post.call_args.kwargs["json"]
        assert "Critical issue found" in payload["body"]

    def test_includes_head_sha(self):
        p = make_publisher(head_sha="deadbeef")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp) as mock_post:
            p.request_changes("msg")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["commit_id"] == "deadbeef"


# ══════════════════════════════════════════════════════════════════════════════
# Testes: GitHubPublisher.publish
# ══════════════════════════════════════════════════════════════════════════════


class TestPublish:
    def test_no_violations_calls_post_summary(self):
        p = make_publisher()
        pr = make_pr_diff()
        with patch.object(p, "post_summary") as mock_summary:
            with patch.object(p, "_create_review") as mock_review:
                p.publish([], pr)
        mock_summary.assert_called_once()
        mock_review.assert_not_called()

    def test_with_violations_calls_create_review(self):
        p = make_publisher()
        pr = make_pr_diff()
        violations = make_violations(1)
        with patch.object(p, "_create_review") as mock_review:
            p.publish(violations, pr)
        mock_review.assert_called_once()

    def test_with_violations_does_not_call_post_summary(self):
        p = make_publisher()
        pr = make_pr_diff()
        violations = make_violations(1)
        with patch.object(p, "post_summary") as mock_summary:
            with patch.object(p, "_create_review", return_value=None):
                p.publish(violations, pr)
        mock_summary.assert_not_called()

    def test_inline_comment_added_when_line_found(self):
        """Quando a linha da violação é encontrada no patch, deve gerar comentário inline."""
        patch_text = "@@ -1,2 +1,3 @@\n context\n+target line here\n-old"
        fd = make_file_diff(patch=patch_text)
        v = make_violation(line_content="target line here")
        pr = make_pr_diff(files=[fd])
        p = make_publisher()

        captured_comments = []

        def capture_create_review(comments, severity_counts):
            captured_comments.extend(comments)

        with patch.object(p, "_create_review", side_effect=capture_create_review):
            p.publish([(fd, v)], pr)

        assert len(captured_comments) == 1
        assert captured_comments[0]["path"] == fd.filename

    def test_no_inline_comment_when_line_not_found(self):
        """Quando a linha não é localizável no patch, não deve gerar comentário inline."""
        patch_text = "@@ -1,2 +1,3 @@\n context\n+different line\n-old"
        fd = make_file_diff(patch=patch_text)
        v = make_violation(line_content="completely unrelated content xyz")
        pr = make_pr_diff(files=[fd])
        p = make_publisher()

        captured_comments = []

        def capture_create_review(comments, severity_counts):
            captured_comments.extend(comments)

        with patch.object(p, "_create_review", side_effect=capture_create_review):
            p.publish([(fd, v)], pr)

        assert len(captured_comments) == 0

    def test_severity_counts_passed_to_create_review(self):
        fd = make_file_diff()
        violations = [
            (fd, make_violation(severity="HIGH")),
            (fd, make_violation(severity="LOW")),
        ]
        pr = make_pr_diff(files=[fd])
        p = make_publisher()

        captured_counts = {}

        def capture(comments, severity_counts):
            captured_counts.update(severity_counts)

        with patch.object(p, "_create_review", side_effect=capture):
            p.publish(violations, pr)

        assert captured_counts.get("HIGH") == 1
        assert captured_counts.get("LOW") == 1


# ══════════════════════════════════════════════════════════════════════════════
# Testes: GitHubPublisher._create_review
# ══════════════════════════════════════════════════════════════════════════════


class TestCreateReview:
    def test_calls_reviews_api_endpoint(self):
        p = make_publisher(repo="org/repo", pr_number=10)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp) as mock_post:
            p._create_review([], {"HIGH": 1})
        url = mock_post.call_args.args[0]
        assert "/pulls/10/reviews" in url
        assert "org/repo" in url

    def test_event_is_comment(self):
        p = make_publisher()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp) as mock_post:
            p._create_review([], {"HIGH": 1})
        payload = mock_post.call_args.kwargs["json"]
        assert payload["event"] == "COMMENT"

    def test_includes_commit_id(self):
        p = make_publisher(head_sha="cafebabe")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp) as mock_post:
            p._create_review([], {"HIGH": 1})
        payload = mock_post.call_args.kwargs["json"]
        assert payload["commit_id"] == "cafebabe"

    def test_inline_comments_included_in_payload(self):
        p = make_publisher()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        inline = [{"path": "f.py", "position": 2, "body": "comment"}]
        with patch("requests.post", return_value=mock_resp) as mock_post:
            p._create_review(inline, {"HIGH": 1})
        payload = mock_post.call_args.kwargs["json"]
        assert payload["comments"] == inline
