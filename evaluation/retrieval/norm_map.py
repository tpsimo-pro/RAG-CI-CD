"""
norm_map.py — Chaves normativas estáveis para a avaliação de retrieval.

O gabarito de retrieval NÃO pode ser ancorado em `chunk_id`: os ids mudam
quando o chunker muda, e a ablação compara justamente configurações de
chunking diferentes. A chave de uma norma é o seu id no catálogo
(`evaluation/dataset/norms.py`), estável entre configurações, o que torna
`recall@k` comparável entre elas.

Um chunk carrega a chave quando contém o ENUNCIADO da norma na PEP 8
(`docs/style_guides/pep-0008.md`), não apenas um exemplo. Isso evita que um
trecho que só mencione `== True` de passagem seja contado como portador da
norma. Quebras de linha e recuos do Markdown valem como espaço.

Este módulo é INSTRUMENTAÇÃO DE AVALIAÇÃO. O sistema em produção não o usa
e não deve passar a usá-lo: as chaves descrevem o gabarito, não o
comportamento do revisor.
"""

from __future__ import annotations

from evaluation.dataset.norms import normas_do_chunk


def norm_keys_of_chunk(text: str) -> set[str]:
    """
    Retorna as chaves normativas que este chunk carrega.

    Args:
        text: Texto integral do chunk recuperado.

    Returns:
        Conjunto de ids de norma; vazio se o chunk não contém nenhuma norma
        do catálogo.
    """
    return normas_do_chunk(text)
