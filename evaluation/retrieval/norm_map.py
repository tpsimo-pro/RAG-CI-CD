"""
norm_map.py — Chaves normativas estáveis para a avaliação de retrieval.

O gabarito de retrieval NÃO pode ser ancorado em `chunk_id`: os ids mudam
quando o chunker muda, e a ablação compara justamente configurações de
chunking diferentes. As chaves aqui definidas são estáveis entre
configurações, tornando `recall@k` comparável entre L0 e L4.

Este módulo é INSTRUMENTAÇÃO DE AVALIAÇÃO. O sistema em produção não o usa
e não deve passar a usá-lo: as chaves descrevem o gabarito, não o
comportamento do revisor.
"""

from __future__ import annotations

import re

NORM_BOOLEANO = "pep8:secao-5:comparacao-booleana"
NORM_NULO = "pep8:secao-5:comparacao-nulo"

# Um chunk carrega a chave quando contém o ENUNCIADO da norma. Casar o
# enunciado (e não apenas o exemplo) evita que um trecho que só mencione
# `== True` de passagem seja contado como portador da norma.
_PADRAO_BOOLEANO = re.compile(
    r"compare?\s+valores\s+booleanos|compara[çc][õo]es\s+booleanas",
    re.IGNORECASE,
)
_PADRAO_NULO = re.compile(
    r"compara[çc][õo]es\s+de\s+nulos|ao\s+comparar\s+com\s+none",
    re.IGNORECASE,
)


def norm_keys_of_chunk(text: str) -> set[str]:
    """
    Retorna as chaves normativas que este chunk carrega.

    Args:
        text: Texto integral do chunk recuperado.

    Returns:
        Conjunto de chaves; vazio se o chunk não contém nenhuma norma do piloto.
    """
    chaves: set[str] = set()
    if _PADRAO_BOOLEANO.search(text):
        chaves.add(NORM_BOOLEANO)
    if _PADRAO_NULO.search(text):
        chaves.add(NORM_NULO)
    return chaves
