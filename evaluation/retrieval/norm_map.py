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
NORM_NOME_FUNCAO = "nomenclatura:funcao"
NORM_NOME_CLASSE = "nomenclatura:classe"
NORM_NOME_PROIBIDO = "nomenclatura:nome-proibido"
NORM_EXCECAO = "coding:secao-4.1:captura-excecao"

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
# A regra de nomenclatura aparece em dois guias do corpus, consistente nas tres
# sub-regras: guia_python_pep8.md (Secao 2 e 2.1) e coding_standards.md
# (2.1 e 2.2). Um chunk de qualquer um dos dois carrega a norma.
_PADRAO_NOME_FUNCAO = re.compile(
    r"\|\s*(?:Fun[çc][õo]es\s+e\s+Vari[áa]veis|Vari[áa]veis\s+e\s+fun[çc][õo]es)"
    r"\s*\|\s*`?snake_case",
    re.IGNORECASE,
)
_PADRAO_NOME_CLASSE = re.compile(r"\|\s*Classes\s*\|\s*`?PascalCase", re.IGNORECASE)
_PADRAO_NOME_PROIBIDO = re.compile(
    r"Nomes\s+de\s+1\s+caractere|nomes\s+de\s+uma\s+[úu]nica\s+letra",
    re.IGNORECASE,
)
# Emenda 2 de D-002: a norma so existe no coding_standards.md, 4.1.
_PADRAO_EXCECAO = re.compile(
    r"capturar\s+`?Exception`?\s+gen[ée]rica|toda\s+exce[çc][ãa]o\s+capturada",
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
    if _PADRAO_NOME_FUNCAO.search(text):
        chaves.add(NORM_NOME_FUNCAO)
    if _PADRAO_NOME_CLASSE.search(text):
        chaves.add(NORM_NOME_CLASSE)
    if _PADRAO_NOME_PROIBIDO.search(text):
        chaves.add(NORM_NOME_PROIBIDO)
    if _PADRAO_EXCECAO.search(text):
        chaves.add(NORM_EXCECAO)
    return chaves
