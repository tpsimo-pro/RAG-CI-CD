"""O log de conexão não expõe o endereço do Qdrant (repositório e logs são públicos)."""

from unittest.mock import MagicMock, patch

from rag_reviewer.vector_store import VectorStore

URL = "https://abc12345-0000-1111-2222-333344445555.sa-east-1-0.aws.cloud.qdrant.io"


def test_log_de_conexao_nao_contem_a_url_nem_o_host():
    settings = MagicMock(
        qdrant_url=URL, qdrant_api_key="k", qdrant_collection="pep8_chunks"
    )
    with (
        patch("rag_reviewer.vector_store.get_settings", return_value=settings),
        patch("rag_reviewer.vector_store.console") as console,
        patch("qdrant_client.QdrantClient"),
    ):
        VectorStore()._get_client()
    texto = " ".join(str(c) for c in console.log.call_args_list)
    assert "conectado ao Qdrant" in texto
    assert "pep8_chunks" in texto
    for pedaco in (URL, "abc12345", "qdrant.io", "https://"):
        assert pedaco not in texto
