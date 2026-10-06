"""
chunker.py — Divisão de documentos em chunks para indexação RAG.

Respeita as fronteiras naturais do texto: itens de lista de topo (uma norma e
seus exemplos) > parágrafos > frases > palavras. Blocos de código cercados
nunca são divididos.

Parâmetros padrão:
  - chunk_size:    512 palavras — balanceia contexto e precisão
  - chunk_overlap: 0 — sem sobreposição, para que nenhum trecho do corpus
                   apareça em dois chunks; é uma opção, não o padrão
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from indexer.document_loader import Document, _fenced_spans


@dataclass
class Chunk:
    """
    Representa um fragmento de documento pronto para ser embedado e indexado.

    Atributos:
        text:        Conteúdo do chunk.
        source:      Caminho do arquivo de origem.
        section:     Seção do documento de origem.
        chunk_index: Índice sequencial do chunk dentro do documento.
        indexed_at:  Timestamp ISO 8601 do momento de indexação.
    """

    text: str
    source: str
    section: str = ""
    chunk_index: int = 0
    indexed_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


class RecursiveChunker:
    """
    Divide documentos em chunks usando estratégia de janela deslizante.

    A divisão respeita fronteiras naturais na seguinte ordem de prioridade:
      1. Parágrafos (\\n\\n)
      2. Quebras de linha simples (\\n)
      3. Fim de frase ('. ', '! ', '? ')
      4. Espaço em branco

    Essa estratégia evita cortes no meio de regras ou frases importantes.

    Uso:
        chunker = RecursiveChunker(chunk_size=512)
        chunks = chunker.split(documents)
    """

    # Separadores em ordem de prioridade (do mais amplo ao mais granular)
    _SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", " "]

    # Marca de abertura/fechamento de bloco cercado (```  ou ~~~).
    _FENCE = re.compile(r"^[ \t]*(```|~~~)", re.MULTILINE)

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 0,
        length_function=None,
    ) -> None:
        """
        Args:
            chunk_size:      Tamanho máximo do chunk em palavras.
            chunk_overlap:   Sobreposição em palavras entre chunks consecutivos.
            length_function: Função para medir o tamanho do texto.
                             Padrão: contagem de palavras (sem necessidade de tokenizador).
        """
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) deve ser menor que chunk_size ({chunk_size})"
            )

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._len = length_function or self._word_count

    # ── Interface pública ─────────────────────────────────────────────────

    def split(self, documents: list[Document]) -> list[Chunk]:
        """
        Divide uma lista de Documents em Chunks.

        Args:
            documents: Lista de Documents retornados pelo DocumentLoader.

        Returns:
            Lista de Chunks com metadados do documento pai preservados.
        """
        all_chunks: list[Chunk] = []

        for doc in documents:
            chunks = self._split_text(doc.text)
            for idx, chunk_text in enumerate(chunks):
                all_chunks.append(
                    Chunk(
                        text=chunk_text,
                        source=doc.source,
                        section=doc.section,
                        chunk_index=idx,
                    )
                )

        return all_chunks

    # ── Implementação interna ─────────────────────────────────────────────

    def _split_text(self, text: str) -> list[str]:
        """
        Divide um texto em segmentos respeitando chunk_size e chunk_overlap.
        """
        # Se o texto cabe em um único chunk, retorna diretamente
        if self._len(text) <= self.chunk_size:
            stripped = text.strip()
            return [stripped] if stripped else []

        itens = self._split_items(text)
        if len(itens) > 1:
            # Cada item de lista de topo (uma norma e seus exemplos) é uma
            # unidade; só o item maior que chunk_size é subdividido.
            pecas: list[str] = []
            for item in itens:
                if self._len(item) > self.chunk_size:
                    pecas.extend(self._split_text(item))
                else:
                    pecas.append(item)
            return self._pack(pecas)

        segmentos = self._protect_fences(text)
        if any(is_fence for _, is_fence in segmentos):
            # Há ao menos um bloco cercado completo: trata cada bloco cercado
            # como unidade indivisível e só divide a prosa ao redor — mesmo
            # quando o bloco cercado é o único segmento (texto inteiro é uma
            # cerca) ou quando o restante da prosa contém uma marca órfã sem
            # par (essa prosa segue para a recursão normalmente, pois seu
            # próprio segmento não é atômico).
            resultado: list[str] = []
            for seg, is_fence in segmentos:
                if is_fence:
                    resultado.append(seg.strip())
                else:
                    resultado.extend(self._split_text(seg))
            return self._pack([r for r in resultado if r])

        # Nenhum bloco cercado completo (sem cercas, ou só marca(s) órfã(s)):
        # segue a divisão normal por separador.
        for separator in self._SEPARATORS:
            if separator in text:
                parts = text.split(separator)
                return self._merge_splits(parts, separator)

        # Fallback: divide por caractere (texto sem separadores naturais)
        return self._hard_split(text)

    def _split_items(self, text: str) -> list[str]:
        """
        Separa o texto nos itens de lista de topo ("- " na coluna 0).

        Linhas dentro de blocos cercados nunca iniciam um item. O trecho
        antes do primeiro item (título e introdução) é o primeiro elemento.
        Sem nenhum item de lista, devolve o texto inteiro como único elemento.
        """
        spans = _fenced_spans(text)
        inicios = [
            m.start()
            for m in re.finditer(r"^- ", text, re.MULTILINE)
            if not any(ini <= m.start() < fim for ini, fim in spans)
        ]
        if not inicios:
            return [text]

        limites = [0, *inicios, len(text)]
        itens = [text[a:b].strip() for a, b in zip(limites, limites[1:])]
        return [item for item in itens if item]

    def _pack(self, pecas: list[str]) -> list[str]:
        """
        Junta peças consecutivas até chunk_size, sem sobreposição.

        Uma peça nunca é dividida aqui: uma cerca ou um item maior que
        chunk_size permanece inteiro em um chunk próprio.
        """
        chunks: list[str] = []
        atual: list[str] = []
        tamanho = 0

        for peca in pecas:
            n = self._len(peca)
            if atual and tamanho + n > self.chunk_size:
                chunks.append("\n\n".join(atual))
                atual, tamanho = [], 0
            atual.append(peca)
            tamanho += n

        if atual:
            chunks.append("\n\n".join(atual))
        return chunks

    def _protect_fences(self, text: str) -> list[tuple[str, bool]]:
        """
        Fatia o texto em segmentos TIPADOS, alternando prosa e blocos
        cercados inteiros.

        Cada segmento vem com uma flag: True quando é um bloco cercado
        completo (par abertura/fechamento) e atômico — nunca deve ser
        dividido; False quando é prosa comum, sujeita à divisão normal por
        `_split_text`. Uma marca de cerca órfã (sem par, ex.: um ``` solto
        mencionado em prosa) nunca produz um segmento atômico sozinha — ela
        permanece dentro do texto de prosa em que caiu, e essa prosa segue
        para a recursão e a checagem de `chunk_size` normalmente. O chamador
        decide pelo tipo do segmento, nunca por uma nova busca de regex, que
        poderia casar essa marca órfã e confundi-la com um bloco atômico.

        Blocos cercados são ATÔMICOS: nunca são divididos. Um bloco partido
        ao meio separa o exemplo Correto do Incorreto, destruindo o par que
        dá ao chunk sua capacidade de casar com código (spec §1.3).
        """
        marcas = [m.start() for m in self._FENCE.finditer(text)]
        if len(marcas) < 2:
            return [(text, False)]

        segmentos: list[tuple[str, bool]] = []
        cursor = 0
        # Consome as marcas aos pares: abertura e fechamento. Uma marca
        # sobrando (contagem ímpar) não é consumida aqui — ela cai no
        # segmento de prosa final, sem se tornar atômica.
        for i in range(0, len(marcas) - 1, 2):
            inicio, fim_marca = marcas[i], marcas[i + 1]
            fim_linha = text.find("\n", fim_marca)
            fim = len(text) if fim_linha == -1 else fim_linha + 1

            if inicio > cursor:
                segmentos.append((text[cursor:inicio], False))
            segmentos.append((text[inicio:fim], True))
            cursor = fim

        if cursor < len(text):
            segmentos.append((text[cursor:], False))

        return [(s, is_fence) for s, is_fence in segmentos if s.strip()]

    def _merge_splits(self, splits: list[str], separator: str) -> list[str]:
        """
        Agrupa splits em chunks do tamanho correto com sobreposição.
        """
        chunks: list[str] = []
        current_parts: list[str] = []
        current_len = 0

        for part in splits:
            part_len = self._len(part)

            # Se adicionar este part excede o chunk_size, fecha o chunk atual
            if current_len + part_len > self.chunk_size and current_parts:
                chunk_text = separator.join(current_parts).strip()
                if chunk_text:
                    chunks.append(chunk_text)

                # Mantém overlap: remove parts do início até caber
                while current_parts and current_len > self.chunk_overlap:
                    removed = current_parts.pop(0)
                    current_len -= self._len(removed)

            current_parts.append(part)
            current_len += part_len

        # Adiciona o último chunk
        if current_parts:
            chunk_text = separator.join(current_parts).strip()
            if chunk_text:
                chunks.append(chunk_text)

        return chunks

    def _hard_split(self, text: str) -> list[str]:
        """
        Divide por palavras quando não há separadores naturais.
        Usado como fallback para textos muito densos (ex: código minificado).
        """
        words = text.split()
        chunks: list[str] = []
        i = 0

        while i < len(words):
            end = min(i + self.chunk_size, len(words))
            chunk_text = " ".join(words[i:end]).strip()
            if chunk_text:
                chunks.append(chunk_text)
            i += self.chunk_size - self.chunk_overlap

        return chunks

    # ── Utilitários ───────────────────────────────────────────────────────

    @staticmethod
    def _word_count(text: str) -> int:
        """Conta palavras (separadas por espaço) como proxy de tokens."""
        return len(text.split())
