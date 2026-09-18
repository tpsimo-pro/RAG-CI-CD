"""
document_loader.py — Carregamento de documentos normativos.

Suporta Markdown (.md) e texto plano (.txt), com os cabeçalhos servindo de
separador de seção. O corpus normativo é integralmente Markdown (D-007), por
isso não há carregador de PDF nem de DOCX.

Retorna uma lista de objetos Document com texto e metadados preservados.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

console = Console()


@dataclass
class Document:
    """
    Representa um documento normativo ou uma seção dele.

    Atributos:
        text:    Conteúdo textual do documento/seção.
        source:  Caminho do arquivo de origem (relativo ao projeto).
        section: Título da seção (relevante para Markdown/DOCX).
    """

    text: str
    source: str
    section: str = ""


def _fenced_spans(raw: str) -> list[tuple[int, int]]:
    """
    Devolve os intervalos [início, fim) ocupados por blocos de código cercados.

    Cercas são linhas que começam com ``` ou ~~~ (com indentação opcional).
    ``` e ~~~ não são intercambiáveis: uma cerca só fecha com uma marca do
    MESMO tipo que a abriu. Uma marca de tipo diferente encontrada com uma
    cerca já aberta é conteúdo do bloco, não delimitador — do contrário a
    cerca de fechamento real vira uma abertura órfã que engole tudo até o
    fim do arquivo, inclusive cabeçalhos legítimos.

    Uma cerca de abertura sem fechamento do mesmo tipo estende-se até o fim
    do arquivo — tratar assim é conservador: prefere-se ignorar cabeçalhos
    reais a fabricar seções fantasma a partir de comentários de código.
    """
    spans: list[tuple[int, int]] = []
    abertura: int | None = None
    tipo_abertura: str | None = None

    for m in re.finditer(r"^[ \t]*(```|~~~)", raw, re.MULTILINE):
        marca = m.group(1)
        if abertura is None:
            abertura = m.start()
            tipo_abertura = marca
        elif marca == tipo_abertura:
            fim = raw.find("\n", m.end())
            spans.append((abertura, len(raw) if fim == -1 else fim + 1))
            abertura = None
            tipo_abertura = None
        # marca de tipo diferente com cerca já aberta: conteúdo, não fechamento.

    if abertura is not None:
        spans.append((abertura, len(raw)))

    return spans


class DocumentLoader:
    """
    Carrega documentos de múltiplos formatos e os converte em lista de Document.

    Uso:
        loader = DocumentLoader()
        docs = loader.load("docs/style_guides/coding_standards.md")
    """

    SUPPORTED_EXTENSIONS = {".md", ".txt"}

    def load(self, path: str | Path) -> list[Document]:
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

        console.log(
            f"[cyan]DocumentLoader:[/cyan] carregando [bold]{path.name}[/bold] ({suffix})"
        )

        docs = self._load_markdown(path)

        console.log(
            f"[green]  ✅ {len(docs)} seção(ões) carregada(s) de '{path.name}'[/green]"
        )
        return docs

    def load_directory(self, directory: str | Path) -> list[Document]:
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

        all_docs: list[Document] = []
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                try:
                    all_docs.extend(self.load(path))
                except Exception as exc:
                    console.log(f"[yellow]⚠️  Erro ao carregar '{path}': {exc}[/yellow]")

        return all_docs

    # ── Implementações por formato ────────────────────────────────────────

    def _load_markdown(self, path: Path) -> list[Document]:
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
        spans = _fenced_spans(raw)
        matches = [
            m
            for m in pattern.finditer(raw)
            if not any(inicio <= m.start() < fim for inicio, fim in spans)
        ]

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

    @staticmethod
    def _clean_text(text: str) -> str:
        """Normaliza espaços e remove separadores visuais do texto carregado."""
        # Remove quebras de linha excessivas
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove espaços extras
        text = re.sub(r"[ \t]+", " ", text)
        # Remove linhas que só têm hífens/underscore (separadores visuais)
        text = re.sub(r"^[-_=]{3,}\s*$", "", text, flags=re.MULTILINE)
        return text.strip()
