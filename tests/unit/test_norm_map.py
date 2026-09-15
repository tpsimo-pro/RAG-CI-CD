from evaluation.retrieval.norm_map import (
    NORM_BOOLEANO,
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
