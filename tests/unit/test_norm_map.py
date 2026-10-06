import json
from pathlib import Path

import pytest

from evaluation.retrieval.gold import build_gold
from evaluation.retrieval.norm_map import (
    NORM_BOOLEANO,
    NORM_EXCECAO,
    NORM_NOME_CLASSE,
    NORM_NOME_FUNCAO,
    NORM_NOME_PROIBIDO,
    NORM_NULO,
    norm_keys_of_chunk,
)
from indexer.chunker import RecursiveChunker
from indexer.document_loader import DocumentLoader


def test_chunk_com_norma_booleana_e_reconhecido():
    texto = (
        "- Don't compare boolean values to True or False using `==`:\n"
        "  Correct: if greeting:\n"
        "  Wrong: if greeting == True:"
    )
    assert NORM_BOOLEANO in norm_keys_of_chunk(texto)


def test_chunk_com_norma_de_nulos_e_reconhecido_apesar_da_quebra_de_linha():
    texto = (
        "- Comparisons to singletons like None should always be done with\n"
        "  `is` or `is not`, never the equality operators."
    )
    assert NORM_NULO in norm_keys_of_chunk(texto)


def test_chunk_irrelevante_nao_carrega_chave():
    texto = "Limit all lines to a maximum of 79 characters."
    assert norm_keys_of_chunk(texto) == set()


def test_chunk_unico_pode_carregar_as_duas_chaves():
    texto = (
        "Don't compare boolean values to True or False using ==.\n"
        "Comparisons to singletons like None should always be done with is."
    )
    assert norm_keys_of_chunk(texto) == {NORM_BOOLEANO, NORM_NULO}


def test_chunk_de_excecoes_carrega_a_norma_do_except_nu():
    texto = (
        "- When catching exceptions, mention specific exceptions whenever\n"
        "  possible instead of using a bare `except:` clause:"
    )
    assert NORM_EXCECAO in norm_keys_of_chunk(texto)


def test_excecao_derivada_de_exception_nao_carrega_a_norma():
    texto = "- Derive exceptions from `Exception` rather than `BaseException`."
    assert NORM_EXCECAO not in norm_keys_of_chunk(texto)


def test_gold_mapeia_as_sub_regras_de_excecao(tmp_path):
    dataset = [
        {
            "pr_id": "PR-900",
            "added_lines": [
                {
                    "line": "except:",
                    "viola": True,
                    "sub_regra": "except_nu_silencioso",
                },
                {
                    "line": "except:",
                    "viola": True,
                    "sub_regra": "except_nu_retorno",
                },
                {"line": "    pass", "viola": False, "sub_regra": None},
            ],
        }
    ]
    path = tmp_path / "ds.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")

    gold = build_gold(path)

    assert [g.norm_key for g in gold] == [NORM_EXCECAO, NORM_EXCECAO]


@pytest.mark.parametrize(
    "chave",
    [
        NORM_BOOLEANO,
        NORM_NULO,
        NORM_NOME_FUNCAO,
        NORM_NOME_CLASSE,
        NORM_NOME_PROIBIDO,
        NORM_EXCECAO,
    ],
)
def test_toda_chave_e_carregada_por_algum_chunk_do_corpus_real(chave):
    corpus = Path(__file__).parent.parent.parent / "docs" / "style_guides"
    chunks = RecursiveChunker().split(DocumentLoader().load_directory(corpus))

    portadores = [c for c in chunks if chave in norm_keys_of_chunk(c.text)]

    assert len(portadores) == 1
