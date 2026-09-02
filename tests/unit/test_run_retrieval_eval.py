"""
test_run_retrieval_eval.py — Testa a montagem pura da consulta por arquivo.

Cobre `_retrieve_for_file`, a lógica L0/L1 do harness de retrieval: nome do
arquivo + linhas adicionadas concatenadas, replicando `build_query_text`
(rag_reviewer/diff_parser.py). Roda sem rede — usa dublês de `Embedder` e
`VectorStore` em vez do Qdrant ou de um modelo sentence-transformers real.
"""

from __future__ import annotations

from evaluation.retrieval.run_retrieval_eval import _retrieve_for_file


class _VetorFalso:
    """Dublê do retorno de `Embedder.embed_single`."""

    def __init__(self, valores: list[float]) -> None:
        self._valores = valores

    def tolist(self) -> list[float]:
        return self._valores


class _EmbedderFalso:
    """Dublê que registra o texto recebido em vez de carregar um modelo real."""

    def __init__(self) -> None:
        self.textos_recebidos: list[str] = []

    def embed_single(self, text: str) -> _VetorFalso:
        self.textos_recebidos.append(text)
        return _VetorFalso([0.1, 0.2, 0.3])


class _VectorStoreFalso:
    """Dublê que registra os argumentos de busca e devolve chunks fixos."""

    def __init__(self) -> None:
        self.chamadas: list[dict] = []

    def search(self, query_vector: list, top_k: int, score_threshold: float) -> list[dict]:
        self.chamadas.append(
            {
                "query_vector": query_vector,
                "top_k": top_k,
                "score_threshold": score_threshold,
            }
        )
        return [
            {
                "text": "chunk-fake",
                "source": "s",
                "section": "5",
                "page": 1,
                "score": 0.9,
            }
        ]


def test_retrieve_for_file_monta_consulta_com_arquivo_e_linhas():
    """A consulta deve ser exatamente 'Arquivo: <nome>\\n<linhas>', igual a build_query_text."""
    embedder = _EmbedderFalso()
    store = _VectorStoreFalso()

    _retrieve_for_file(
        embedder,
        store,
        lines=["linha um", "linha dois"],
        filename="auth/permissions.py",
        top_k=5,
        score_threshold=0.55,
    )

    assert embedder.textos_recebidos == [
        "Arquivo: auth/permissions.py\nlinha um\nlinha dois"
    ]


def test_retrieve_for_file_repassa_top_k_e_threshold_para_a_busca():
    """top_k e score_threshold devem chegar intactos ao VectorStore.search."""
    embedder = _EmbedderFalso()
    store = _VectorStoreFalso()

    _retrieve_for_file(embedder, store, ["x"], "f.py", top_k=3, score_threshold=0.7)

    assert store.chamadas == [
        {"query_vector": [0.1, 0.2, 0.3], "top_k": 3, "score_threshold": 0.7}
    ]


def test_retrieve_for_file_devolve_os_chunks_do_store():
    """O retorno deve ser exatamente a lista de chunks que o VectorStore devolveu."""
    embedder = _EmbedderFalso()
    store = _VectorStoreFalso()

    resultado = _retrieve_for_file(
        embedder, store, ["x"], "f.py", top_k=5, score_threshold=0.55
    )

    assert resultado == [
        {"text": "chunk-fake", "source": "s", "section": "5", "page": 1, "score": 0.9}
    ]


def test_retrieve_for_file_com_lista_de_linhas_vazia():
    """Sem linhas adicionadas, a consulta se resume ao cabeçalho do arquivo."""
    embedder = _EmbedderFalso()
    store = _VectorStoreFalso()

    _retrieve_for_file(embedder, store, [], "f.py", top_k=5, score_threshold=0.55)

    assert embedder.textos_recebidos == ["Arquivo: f.py\n"]
