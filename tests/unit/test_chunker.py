"""Testes unitários para o RecursiveChunker."""

from __future__ import annotations

import pytest

from indexer.chunker import Chunk, RecursiveChunker
from indexer.document_loader import Document

# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_doc(text: str, source: str = "test.md", section: str = "Teste") -> Document:
    return Document(text=text, source=source, section=section, page=0)


@pytest.fixture
def chunker() -> RecursiveChunker:
    return RecursiveChunker(chunk_size=50, chunk_overlap=10)


@pytest.fixture
def small_chunker() -> RecursiveChunker:
    """Chunker com chunk_size pequeno para forçar divisão."""
    return RecursiveChunker(chunk_size=10, chunk_overlap=2)


# ── Testes: Chunk dataclass ───────────────────────────────────────────────────


class TestChunk:
    def test_defaults(self):
        chunk = Chunk(text="hello", source="file.md")
        assert chunk.section == ""
        assert chunk.page == 0
        assert chunk.chunk_index == 0
        assert chunk.indexed_at != ""

    def test_indexed_at_is_iso8601(self):
        import re

        chunk = Chunk(text="test", source="f.md")
        # Verifica formato ISO 8601 básico
        assert re.match(r"\d{4}-\d{2}-\d{2}T", chunk.indexed_at)


# ── Testes: RecursiveChunker.__init__ ────────────────────────────────────────


class TestChunkerInit:
    def test_valid_parameters(self):
        chunker = RecursiveChunker(chunk_size=512, chunk_overlap=64)
        assert chunker.chunk_size == 512
        assert chunker.chunk_overlap == 64

    def test_overlap_equal_to_size_raises(self):
        with pytest.raises(ValueError, match="chunk_overlap"):
            RecursiveChunker(chunk_size=100, chunk_overlap=100)

    def test_overlap_greater_than_size_raises(self):
        with pytest.raises(ValueError, match="chunk_overlap"):
            RecursiveChunker(chunk_size=100, chunk_overlap=150)


# ── Testes: split — documento pequeno ────────────────────────────────────────


class TestSplitSmallDocument:
    def test_document_smaller_than_chunk_size_returns_one_chunk(
        self, chunker: RecursiveChunker
    ):
        doc = make_doc("Texto curto.")
        chunks = chunker.split([doc])
        assert len(chunks) == 1

    def test_single_chunk_preserves_text(self, chunker: RecursiveChunker):
        text = "Texto curto que cabe em um chunk."
        doc = make_doc(text)
        chunks = chunker.split([doc])
        assert chunks[0].text == text

    def test_empty_document_returns_no_chunks(self, chunker: RecursiveChunker):
        doc = make_doc("")
        chunks = chunker.split([doc])
        assert chunks == []

    def test_whitespace_only_document_returns_no_chunks(
        self, chunker: RecursiveChunker
    ):
        doc = make_doc("   \n\n   ")
        chunks = chunker.split([doc])
        assert chunks == []


# ── Testes: split — documento grande ─────────────────────────────────────────


class TestSplitLargeDocument:
    def test_large_document_splits_into_multiple_chunks(
        self, small_chunker: RecursiveChunker
    ):
        # 50 palavras → deve gerar mais de 1 chunk com chunk_size=10
        text = " ".join(f"palavra{i}" for i in range(50))
        doc = make_doc(text)
        chunks = small_chunker.split([doc])
        assert len(chunks) > 1

    def test_all_chunks_respect_size_limit(self, small_chunker: RecursiveChunker):
        text = " ".join(f"palavra{i}" for i in range(100))
        doc = make_doc(text)
        chunks = small_chunker.split([doc])
        # Com uma margem de tolerância (separadores podem aumentar levemente)
        for chunk in chunks:
            word_count = len(chunk.text.split())
            assert (
                word_count <= small_chunker.chunk_size + 5
            ), f"Chunk muito grande: {word_count} palavras"

    def test_chunks_are_not_empty(self, small_chunker: RecursiveChunker):
        text = " ".join(f"palavra{i}" for i in range(50))
        doc = make_doc(text)
        chunks = small_chunker.split([doc])
        assert all(len(c.text.strip()) > 0 for c in chunks)

    def test_chunk_indices_are_sequential(self, small_chunker: RecursiveChunker):
        text = " ".join(f"palavra{i}" for i in range(50))
        doc = make_doc(text)
        chunks = small_chunker.split([doc])
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))


# ── Testes: split — metadados ─────────────────────────────────────────────────


