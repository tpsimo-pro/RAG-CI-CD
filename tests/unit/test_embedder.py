"""Testes unitários para o Embedder."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from rag_reviewer.embedder import Embedder


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_sentence_transformer():
    """Mock do SentenceTransformer para evitar download de modelo nos testes."""
    model = MagicMock()
    model.get_sentence_embedding_dimension.return_value = 384
    # encode retorna array numpy de floats normalizados
    model.encode = MagicMock(
        side_effect=lambda texts, **kwargs: np.random.rand(len(texts), 384).astype(np.float32)
    )
    return model


@pytest.fixture
def embedder(mock_sentence_transformer) -> Embedder:
    """Embedder com modelo mockado."""
    with patch("rag_reviewer.embedder.SentenceTransformer", return_value=mock_sentence_transformer):
        emb = Embedder(model_name="all-MiniLM-L6-v2")
        emb._model = mock_sentence_transformer  # injeta o mock diretamente
        return emb


# ── Testes: inicialização ─────────────────────────────────────────────────────


class TestEmbedderInit:
    def test_default_model_name(self):
        emb = Embedder()
        assert emb.model_name == "all-MiniLM-L6-v2"

    def test_custom_model_name(self):
        emb = Embedder(model_name="paraphrase-multilingual-MiniLM-L12-v2")
        assert emb.model_name == "paraphrase-multilingual-MiniLM-L12-v2"

    def test_model_not_loaded_on_init(self):
        emb = Embedder()
        assert emb._model is None  # lazy loading — não carrega no __init__


# ── Testes: embed ─────────────────────────────────────────────────────────────


class TestEmbed:
    def test_returns_numpy_array(self, embedder: Embedder):
        result = embedder.embed(["texto de teste"])
        assert isinstance(result, np.ndarray)

    def test_shape_is_correct(self, embedder: Embedder):
        texts = ["texto um", "texto dois", "texto três"]
        result = embedder.embed(texts)
        assert result.shape == (3, 384)

    def test_dtype_is_float32(self, embedder: Embedder):
        result = embedder.embed(["texto"])
        assert result.dtype == np.float32

    def test_empty_list_returns_empty_array(self, embedder: Embedder):
        result = embedder.embed([])
        assert len(result) == 0

    def test_single_text_returns_shape_1_d(self, embedder: Embedder):
        result = embedder.embed(["apenas um texto"])
        assert result.shape[0] == 1

    def test_encode_called_with_correct_arguments(self, embedder: Embedder, mock_sentence_transformer):
        texts = ["texto A", "texto B"]
        embedder.embed(texts)
        mock_sentence_transformer.encode.assert_called_once()
        call_args = mock_sentence_transformer.encode.call_args
        assert call_args[0][0] == texts
        assert call_args[1]["normalize_embeddings"] is True
        assert call_args[1]["batch_size"] == 32


# ── Testes: embed_single ─────────────────────────────────────────────────────


class TestEmbedSingle:
    def test_returns_1d_array(self, embedder: Embedder):
        result = embedder.embed_single("texto único")
        assert result.ndim == 1
        assert result.shape[0] == 384

    def test_dtype_is_float32(self, embedder: Embedder):
        result = embedder.embed_single("texto")
        assert result.dtype == np.float32


# ── Testes: vector_size ───────────────────────────────────────────────────────


class TestVectorSize:
    def test_vector_size_returns_correct_dimension(self, embedder: Embedder):
        assert embedder.vector_size == 384

    def test_vector_size_triggers_model_load(self, mock_sentence_transformer):
        """vector_size deve forçar o carregamento do modelo."""
        with patch("rag_reviewer.embedder.SentenceTransformer", return_value=mock_sentence_transformer) as mock_cls:
            emb = Embedder(model_name="all-MiniLM-L6-v2")
            assert emb._model is None  # ainda não carregado
            _ = emb.vector_size
            assert emb._model is not None  # deve ter carregado


# ── Testes: ImportError ───────────────────────────────────────────────────────


class TestImportError:
    def test_missing_sentence_transformers_raises_import_error(self):
        """Se sentence-transformers não estiver instalado, deve levantar ImportError claro."""
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            emb = Embedder()
            emb._model = None  # garante que tentará carregar
            with pytest.raises((ImportError, TypeError)):
                emb._ensure_model_loaded()
