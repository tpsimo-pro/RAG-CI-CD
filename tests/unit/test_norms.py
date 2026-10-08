"""O catalogo de normas (D-010) contra o ruff instalado e o texto da PEP 8."""

from __future__ import annotations

from pathlib import Path

import pytest

from evaluation.dataset.conformity import ast_findings, ruff_findings
from evaluation.dataset.norms import (
    FAMILIAS,
    NORMAS,
    NORMAS_POR_ID,
    ids_da_familia,
    normas_do_chunk,
)
from indexer.chunker import RecursiveChunker
from indexer.document_loader import DocumentLoader

CORPUS = Path(__file__).parent.parent.parent / "docs" / "style_guides"


def test_sao_23_normas_em_6_familias_com_ids_unicos():
    assert len(NORMAS) == 23
    assert len(NORMAS_POR_ID) == 23
    assert {n.familia for n in NORMAS} == set(FAMILIAS)
    assert len(FAMILIAS) == 6


@pytest.mark.parametrize("norma", NORMAS, ids=lambda n: n.id)
def test_exemplo_viola_so_a_propria_norma(norma):
    codigo = norma.exemplo.rstrip("\n")
    achados = {tag for _, tag in ruff_findings(codigo)}
    assert achados & norma.ruff, (norma.id, achados)
    assert achados <= norma.ruff, (norma.id, achados)
    tags_ast = {tag for _, tag in ast_findings(codigo)}
    assert (norma.id in tags_ast) == norma.ast, (norma.id, tags_ast)


def test_constante_em_capwords_so_a_checagem_ast_pega():
    codigo = "MaxRetries = 3"
    assert ruff_findings(codigo) == []
    assert {tag for _, tag in ast_findings(codigo)} == {"constante_maiuscula"}


@pytest.mark.parametrize(
    "codigo",
    [
        "MAX_RETRIES = 3",
        "max_retries = 3",
        "logger = make_logger()",
        "__all__ = ['f']",
        "def f():\n    maxRetries = 3\n    return maxRetries",
    ],
)
def test_constante_nao_acusa_formas_validas(codigo):
    assert "constante_maiuscula" not in {t for _, t in ast_findings(codigo)}


@pytest.fixture(scope="module")
def chunks():
    docs = DocumentLoader().load_directory(CORPUS)
    return RecursiveChunker().split(docs)


@pytest.mark.parametrize("norma", NORMAS, ids=lambda n: n.id)
def test_cada_norma_esta_em_exatamente_um_chunk_do_corpus(norma, chunks):
    portadores = [c for c in chunks if norma.id in normas_do_chunk(c.text)]
    assert len(portadores) == 1, norma.id


def test_ids_da_familia():
    assert ids_da_familia("pep8-layout") == {"linha_longa", "linhas_em_branco"}
    assert "except_nu" in ids_da_familia("pep8-recomendacoes")


def test_citacao_da_familia_casa_a_secao_certa():
    assert FAMILIAS["pep8-recomendacoes"].search("Programming Recommendations")
    assert FAMILIAS["pep8-nomes"].search("Function and Variable Names")
    assert FAMILIAS["pep8-layout"].search("Maximum Line Length")
    assert FAMILIAS["pep8-imports"].search("Imports")
    assert FAMILIAS["pep8-espacos"].search("Pet Peeves")
    assert FAMILIAS["pep8-comentarios"].search("Inline Comments")
    assert not FAMILIAS["pep8-imports"].search("Maximum Line Length")
    assert not FAMILIAS["pep8-recomendacoes"].search("Exception Names")
