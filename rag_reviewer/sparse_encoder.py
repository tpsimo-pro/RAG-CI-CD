"""
sparse_encoder.py — Vetores esparsos BM25 para a metade lexical da busca.

`== True` e `!= None` são padrões LEXICAIS: strings literais. Nenhum modelo
semântico deveria ser responsável por casar uma string exata — é a ferramenta
errada, e foi o que manteve todos os scores comprimidos entre 0.3 e 0.5
(spec §1.3). O casamento por token exato não depende de o modelo entender
português nem Python.
"""

from __future__ import annotations

from rich.console import Console

console = Console()

_MODEL_NAME = "Qdrant/bm25"


class SparseEncoder:
    """Gera vetores esparsos BM25 via fastembed, com carregamento preguiçoso."""

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        self._model_name = model_name
        self._model = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def encode(self, text: str) -> tuple[list[int], list[float]]:
        """
        Codifica um texto em (índices, valores) esparsos.

        Raises:
            ImportError: Se o fastembed não estiver instalado. NÃO há fallback
                para "só denso": isso mudaria em silêncio a configuração sob
                medição e invalidaria a ablação (spec §8.2).
        """
        self._ensure_model_loaded()
        emb = next(iter(self._model.embed([text])))  # type: ignore[union-attr]
        return [int(i) for i in emb.indices], [float(v) for v in emb.values]

    def encode_batch(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        """Versão em lote, usada na indexação."""
        self._ensure_model_loaded()
        return [
            ([int(i) for i in e.indices], [float(v) for v in e.values])
            for e in self._model.embed(texts)  # type: ignore[union-attr]
        ]

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from fastembed import SparseTextEmbedding  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "fastembed não está instalado e é obrigatório para a busca "
                "híbrida. Execute: pip install fastembed"
            ) from exc

        console.log(f"[cyan]SparseEncoder:[/cyan] carregando '{self._model_name}'...")
        self._model = SparseTextEmbedding(model_name=self._model_name)
