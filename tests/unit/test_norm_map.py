import json

from evaluation.retrieval.gold import build_gold
from evaluation.retrieval.norm_map import (
    NORM_BOOLEANO,
    NORM_EXCECAO,
    NORM_NULO,
    norm_keys_of_chunk,
)


def test_chunk_com_norma_booleana_e_reconhecido():
    texto = (
        "5. Práticas de Código\n"
        "Comparações booleanas: Não compare valores booleanos com == True ou == False.\n"
        "Correto: if is_valid:\n"
        "Incorreto: if is_valid == True:"
    )
    assert NORM_BOOLEANO in norm_keys_of_chunk(texto)


def test_chunk_com_norma_de_nulos_e_reconhecido():
    texto = (
        "Comparações de nulos: Sempre use is ou is not ao comparar com None.\n"
        "Correto: if value is not None:\n"
        "Incorreto: if value != None:"
    )
    assert NORM_NULO in norm_keys_of_chunk(texto)


def test_chunk_irrelevante_nao_carrega_chave():
    texto = "1.1 Tamanho Máximo de Linha: o limite é de 79 caracteres."
    assert norm_keys_of_chunk(texto) == set()


def test_chunk_unico_pode_carregar_as_duas_chaves():
    texto = (
        "Não compare valores booleanos com == True ou == False.\n"
        "Sempre use is ou is not ao comparar com None."
    )
    assert norm_keys_of_chunk(texto) == {NORM_BOOLEANO, NORM_NULO}


def test_chunk_da_secao_4_1_do_coding_standards_carrega_a_norma():
    texto = (
        "### 4.1 Regras Obrigatórias\n"
        "- **Proibido** capturar `Exception` genérica sem re-raise ou logging.\n"
        "- Toda exceção capturada deve ser logada com `logger.exception()` ou "
        "re-lançada com contexto adicional."
    )
    assert NORM_EXCECAO in norm_keys_of_chunk(texto)


def test_tabela_de_nomenclatura_com_excecoes_nao_carrega_a_norma():
    texto = "| Exceções | `PascalCase` com sufixo `Error` | `InvalidTokenError` |"
    assert NORM_EXCECAO not in norm_keys_of_chunk(texto)


def test_gold_mapeia_as_sub_regras_de_excecao(tmp_path):
    dataset = [{
        "pr_id": "PR-900",
        "added_lines": [
            {"line": "except Exception:", "viola": True,
             "sub_regra": "captura_generica"},
            {"line": "except ValueError:", "viola": True,
             "sub_regra": "captura_silenciosa"},
            {"line": "    pass", "viola": False, "sub_regra": None},
        ],
    }]
    path = tmp_path / "ds.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")

    gold = build_gold(path)

    assert [g.norm_key for g in gold] == [NORM_EXCECAO, NORM_EXCECAO]
