import pytest

from rag_reviewer.vector_store import VectorStore


class _FakeClient:
    def __init__(self, modelo_no_indice: str | None):
        self._modelo = modelo_no_indice

    def scroll(self, collection_name, limit, with_payload):
        if self._modelo is None:
            return [], None
        ponto = type("P", (), {"payload": {"embedding_model": self._modelo}})()
        return [ponto], None


def _store_com(modelo_no_indice):
    store = VectorStore(collection_name="teste")
    store._client = _FakeClient(modelo_no_indice)
    return store


def test_modelo_igual_nao_levanta():
    _store_com("all-MiniLM-L6-v2").assert_model_matches("all-MiniLM-L6-v2")


def test_modelo_divergente_levanta_com_instrucao():
    store = _store_com("all-MiniLM-L6-v2")
    with pytest.raises(RuntimeError) as exc:
        store.assert_model_matches("paraphrase-multilingual-MiniLM-L12-v2")
    assert "index-recreate" in str(exc.value)


def test_indice_vazio_levanta():
    store = _store_com(None)
    with pytest.raises(RuntimeError):
        store.assert_model_matches("qualquer-modelo")
