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

NORM_BOOLEANO = "pep8:recomendacoes:comparacao-booleana"
NORM_NULO = "pep8:recomendacoes:comparacao-nulo"
NORM_NOME_FUNCAO = "pep8:nomes:funcao"
NORM_NOME_CLASSE = "pep8:nomes:classe"
NORM_NOME_PROIBIDO = "pep8:nomes:proibido"
NORM_EXCECAO = "pep8:excecoes:except-nu"

# Um chunk carrega a chave quando contém o ENUNCIADO da norma na PEP 8
# (`docs/style_guides/pep-0008.md`). Casar o enunciado (e não apenas o
# exemplo) evita que um trecho que só mencione `== True` de passagem seja
# contado como portador da norma. Quebras de linha e recuos do Markdown
# valem como espaço.
_PADRAO_BOOLEANO = re.compile(
    r"compare\s+boolean\s+values\s+to\s+True\s+or\s+False", re.IGNORECASE
)
_PADRAO_NULO = re.compile(
    r"comparisons\s+to\s+singletons\s+like\s+None", re.IGNORECASE
)
_PADRAO_NOME_FUNCAO = re.compile(
    r"function\s+names\s+should\s+be\s+lowercase", re.IGNORECASE
)
_PADRAO_NOME_CLASSE = re.compile(
    r"class\s+names\s+should\s+normally\s+use\s+the\s+CapWords", re.IGNORECASE
)
_PADRAO_NOME_PROIBIDO = re.compile(
    r"never\s+use\s+the\s+characters\s+'l'", re.IGNORECASE
)
_PADRAO_EXCECAO = re.compile(
    r"mention\s+specific\s+exceptions\s+whenever\s+possible\s+instead\s+of"
    r"\s+using\s+a\s+bare",
    re.IGNORECASE,
)

_PADROES = (
    (NORM_BOOLEANO, _PADRAO_BOOLEANO),
    (NORM_NULO, _PADRAO_NULO),
    (NORM_NOME_FUNCAO, _PADRAO_NOME_FUNCAO),
    (NORM_NOME_CLASSE, _PADRAO_NOME_CLASSE),
    (NORM_NOME_PROIBIDO, _PADRAO_NOME_PROIBIDO),
    (NORM_EXCECAO, _PADRAO_EXCECAO),
)


def norm_keys_of_chunk(text: str) -> set[str]:
    """
    Retorna as chaves normativas que este chunk carrega.

    Args:
        text: Texto integral do chunk recuperado.

    Returns:
        Conjunto de chaves; vazio se o chunk não contém nenhuma norma do piloto.
    """
    return {chave for chave, padrao in _PADROES if padrao.search(text)}
