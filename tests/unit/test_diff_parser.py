"""Testes unitários para rag_reviewer/diff_parser.py.

Todos os testes são isolados: não há chamadas de rede reais.
A GitHub API é mockada via pytest-mock / unittest.mock.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from rag_reviewer.diff_parser import (
    DiffCollector,
    FileDiff,
    PullRequestDiff,
    _extract_added_lines,
    _is_ignored_file,
    build_query_text,
    _MAX_QUERY_CHARS,
    _IGNORED_EXTENSIONS,
)


# ── Helpers de fixture ────────────────────────────────────────────────────────


def make_file_diff(
    filename: str = "src/app.py",
    patch: str = "@@ -1,3 +1,4 @@\n context\n+added line\n-removed line",
    status: str = "modified",
    additions: int = 1,
    deletions: int = 1,
    added_lines: list | None = None,
) -> FileDiff:
    if added_lines is None:
        added_lines = ["added line"]
    return FileDiff(
        filename=filename,
        patch=patch,
        status=status,
        additions=additions,
        deletions=deletions,
        added_lines=added_lines,
    )


def make_raw_file(
    filename: str = "src/app.py",
    status: str = "modified",
    patch: str = "@@ -1 +1,2 @@\n context\n+new line",
    additions: int = 1,
    deletions: int = 0,
) -> dict:
    """Simula um objeto retornado pela GitHub API (GET /pulls/:pr/files)."""
    return {
        "filename": filename,
        "status": status,
        "patch": patch,
        "additions": additions,
        "deletions": deletions,
    }


# ── Testes: FileDiff dataclass ────────────────────────────────────────────────


class TestFileDiff:
    def test_defaults(self):
        fd = FileDiff(filename="f.py", patch="", status="modified")
        assert fd.additions == 0
        assert fd.deletions == 0
        assert fd.added_lines == []

    def test_added_lines_default_is_independent(self):
        """Garante que added_lines usa field(default_factory=list) — não compartilha lista."""
        fd1 = FileDiff(filename="a.py", patch="", status="added")
        fd2 = FileDiff(filename="b.py", patch="", status="added")
        fd1.added_lines.append("x")
        assert fd2.added_lines == []

    def test_all_fields_set(self):
        fd = make_file_diff()
        assert fd.filename == "src/app.py"
        assert fd.status == "modified"
        assert fd.additions == 1
        assert fd.deletions == 1
        assert fd.added_lines == ["added line"]


# ── Testes: PullRequestDiff dataclass ────────────────────────────────────────


class TestPullRequestDiff:
    def test_basic_construction(self):
        fd = make_file_diff()
        pr = PullRequestDiff(
            pr_number=42,
            repo="org/repo",
            files=[fd],
            total_additions=1,
            total_deletions=1,
        )
        assert pr.pr_number == 42
        assert pr.repo == "org/repo"
        assert len(pr.files) == 1

    def test_empty_files(self):
        pr = PullRequestDiff(
            pr_number=1,
            repo="org/repo",
            files=[],
            total_additions=0,
            total_deletions=0,
        )
        assert pr.files == []
        assert pr.total_additions == 0


# ── Testes: _extract_added_lines ─────────────────────────────────────────────


class TestExtractAddedLines:
    def test_extracts_added_lines(self):
        patch = "@@ -1,3 +1,4 @@\n context\n+added line\n-removed line\n+another added"
        lines = _extract_added_lines(patch)
        assert lines == ["added line", "another added"]

    def test_ignores_context_lines(self):
        patch = "@@ -1,2 +1,2 @@\n context line\n+added"
        lines = _extract_added_lines(patch)
        assert lines == ["added"]

    def test_ignores_removed_lines(self):
        patch = "@@ -1,2 +1,1 @@\n context\n-removed line"
        lines = _extract_added_lines(patch)
        assert lines == []

    def test_ignores_hunk_header_plus_plus_plus(self):
        patch = "+++ b/src/app.py\n@@ -0,0 +1 @@\n+new file content"
        lines = _extract_added_lines(patch)
        assert lines == ["new file content"]

    def test_empty_patch_returns_empty_list(self):
        assert _extract_added_lines("") == []

    def test_prefix_plus_is_removed(self):
        patch = "@@ -1 +1,2 @@\n context\n+    indented code"
        lines = _extract_added_lines(patch)
        assert lines == ["    indented code"]

    def test_multiple_hunks(self):
        patch = (
            "@@ -1,3 +1,4 @@\n ctx\n+line1\n-old\n"
            "@@ -10,2 +11,3 @@\n ctx2\n+line2"
        )
        lines = _extract_added_lines(patch)
        assert lines == ["line1", "line2"]

    def test_blank_added_line_is_included(self):
        """Linha em branco adicionada ('+' sozinho) deve ser incluída."""
        patch = "@@ -1 +1,2 @@\n context\n+"
        lines = _extract_added_lines(patch)
        assert lines == [""]


# ── Testes: _is_ignored_file ──────────────────────────────────────────────────


class TestIsIgnoredFile:
    @pytest.mark.parametrize(
        "filename",
        [
            "image.png",
            "logo.JPG",
            "animation.gif",
            "icon.svg",
            "favicon.ico",
            "photo.webp",
            "document.pdf",
            "archive.zip",
            "backup.tar",
            "data.gz",
            "package.whl",
            "program.exe",
            "library.dll",
            "poetry.lock",
            "go.sum",
        ],
    )
    def test_ignored_extensions(self, filename: str):
        assert _is_ignored_file(filename) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "src/app.py",
            "lib/utils.js",
            "components/Header.tsx",
            "Main.java",
            "README.md",
            "config.yaml",
            "Dockerfile",
            "src/app.go",
        ],
    )
    def test_non_ignored_extensions(self, filename: str):
        assert _is_ignored_file(filename) is False

    def test_case_insensitive_extension(self):
        assert _is_ignored_file("IMAGE.PNG") is True

    def test_file_without_extension(self):
        assert _is_ignored_file("Makefile") is False

    def test_hidden_file_with_ignored_extension(self):
        assert _is_ignored_file(".hidden.png") is True


# ── Testes: build_query_text ──────────────────────────────────────────────────


class TestBuildQueryText:
    def test_includes_filename_as_header(self):
        fd = make_file_diff(filename="src/service.py", added_lines=["x = 1"])
        result = build_query_text(fd)
        assert result.startswith("Arquivo: src/service.py\n")

    def test_includes_added_lines(self):
        fd = make_file_diff(added_lines=["def foo():", "    return 42"])
        result = build_query_text(fd)
        assert "def foo():" in result
        assert "    return 42" in result

    def test_empty_added_lines_returns_header_only(self):
        fd = make_file_diff(added_lines=[])
        result = build_query_text(fd)
        assert result == "Arquivo: src/app.py\n"

    def test_long_diff_is_truncated(self):
        long_line = "x" * 3000
        fd = make_file_diff(added_lines=[long_line])
        result = build_query_text(fd, max_chars=100)
        assert len(result) <= 100
        assert result.endswith("[TRUNCADO]")

    def test_short_diff_is_not_truncated(self):
        fd = make_file_diff(added_lines=["short line"])
        result = build_query_text(fd)
        assert "[TRUNCADO]" not in result

    def test_exact_max_chars_not_truncated(self):
        """Texto com exatamente max_chars não deve ser truncado."""
        fd = make_file_diff(filename="f.py", added_lines=[])
        # "Arquivo: f.py\n" = 14 chars
        header_len = len(f"Arquivo: {fd.filename}\n")
        result = build_query_text(fd, max_chars=header_len)
        assert "[TRUNCADO]" not in result
        assert len(result) == header_len

    def test_default_max_chars(self):
        """Verifica que o limite padrão é _MAX_QUERY_CHARS."""
        fd = make_file_diff(added_lines=["a" * (_MAX_QUERY_CHARS + 1)])
        result = build_query_text(fd)
        assert len(result) <= _MAX_QUERY_CHARS

    def test_lines_joined_with_newline(self):
        fd = make_file_diff(added_lines=["line1", "line2", "line3"])
        result = build_query_text(fd)
        assert "line1\nline2\nline3" in result


# ── Testes: DiffCollector.__init__ ───────────────────────────────────────────


class TestDiffCollectorInit:
    def test_explicit_params_override_settings(self):
        collector = DiffCollector(token="tk", repo="org/repo", pr_number=7)
        assert collector._token == "tk"
        assert collector._repo == "org/repo"
        assert collector._pr_number == 7

    def test_headers_include_auth_token(self):
        collector = DiffCollector(token="mytoken", repo="org/r", pr_number=1)
        assert "Authorization" in collector._headers
        assert collector._headers["Authorization"] == "Bearer mytoken"

    def test_headers_include_github_api_version(self):
        collector = DiffCollector(token="t", repo="o/r", pr_number=1)
        assert collector._headers["X-GitHub-Api-Version"] == "2022-11-28"

    def test_headers_include_accept_json(self):
        collector = DiffCollector(token="t", repo="o/r", pr_number=1)
        assert "application/vnd.github+json" in collector._headers["Accept"]


# ── Testes: DiffCollector._validate_config ───────────────────────────────────


class TestDiffCollectorValidateConfig:
    def test_raises_when_token_missing(self):
        collector = DiffCollector(token="", repo="org/repo", pr_number=1)
        with pytest.raises(ValueError, match="GITHUB_TOKEN"):
            collector._validate_config()

    def test_raises_when_repo_missing(self):
        collector = DiffCollector(token="tk", repo="", pr_number=1)
        with pytest.raises(ValueError, match="REPO_FULL_NAME"):
            collector._validate_config()

    def test_raises_when_pr_number_missing(self):
        collector = DiffCollector(token="tk", repo="org/repo", pr_number=0)
        with pytest.raises(ValueError, match="PR_NUMBER"):
            collector._validate_config()

    def test_passes_with_valid_config(self):
        collector = DiffCollector(token="tk", repo="org/repo", pr_number=1)
        collector._validate_config()  # não deve levantar exceção


# ── Testes: DiffCollector._parse_files ───────────────────────────────────────


class TestDiffCollectorParseFiles:
    def setup_method(self):
        self.collector = DiffCollector(token="tk", repo="org/repo", pr_number=1)

    def test_parses_single_file(self):
        raw = [make_raw_file(filename="app.py", additions=1, deletions=0)]
        files = self.collector._parse_files(raw)
        assert len(files) == 1
        assert files[0].filename == "app.py"

    def test_skips_deleted_files(self):
        raw = [make_raw_file(status="deleted")]
        files = self.collector._parse_files(raw)
        assert files == []

    def test_skips_ignored_extensions(self):
        raw = [make_raw_file(filename="image.png")]
        files = self.collector._parse_files(raw)
        assert files == []

    def test_skips_files_without_patch(self):
        raw = [make_raw_file(patch="")]
        files = self.collector._parse_files(raw)
        assert files == []

    def test_preserves_additions_and_deletions(self):
        raw = [make_raw_file(additions=5, deletions=3)]
        files = self.collector._parse_files(raw)
        assert files[0].additions == 5
        assert files[0].deletions == 3

    def test_extracts_added_lines_from_patch(self):
        patch = "@@ -1,2 +1,3 @@\n context\n+added line\n-removed"
        raw = [make_raw_file(patch=patch)]
        files = self.collector._parse_files(raw)
        assert files[0].added_lines == ["added line"]

    def test_parses_multiple_files(self):
        raw = [
            make_raw_file(filename="a.py", patch="@@ -1 +1 @@\n+line a"),
            make_raw_file(filename="b.js", patch="@@ -1 +1 @@\n+line b"),
        ]
        files = self.collector._parse_files(raw)
        assert len(files) == 2
        filenames = {f.filename for f in files}
        assert "a.py" in filenames
        assert "b.js" in filenames

    def test_empty_raw_list_returns_empty(self):
        files = self.collector._parse_files([])
        assert files == []

    def test_renamed_file_with_patch_is_included(self):
        raw = [make_raw_file(status="renamed", patch="@@ -1 +1 @@\n+changed")]
        files = self.collector._parse_files(raw)
        assert len(files) == 1
        assert files[0].status == "renamed"

    def test_added_file_is_included(self):
        raw = [make_raw_file(status="added", patch="@@ -0,0 +1 @@\n+new file")]
        files = self.collector._parse_files(raw)
        assert len(files) == 1


# ── Testes: DiffCollector._paginate ──────────────────────────────────────────


class TestDiffCollectorPaginate:
    def setup_method(self):
        self.collector = DiffCollector(token="tk", repo="org/repo", pr_number=1)

    def test_single_page(self):
        mock_response = MagicMock()
        mock_response.json.return_value = [{"id": 1}, {"id": 2}]
        mock_response.links = {}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            result = self.collector._paginate("https://api.github.com/test")

        assert result == [{"id": 1}, {"id": 2}]
        mock_get.assert_called_once()

    def test_multiple_pages(self):
        page1 = MagicMock()
        page1.json.return_value = [{"id": 1}]
        page1.links = {"next": {"url": "https://api.github.com/test?page=2"}}
        page1.raise_for_status = MagicMock()

        page2 = MagicMock()
        page2.json.return_value = [{"id": 2}]
        page2.links = {}
        page2.raise_for_status = MagicMock()

        with patch("requests.get", side_effect=[page1, page2]) as mock_get:
            result = self.collector._paginate("https://api.github.com/test")

        assert result == [{"id": 1}, {"id": 2}]
        assert mock_get.call_count == 2

    def test_http_error_propagates(self):
        import requests as req

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = req.HTTPError("404 Not Found")

        with patch("requests.get", return_value=mock_response):
            with pytest.raises(req.HTTPError):
                self.collector._paginate("https://api.github.com/bad")


# ── Testes: DiffCollector.collect (integração mockada) ───────────────────────


class TestDiffCollectorCollect:
    def _make_collector(self) -> DiffCollector:
        return DiffCollector(token="tk", repo="org/repo", pr_number=42)

    def test_collect_returns_pr_diff(self):
        collector = self._make_collector()
        raw_files = [
            make_raw_file(filename="app.py", additions=2, deletions=1),
        ]
        with patch.object(collector, "_paginate", return_value=raw_files):
            result = collector.collect()

        assert isinstance(result, PullRequestDiff)
        assert result.pr_number == 42
        assert result.repo == "org/repo"

    def test_collect_computes_total_additions(self):
        collector = self._make_collector()
        raw_files = [
            make_raw_file(filename="a.py", additions=3, patch="@@ @@\n+a\n+b\n+c"),
            make_raw_file(filename="b.py", additions=2, patch="@@ @@\n+x\n+y"),
        ]
        with patch.object(collector, "_paginate", return_value=raw_files):
            result = collector.collect()

        assert result.total_additions == 5

    def test_collect_computes_total_deletions(self):
        collector = self._make_collector()
        raw_files = [
            make_raw_file(filename="a.py", deletions=4, patch="@@ @@\n+keep"),
        ]
        with patch.object(collector, "_paginate", return_value=raw_files):
            result = collector.collect()

        assert result.total_deletions == 4

    def test_collect_raises_when_config_invalid(self):
        """_validate_config deve levantar ValueError antes de qualquer chamada HTTP."""
        collector = DiffCollector(token="", repo="org/repo", pr_number=1)
        with pytest.raises(ValueError, match="GITHUB_TOKEN"):
            collector._validate_config()

    def test_collect_excludes_deleted_files(self):
        collector = self._make_collector()
        raw_files = [
            make_raw_file(filename="deleted.py", status="deleted"),
            make_raw_file(filename="modified.py", status="modified"),
        ]
        with patch.object(collector, "_paginate", return_value=raw_files):
            result = collector.collect()

        filenames = [f.filename for f in result.files]
        assert "deleted.py" not in filenames
        assert "modified.py" in filenames

    def test_collect_excludes_binary_files(self):
        collector = self._make_collector()
        raw_files = [
            make_raw_file(filename="logo.png", status="added"),
            make_raw_file(filename="app.py", status="modified"),
        ]
        with patch.object(collector, "_paginate", return_value=raw_files):
            result = collector.collect()

        filenames = [f.filename for f in result.files]
        assert "logo.png" not in filenames
        assert "app.py" in filenames

    def test_collect_with_no_relevant_files(self):
        collector = self._make_collector()
        raw_files = [
            make_raw_file(filename="image.png", status="added"),
            make_raw_file(filename="deleted.py", status="deleted"),
        ]
        with patch.object(collector, "_paginate", return_value=raw_files):
            result = collector.collect()

        assert result.files == []
        assert result.total_additions == 0
        assert result.total_deletions == 0