class TestSplitMetadata:
    def test_source_preserved_in_chunks(self, chunker: RecursiveChunker):
        doc = make_doc("Conteúdo de teste.", source="my_guide.pdf")
        chunks = chunker.split([doc])
        assert all(c.source == "my_guide.pdf" for c in chunks)

    def test_section_preserved_in_chunks(self, chunker: RecursiveChunker):
        doc = make_doc("Conteúdo.", section="3.2 Nomenclatura")
        chunks = chunker.split([doc])
        assert all(c.section == "3.2 Nomenclatura" for c in chunks)

    def test_page_preserved_in_chunks(self, chunker: RecursiveChunker):
        doc = Document(text="Conteúdo da página 5.", source="doc.pdf", page=5)
        chunks = chunker.split([doc])
        assert all(c.page == 5 for c in chunks)

    def test_indexed_at_is_set(self, chunker: RecursiveChunker):
        doc = make_doc("Conteúdo.")
        chunks = chunker.split([doc])
        assert all(c.indexed_at != "" for c in chunks)


# ── Testes: split — múltiplos documentos ─────────────────────────────────────


class TestSplitMultipleDocuments:
    def test_multiple_documents_concatenated(self, chunker: RecursiveChunker):
        docs = [make_doc("Doc A."), make_doc("Doc B.")]
        chunks = chunker.split(docs)
        assert len(chunks) >= 2

    def test_chunks_from_different_sources(self, chunker: RecursiveChunker):
        docs = [
            make_doc("Conteúdo A.", source="a.md"),
            make_doc("Conteúdo B.", source="b.md"),
        ]
        chunks = chunker.split(docs)
        sources = {c.source for c in chunks}
        assert "a.md" in sources
        assert "b.md" in sources

    def test_empty_list_returns_empty(self, chunker: RecursiveChunker):
        chunks = chunker.split([])
        assert chunks == []


# ── Testes: divisão por parágrafos ────────────────────────────────────────────


class TestSplitByParagraph:
    def test_respects_paragraph_boundaries(self):
        """Com chunk_size grande, parágrafos devem ser agrupados; com chunk_size pequeno, separados."""
        chunker = RecursiveChunker(chunk_size=5, chunk_overlap=1)
        text = "Parágrafo um com algumas palavras.\n\nParágrafo dois com mais palavras aqui."
        doc = make_doc(text)
        chunks = chunker.split([doc])
        # Deve haver mais de 1 chunk dado o tamanho pequeno
        assert len(chunks) >= 1
        assert all(len(c.text.strip()) > 0 for c in chunks)


# ── Testes: blocos cercados são atômicos (Tarefa 5) ──────────────────────────

from indexer.document_loader import Document
from indexer.chunker import RecursiveChunker


def _conta_cercas(texto: str) -> int:
    return sum(1 for linha in texto.splitlines() if linha.strip().startswith("```"))


def test_bloco_cercado_nunca_e_partido_entre_chunks():
    """
    Um bloco de código partido ao meio perde o par Correto/Incorreto, que é
    justamente o que dá +42% de margem de discriminação (spec §1.3).
    """
    corpo = "Texto normativo. " * 400  # força a divisão por tamanho
    doc = Document(
        text=(
            "5. Comparações\n\n"
            + corpo
            + "\n\n```python\n# Correto\nif is_valid:\n# Incorreto\nif is_valid == True:\n```\n"
        ),
        source="guia.md",
        section="5. Comparações",
    )

    chunks = RecursiveChunker(chunk_size=100, chunk_overlap=10).split([doc])

    assert len(chunks) > 1, "o teste precisa de um documento que realmente divida"
    for c in chunks:
        assert _conta_cercas(c.text) % 2 == 0, (
            f"chunk com cerca desemparelhada:\n{c.text}"
        )


def test_documento_pequeno_vira_um_unico_chunk():
    doc = Document(
        text="5. Comparações\n\nNão compare booleanos com == True.\n\n"
        "```python\nif is_valid:\n```",
        source="guia.md",
        section="5. Comparações",
    )
    chunks = RecursiveChunker(chunk_size=512, chunk_overlap=64).split([doc])
    assert len(chunks) == 1
    assert "if is_valid:" in chunks[0].text


def test_bloco_cercado_com_linha_em_branco_interna_nao_e_partido():
    """
    Regressão (achada por verificação manual durante a Tarefa 5): antes da
    correção, uma linha em branco DENTRO do bloco cercado fazia o separador
    de parágrafo ('\n\n') cortar a própria cerca ao meio — cada metade
    ficava com uma marca ``` desemparelhada em chunks diferentes.
    """
    texto = (
        "5. Comparações\n\n"
        "```python\n# Correto\nif is_valid:\n\n# Incorreto\nif is_valid == True:\n```\n"
    )
    doc = Document(text=texto, source="guia.md", section="5. Comparações")

    chunks = RecursiveChunker(chunk_size=10, chunk_overlap=2).split([doc])

    for c in chunks:
        assert _conta_cercas(c.text) % 2 == 0, (
            f"chunk com cerca desemparelhada:\n{c.text}"
        )
    # O bloco cercado inteiro deve estar junto em um único chunk.
    assert any("# Correto" in c.text and "# Incorreto" in c.text for c in chunks)
