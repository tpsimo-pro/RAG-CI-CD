"""Testes unitários para o DocumentLoader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from indexer.document_loader import Document, DocumentLoader

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def loader() -> DocumentLoader:
    return DocumentLoader()


@pytest.fixture
def tmp_md(tmp_path: Path) -> Path:
    """Cria um arquivo Markdown temporário para testes."""
    content = textwrap.dedent(
        """\
        # Guia de Estilo

        Introdução ao guia.

        ## Nomenclatura

        Variáveis devem usar snake_case.

        ### Funções Booleanas

        Use o prefixo is_ ou has_.

        ## Tratamento de Exceções

        Nunca capture Exception genérica silenciosamente.
    """
    )
    md_file = tmp_path / "guide.md"
    md_file.write_text(content, encoding="utf-8")
    return md_file


@pytest.fixture
def tmp_txt(tmp_path: Path) -> Path:
    """Cria um arquivo TXT temporário."""
    content = "Regra 1: use snake_case.\nRegra 2: docstrings obrigatórias."
    txt_file = tmp_path / "rules.txt"
    txt_file.write_text(content, encoding="utf-8")
    return txt_file


# ── Testes: Document dataclass ────────────────────────────────────────────────


class TestDocument:
    def test_defaults(self):
        doc = Document(text="hello", source="file.md")
        assert doc.page == 0
        assert doc.section == ""

    def test_full_construction(self):
        doc = Document(text="content", source="guide.md", page=3, section="2.1 Naming")
        assert doc.text == "content"
        assert doc.source == "guide.md"
        assert doc.page == 3
        assert doc.section == "2.1 Naming"


# ── Testes: load_markdown ─────────────────────────────────────────────────────


class TestLoadMarkdown:
    def test_returns_list_of_documents(self, loader: DocumentLoader, tmp_md: Path):
        docs = loader.load(tmp_md)
        assert isinstance(docs, list)
        assert len(docs) > 0

    def test_all_items_are_documents(self, loader: DocumentLoader, tmp_md: Path):
        docs = loader.load(tmp_md)
        assert all(isinstance(d, Document) for d in docs)

    def test_source_is_correct_path(self, loader: DocumentLoader, tmp_md: Path):
        docs = loader.load(tmp_md)
        assert all(d.source == str(tmp_md) for d in docs)

    def test_section_headers_extracted(self, loader: DocumentLoader, tmp_md: Path):
        docs = loader.load(tmp_md)
        sections = [d.section for d in docs]
        assert "Nomenclatura" in sections
        assert "Tratamento de Exceções" in sections

    def test_text_not_empty(self, loader: DocumentLoader, tmp_md: Path):
        docs = loader.load(tmp_md)
        assert all(len(d.text.strip()) > 0 for d in docs)

    def test_subsection_extracted(self, loader: DocumentLoader, tmp_md: Path):
        docs = loader.load(tmp_md)
        sections = [d.section for d in docs]
        assert "Funções Booleanas" in sections

    def test_intro_before_first_heading(self, loader: DocumentLoader, tmp_md: Path):
        docs = loader.load(tmp_md)
        # Deve haver uma seção de introdução com o conteúdo antes do primeiro ##
        intro_docs = [
            d for d in docs if "Introdução" in d.section or "snake_case" in d.text
        ]
        assert len(intro_docs) > 0


class TestLoadMarkdownEdgeCases:
    def test_file_without_headings(self, loader: DocumentLoader, tmp_path: Path):
        md = tmp_path / "flat.md"
        md.write_text("Apenas texto plano sem cabeçalhos.", encoding="utf-8")
        docs = loader.load(md)
        assert len(docs) == 1
        assert "Apenas texto plano" in docs[0].text

    def test_empty_file_returns_empty_list(
        self, loader: DocumentLoader, tmp_path: Path
    ):
        md = tmp_path / "empty.md"
        md.write_text("", encoding="utf-8")
        docs = loader.load(md)
        assert docs == []

    def test_file_with_only_headings(self, loader: DocumentLoader, tmp_path: Path):
        md = tmp_path / "headers_only.md"
        md.write_text("## Seção A\n## Seção B\n", encoding="utf-8")
        docs = loader.load(md)
        # Seções sem conteúdo real devem ser omitidas
        assert all(len(d.text.strip()) > 0 for d in docs)


# ── Testes: load_txt ─────────────────────────────────────────────────────────


class TestLoadTxt:
    def test_loads_txt_as_single_document(self, loader: DocumentLoader, tmp_txt: Path):
        docs = loader.load(tmp_txt)
        assert len(docs) >= 1

    def test_source_preserved(self, loader: DocumentLoader, tmp_txt: Path):
        docs = loader.load(tmp_txt)
        assert all(d.source == str(tmp_txt) for d in docs)


# ── Testes: load_directory ────────────────────────────────────────────────────


class TestLoadDirectory:
    def test_loads_all_supported_files(self, loader: DocumentLoader, tmp_path: Path):
        (tmp_path / "a.md").write_text("## Seção A\nConteúdo A.", encoding="utf-8")
        (tmp_path / "b.txt").write_text("Conteúdo B.", encoding="utf-8")
        (tmp_path / "ignore.csv").write_text("col1,col2", encoding="utf-8")

        docs = loader.load_directory(tmp_path)
        # CSV deve ser ignorado
        sources = [d.source for d in docs]
        assert not any("ignore.csv" in s for s in sources)
        assert any("a.md" in s for s in sources)
        assert any("b.txt" in s for s in sources)

    def test_recursive_scan(self, loader: DocumentLoader, tmp_path: Path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "deep.md").write_text("## Deep\nConteúdo profundo.", encoding="utf-8")

        docs = loader.load_directory(tmp_path)
        assert any("deep.md" in d.source for d in docs)

    def test_empty_directory_returns_empty_list(
        self, loader: DocumentLoader, tmp_path: Path
    ):
        docs = loader.load_directory(tmp_path)
        assert docs == []


# ── Testes: erros ────────────────────────────────────────────────────────────


class TestLoadErrors:
    def test_file_not_found_raises(self, loader: DocumentLoader):
        with pytest.raises(FileNotFoundError):
            loader.load("caminho/que/nao/existe.md")

    def test_unsupported_format_raises(self, loader: DocumentLoader, tmp_path: Path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("col1,col2\n1,2", encoding="utf-8")
        with pytest.raises(ValueError, match="Formato não suportado"):
            loader.load(csv_file)

    def test_not_a_directory_raises(self, loader: DocumentLoader, tmp_path: Path):
        file = tmp_path / "file.md"
        file.write_text("content", encoding="utf-8")
        with pytest.raises(NotADirectoryError):
            loader.load_directory(file)
