"""Testes unitários para rag_reviewer/retriever.py.

Todos os testes são isolados via unittest.mock — sem chamadas reais
ao Qdrant nem ao modelo de embedding.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from rag_reviewer.diff_parser import FileDiff, PullRequestDiff
from rag_reviewer.retriever import RetrievedContext, Retriever

# ── Helpers de fixture ────────────────────────────────────────────────────────


def make_file_diff(
    filename: str = "src/app.py",
    added_lines: list | None = None,
    status: str = "modified",
) -> FileDiff:
    if added_lines is None:
        added_lines = ["def foo():", "    return 42"]
    return FileDiff(
        filename=filename,
        patch="",
        status=status,
        additions=len(added_lines),
        deletions=0,
        added_lines=added_lines,
    )


def make_pr_diff(files: list | None = None) -> PullRequestDiff:
    if files is None:
        files = [make_file_diff()]
    return PullRequestDiff(
        pr_number=1,
        repo="org/repo",
        files=files,
        total_additions=sum(f.additions for f in files),
        total_deletions=0,
    )


def make_chunk(
    text: str = "Funções devem ter um único propósito.",
    source: str = "coding_standards.md",
    section: str = "3.2 Funções",
    score: float = 0.82,
) -> dict:
    return {
        "text": text,
        "source": source,
        "section": section,
        "page": 0,
        "score": score,
    }


def make_embedder_mock(vector_size: int = 4) -> MagicMock:
    """Cria um mock do Embedder que retorna vetores numpy determinísticos."""
    mock = MagicMock()
    mock.embed.return_value = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)
    return mock


def make_store_mock(chunks: list | None = None) -> MagicMock:
    """Cria um mock do VectorStore que retorna chunks predefinidos."""
    mock = MagicMock()
    mock.search.return_value = chunks if chunks is not None else [make_chunk()]
    return mock


def make_retriever(
    chunks: list | None = None,
    top_k: int = 3,
    score_threshold: float = 0.55,
) -> tuple[Retriever, MagicMock, MagicMock]:
    """Retorna (retriever, embedder_mock, store_mock) prontos para testes."""
    embedder = make_embedder_mock()
    store = make_store_mock(chunks)
    retriever = Retriever(
        embedder=embedder,
        store=store,
        top_k=top_k,
        score_threshold=score_threshold,
    )
    return retriever, embedder, store


# ── Testes: RetrievedContext dataclass ───────────────────────────────────────


class TestRetrievedContext:
    def test_construction(self):
        fd = make_file_diff()
        chunks = [make_chunk()]
        ctx = RetrievedContext(file_diff=fd, chunks=chunks, query_text="query")
        assert ctx.file_diff is fd
        assert ctx.chunks == chunks
        assert ctx.query_text == "query"

    def test_empty_chunks_allowed(self):
        fd = make_file_diff()
        ctx = RetrievedContext(file_diff=fd, chunks=[], query_text="q")
        assert ctx.chunks == []


# ── Testes: Retriever.__init__ ────────────────────────────────────────────────


class TestRetrieverInit:
    def test_explicit_params_are_stored(self):
        embedder = make_embedder_mock()
        store = make_store_mock()
        r = Retriever(embedder=embedder, store=store, top_k=7, score_threshold=0.7)
        assert r.top_k == 7
        assert r.score_threshold == 0.7

    def test_top_k_from_settings_when_not_provided(self):
        """Quando top_k não é fornecido, deve vir de get_settings()."""
        embedder = make_embedder_mock()
        store = make_store_mock()
        # O .env / settings padrão define TOP_K_CHUNKS=5
        r = Retriever(embedder=embedder, store=store)
        assert r.top_k >= 1  # Deve ter um valor válido

    def test_score_threshold_from_settings_when_not_provided(self):
        embedder = make_embedder_mock()
        store = make_store_mock()
        r = Retriever(embedder=embedder, store=store)
        assert 0.0 <= r.score_threshold <= 1.0

    def test_properties_are_readonly_values(self):
        r, _, _ = make_retriever(top_k=4, score_threshold=0.6)
        assert r.top_k == 4
        assert r.score_threshold == 0.6


# ── Testes: _filter_candidates ────────────────────────────────────────────────


class TestFilterCandidates:
    def test_file_with_added_lines_is_included(self):
        r, _, _ = make_retriever()
        fd = make_file_diff(added_lines=["x = 1"])
        result = r._filter_candidates([fd])
        assert fd in result

    def test_file_without_added_lines_is_excluded(self):
        r, _, _ = make_retriever()
        fd = make_file_diff(added_lines=[])
        result = r._filter_candidates([fd])
        assert result == []

    def test_mixed_files(self):
        r, _, _ = make_retriever()
        fd_with = make_file_diff(filename="a.py", added_lines=["x"])
        fd_without = make_file_diff(filename="b.py", added_lines=[])
        result = r._filter_candidates([fd_with, fd_without])
        assert fd_with in result
        assert fd_without not in result

    def test_empty_list_returns_empty(self):
        r, _, _ = make_retriever()
        assert r._filter_candidates([]) == []


# ── Testes: retrieve_for_file ─────────────────────────────────────────────────


class TestRetrieveForFile:
    def test_returns_retrieved_context_with_chunks(self):
        chunks = [make_chunk(score=0.9)]
        r, embedder, store = make_retriever(chunks=chunks)
        fd = make_file_diff()
        ctx = r.retrieve_for_file(fd)
        assert ctx is not None
        assert ctx.file_diff is fd
        assert ctx.chunks == chunks

    def test_returns_none_when_no_chunks_found(self):
        r, _, _ = make_retriever(chunks=[])
        fd = make_file_diff()
        ctx = r.retrieve_for_file(fd)
        assert ctx is None

    def test_query_text_is_stored_in_context(self):
        r, _, _ = make_retriever()
        fd = make_file_diff(filename="src/svc.py", added_lines=["x = 1"])
        ctx = r.retrieve_for_file(fd)
        assert ctx is not None
        assert "src/svc.py" in ctx.query_text
        assert "x = 1" in ctx.query_text

    def test_embedder_is_called_with_query_text(self):
        r, embedder, _ = make_retriever()
        fd = make_file_diff(filename="f.py", added_lines=["line"])
        r.retrieve_for_file(fd)
        embedder.embed.assert_called_once()
        call_arg = embedder.embed.call_args[0][0]  # primeiro arg posicional
        assert isinstance(call_arg, list)
        assert len(call_arg) == 1  # sempre uma lista com um texto

    def test_store_search_called_with_correct_params(self):
        """Verifica top_k e score_threshold; compara o vetor com tolerância float32."""
        r, embedder, store = make_retriever(top_k=3, score_threshold=0.7)
        fd = make_file_diff()
        r.retrieve_for_file(fd)

        store.search.assert_called_once()
        call_kwargs = store.search.call_args.kwargs
        assert call_kwargs["top_k"] == 3
        assert call_kwargs["score_threshold"] == 0.7
        # float32 → Python list pode ter imprecisão mínima; usa allclose
        assert np.allclose(call_kwargs["query_vector"], [0.1, 0.2, 0.3, 0.4], atol=1e-6)

    def test_embedding_is_converted_to_list(self):
        """O vetor enviado ao store deve ser uma lista Python, não numpy."""
        r, _, store = make_retriever()
        fd = make_file_diff()
        r.retrieve_for_file(fd)
        call_kwargs = store.search.call_args.kwargs
        assert isinstance(call_kwargs["query_vector"], list)


# ── Testes: retrieve_for_diff ─────────────────────────────────────────────────


class TestRetrieveForDiff:
    def test_returns_context_for_each_relevant_file(self):
        chunks = [make_chunk()]
        r, _, _ = make_retriever(chunks=chunks)
        pr = make_pr_diff(
            files=[
                make_file_diff(filename="a.py"),
                make_file_diff(filename="b.py"),
            ]
        )
        contexts = r.retrieve_for_diff(pr)
        assert len(contexts) == 2

    def test_files_without_added_lines_are_skipped(self):
        chunks = [make_chunk()]
        r, _, _ = make_retriever(chunks=chunks)
        pr = make_pr_diff(
            files=[
                make_file_diff(filename="a.py", added_lines=["x"]),
                make_file_diff(filename="b.py", added_lines=[]),  # sem adições
            ]
        )
        contexts = r.retrieve_for_diff(pr)
        filenames = [c.file_diff.filename for c in contexts]
        assert "a.py" in filenames
        assert "b.py" not in filenames

    def test_files_with_no_chunks_are_excluded(self):
        """Arquivos cujo diff não recupera normas relevantes não aparecem no resultado."""
        # Primeiro arquivo retorna chunks, segundo não
        store = MagicMock()
        store.search.side_effect = [
            [make_chunk()],  # a.py → tem contexto
            [],  # b.py → sem contexto
        ]
        embedder = make_embedder_mock()
        r = Retriever(embedder=embedder, store=store, top_k=3, score_threshold=0.55)

        pr = make_pr_diff(
            files=[
                make_file_diff(filename="a.py"),
                make_file_diff(filename="b.py"),
            ]
        )
        contexts = r.retrieve_for_diff(pr)
        assert len(contexts) == 1
        assert contexts[0].file_diff.filename == "a.py"

    def test_empty_pr_diff_returns_empty_list(self):
        r, _, _ = make_retriever()
        pr = make_pr_diff(files=[])
        assert r.retrieve_for_diff(pr) == []

    def test_all_files_without_added_lines_returns_empty(self):
        r, _, _ = make_retriever()
        pr = make_pr_diff(
            files=[
                make_file_diff(added_lines=[]),
                make_file_diff(added_lines=[]),
            ]
        )
        assert r.retrieve_for_diff(pr) == []

    def test_embedder_called_once_per_candidate_file(self):
        chunks = [make_chunk()]
        r, embedder, _ = make_retriever(chunks=chunks)
        pr = make_pr_diff(
            files=[
                make_file_diff(filename="a.py"),
                make_file_diff(filename="b.py"),
                make_file_diff(filename="c.py", added_lines=[]),  # ignorado
            ]
        )
        r.retrieve_for_diff(pr)
        # Dois arquivos com added_lines → embed chamado 2x
        assert embedder.embed.call_count == 2

    def test_store_search_called_once_per_candidate_file(self):
        chunks = [make_chunk()]
        r, _, store = make_retriever(chunks=chunks)
        pr = make_pr_diff(
            files=[
                make_file_diff(filename="a.py"),
                make_file_diff(filename="b.py"),
            ]
        )
        r.retrieve_for_diff(pr)
        assert store.search.call_count == 2

    def test_contexts_preserve_correct_file_diff(self):
        chunks = [make_chunk()]
        r, _, _ = make_retriever(chunks=chunks)
        fd_a = make_file_diff(filename="a.py")
        fd_b = make_file_diff(filename="b.py")
        pr = make_pr_diff(files=[fd_a, fd_b])
        contexts = r.retrieve_for_diff(pr)
        ctx_filenames = {c.file_diff.filename for c in contexts}
        assert ctx_filenames == {"a.py", "b.py"}

    def test_contexts_contain_chunks_from_store(self):
        chunk_a = make_chunk(text="Norma A", score=0.9)
        chunk_b = make_chunk(text="Norma B", score=0.75)
        store = MagicMock()
        store.search.side_effect = [[chunk_a], [chunk_b]]
        r = Retriever(
            embedder=make_embedder_mock(),
            store=store,
            top_k=3,
            score_threshold=0.55,
        )
        pr = make_pr_diff(
            files=[
                make_file_diff(filename="a.py"),
                make_file_diff(filename="b.py"),
            ]
        )
        contexts = r.retrieve_for_diff(pr)
        all_chunks = [c.chunks for c in contexts]
        assert [chunk_a] in all_chunks
        assert [chunk_b] in all_chunks


# ── Testes: integração com build_query_text ───────────────────────────────────


class TestQueryTextIntegration:
    def test_query_text_includes_filename_and_code(self):
        r, embedder, _ = make_retriever()
        fd = make_file_diff(
            filename="src/services/payment.py",
            added_lines=["amount = total * 1.1", "return amount"],
        )
        r.retrieve_for_file(fd)

        # Verifica o que foi passado ao embedder
        embedded_text = embedder.embed.call_args[0][0][0]
        assert "src/services/payment.py" in embedded_text
        assert "amount = total * 1.1" in embedded_text
        assert "return amount" in embedded_text

    def test_long_diff_is_truncated_before_embedding(self):
        """O build_query_text deve truncar diffs gigantes antes de embedar."""
        r, embedder, _ = make_retriever()
        fd = make_file_diff(added_lines=["x" * 3000])
        r.retrieve_for_file(fd)
        embedded_text = embedder.embed.call_args[0][0][0]
        assert len(embedded_text) <= 2000  # _MAX_QUERY_CHARS default
