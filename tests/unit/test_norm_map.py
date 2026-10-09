import json

import pytest

from evaluation.retrieval.gold import build_gold
from evaluation.retrieval.norm_map import norm_keys_of_chunk


def test_chunk_com_norma_booleana_e_reconhecido():
    texto = (
        "- Don't compare boolean values to True or False using `==`:\n"
        "  Correct: if greeting:\n"
        "  Wrong: if greeting == True:"
    )
    assert "booleano" in norm_keys_of_chunk(texto)


def test_chunk_com_norma_de_nulos_e_reconhecido_apesar_da_quebra_de_linha():
    texto = (
        "- Comparisons to singletons like None should always be done with\n"
        "  `is` or `is not`, never the equality operators."
    )
    assert "nulo" in norm_keys_of_chunk(texto)


def test_chunk_irrelevante_nao_carrega_chave():
    texto = "Use blank lines in functions, sparingly, to indicate sections."
    assert norm_keys_of_chunk(texto) == set()


def test_chunk_unico_pode_carregar_varias_chaves():
    texto = (
        "Don't compare boolean values to True or False using ==.\n"
        "Comparisons to singletons like None should always be done with is."
    )
    assert norm_keys_of_chunk(texto) == {"booleano", "nulo"}


def test_chunk_de_excecoes_carrega_a_norma_do_except_nu():
    texto = (
        "- When catching exceptions, mention specific exceptions whenever\n"
        "  possible instead of using a bare `except:` clause:"
    )
    assert "except_nu" in norm_keys_of_chunk(texto)


def test_excecao_derivada_de_exception_nao_carrega_a_norma():
    texto = "- Derive exceptions from `Exception` rather than `BaseException`."
    assert "except_nu" not in norm_keys_of_chunk(texto)


def _dataset(tmp_path, sub_regra="except_nu"):
    dataset = [
        {
            "pr_id": "PR-900",
            "files": [
                {
                    "filename": "a.py",
                    "added_lines": [
                        {"line": "except:", "viola": True, "sub_regra": sub_regra},
                        {"line": "    pass", "viola": False, "sub_regra": None},
                    ],
                },
                {
                    "filename": "b.py",
                    "added_lines": [
                        {"line": "x=1", "viola": True, "sub_regra": "espaco_operador"},
                    ],
                },
            ],
        }
    ]
    path = tmp_path / "ds.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")
    return path


def test_gold_usa_a_sub_regra_como_chave_e_guarda_o_arquivo(tmp_path):
    gold = build_gold(_dataset(tmp_path))

    assert [(g.pr_id, g.filename, g.norm_key) for g in gold] == [
        ("PR-900", "a.py", "except_nu"),
        ("PR-900", "b.py", "espaco_operador"),
    ]


def test_gold_rejeita_sub_regra_fora_do_catalogo(tmp_path):
    with pytest.raises(ValueError, match="sub_regra desconhecida"):
        build_gold(_dataset(tmp_path, sub_regra="captura_generica"))
