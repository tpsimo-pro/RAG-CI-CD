"""
document_loader.py — Carregamento de documentos normativos.

Suporta os formatos:
  - PDF (.pdf) via pypdf
  - Markdown (.md) e texto plano (.txt) via markdown + BeautifulSoup
  - DOCX (.docx) via python-docx

Retorna uma lista de objetos Document com texto e metadados preservados.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from rich.console import Console

console = Console()


@dataclass
class Document:
    """
    Representa um documento normativo ou uma seção dele.

    Atributos:
        text:    Conteúdo textual do documento/seção.
        source:  Caminho do arquivo de origem (relativo ao projeto).
        page:    Número da página (relevante para PDFs; 0 para outros formatos).
        section: Título da seção (relevante para Markdown/DOCX).
    """

    text: str
    source: str
    page: int = 0
    section: str = ""


class DocumentLoader:
    """
    Carrega documentos de múltiplos formatos e os converte em lista de Document.

    Uso:
        loader = DocumentLoader()
        docs = loader.load("docs/style_guides/coding_standards.md")
    """

    SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt", ".docx"}

    def load(self, path: str | Path) -> List[Document]:
        """
        Carrega um arquivo e retorna lista de Document.

        Args:
            path: Caminho para o arquivo a ser carregado.

        Returns:
            Lista de Document com texto e metadados.

        Raises:
            ValueError: Se o formato do arquivo não for suportado.
            FileNotFoundError: Se o arquivo não existir.
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")

        suffix = path.suffix.lower()

        if suffix not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Formato não suportado: '{suffix}'. "
                f"Formatos suportados: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )

        console.log(f"[cyan]DocumentLoader:[/cyan] carregando [bold]{path.name}[/bold] ({suffix})")

        if suffix == ".pdf":
            docs = self._load_pdf(path)
        elif suffix in (".md", ".txt"):
            docs = self._load_markdown(path)
        elif suffix == ".docx":
            docs = self._load_docx(path)
        else:
            docs = []

        console.log(
            f"[green]  ✅ {len(docs)} seção(ões) carregada(s) de '{path.name}'[/green]"
        )
        return docs

    def load_directory(self, directory: str | Path) -> List[Document]:
        """
        Carrega recursivamente todos os documentos suportados de um diretório.

        Args:
            directory: Caminho do diretório a ser escaneado.

        Returns:
            Lista concatenada de todos os Documents encontrados.
        """
        directory = Path(directory)
        if not directory.is_dir():
            raise NotADirectoryError(f"Não é um diretório: {directory}")

        all_docs: List[Document] = []
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                try:
                    all_docs.extend(self.load(path))
                except Exception as exc:
                    console.log(f"[yellow]⚠️  Erro ao carregar '{path}': {exc}[/yellow]")

        return all_docs

    # ── Implementações por formato ────────────────────────────────────────

    def _load_pdf(self, path: Path) -> List[Document]:
        """Extrai texto página a página usando pypdf."""
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "pypdf não está instalado. Execute: pip install pypdf"
            ) from exc

        reader = PdfReader(str(path))
        docs = []

        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = self._clean_text(text)

            if len(text.strip()) < 20:
                # Página sem conteúdo relevante (ex: páginas em branco, cabeçalhos)
                continue

            docs.append(
                Document(
                    text=text,
                    source=str(path),
                    page=page_num,
                    section=f"Página {page_num}",
                )
            )

        return docs

    def _load_markdown(self, path: Path) -> List[Document]:
        """
        Extrai seções de Markdown usando cabeçalhos como separadores.

        Cada seção (##, ###) se torna um Document separado, preservando
        o título da seção como metadado. O conteúdo anterior ao primeiro
        cabeçalho é tratado como seção introdutória.
        """
        raw = path.read_text(encoding="utf-8", errors="replace")

        # Divide por cabeçalhos de nível 1, 2 ou 3
        # Regex: captura o cabeçalho e seu conteúdo até o próximo cabeçalho
        pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
        matches = list(pattern.finditer(raw))

        docs = []
        source = str(path)

        if not matches:
            # Arquivo sem cabeçalhos: trata como documento único
            text = self._clean_text(raw)
            if text.strip():
                docs.append(Document(text=text, source=source, section="(sem título)"))
            return docs

        # Conteúdo antes do primeiro cabeçalho (ex: metadados, introdução)
        intro = raw[: matches[0].start()].strip()
        if intro:
            docs.append(
                Document(
                    text=self._clean_text(intro),
                    source=source,
                    section="Introdução",
                )
            )

        # Extrai cada seção
        for i, match in enumerate(matches):
            section_title = match.group(2).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            body = raw[start:end].strip()

            # Inclui o título no texto para contexto semântico
            full_text = f"{section_title}\n\n{body}"
            text = self._clean_text(full_text)

            if len(text.strip()) < 10:
                continue

            docs.append(
                Document(
                    text=text,
                    source=source,
                    section=section_title,
                )
            )

        return docs

    def _load_docx(self, path: Path) -> List[Document]:
        """
        Extrai parágrafos de um arquivo DOCX, agrupando por estilos de cabeçalho.

        Parágrafos com estilo 'Heading X' delimitam novas seções.
        """
        try:
            import docx  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "python-docx não está instalado. Execute: pip install python-docx"
            ) from exc

        doc = docx.Document(str(path))
        docs = []
        source = str(path)

        current_section = "Introdução"
        current_paragraphs: List[str] = []

        for para in doc.paragraphs:
            style_name = para.style.name if para.style else ""
            text = para.text.strip()

            if not text:
                continue

            is_heading = style_name.startswith("Heading") or style_name.startswith("Título")

            if is_heading:
                # Salva a seção anterior
                if current_paragraphs:
                    body = "\n\n".join(current_paragraphs)
                    full_text = f"{current_section}\n\n{body}"
                    docs.append(
                        Document(
                            text=self._clean_text(full_text),
                            source=source,
                            section=current_section,
                        )
                    )
                # Inicia nova seção
                current_section = text
                current_paragraphs = []
            else:
                current_paragraphs.append(text)

        # Salva a última seção
        if current_paragraphs:
            body = "\n\n".join(current_paragraphs)
            full_text = f"{current_section}\n\n{body}"
            docs.append(
                Document(
                    text=self._clean_text(full_text),
                    source=source,
                    section=current_section,
                )
            )

        return docs

    # ── Utilitários ───────────────────────────────────────────────────────

    @staticmethod
    def _clean_text(text: str) -> str:
        """
        Normaliza espaços e remove artefatos comuns de extração de PDF/DOCX.
        """
        # Remove quebras de linha excessivas
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove espaços extras
        text = re.sub(r"[ \t]+", " ", text)
        # Remove linhas que só têm hífens/underscore (separadores visuais)
        text = re.sub(r"^[-_=]{3,}\s*$", "", text, flags=re.MULTILINE)
        return text.strip()
