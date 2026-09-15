import pytest

from rag_reviewer.sparse_encoder import SparseEncoder


def test_tokens_identicos_produzem_indices_em_comum():
    """
    `== True` é uma string literal. O casamento lexical não depende de o
    modelo entender português nem Python — é o ponto da camada esparsa.
    """
    enc = SparseEncoder()
    idx_norma, _ = enc.encode("Não compare valores booleanos com == True ou == False.")
    idx_linha, _ = enc.encode("if user.is_admin == True:")

    assert set(idx_norma) & set(idx_linha), "nenhum token em comum"


def test_textos_sem_relacao_nao_compartilham_tokens_relevantes():
    enc = SparseEncoder()
    idx_a, _ = enc.encode("comparações booleanas com == True")
    idx_b, _ = enc.encode("tamanho máximo de linha 79 caracteres")

    assert len(set(idx_a) & set(idx_b)) < len(set(idx_a)) / 2


def test_encoder_indisponivel_falha_alto(monkeypatch):
    """
    Cair para 'só denso' mudaria em silêncio a configuração sob medição,
    invalidando a ablação (spec §8.2).
    """
    enc = SparseEncoder()
    monkeypatch.setattr(
        enc, "_ensure_model_loaded", lambda: (_ for _ in ()).throw(ImportError("boom"))
    )
    with pytest.raises(ImportError):
        enc.encode("qualquer texto")
