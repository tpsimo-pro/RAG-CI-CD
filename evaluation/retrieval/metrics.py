"""
metrics.py — Métricas de recuperação: recall@k, MRR e precisão de contexto.

Todas operam sobre `RetrievalOutcome`, que guarda, para uma linha do
gabarito, as chaves normativas de cada chunk recuperado NA ORDEM do ranking.
Nenhuma métrica aqui depende de `chunk_id`, o que as torna comparáveis entre
configurações de chunking diferentes (spec §6.1).
"""

from __future__ import annotations

from dataclasses import dataclass

from evaluation.retrieval.gold import GoldLine


@dataclass
class RetrievalOutcome:
    """Resultado da recuperação para uma linha do gabarito."""

    gold: GoldLine
    ranked_norm_keys: list[set[str]]
    """Chaves normativas de cada chunk recuperado, na ordem do ranking."""

    def first_hit_rank(self) -> int | None:
        """Posição 1-indexada do primeiro chunk que carrega a norma exigida."""
        for i, keys in enumerate(self.ranked_norm_keys, start=1):
            if self.gold.norm_key in keys:
                return i
        return None


def recall_at_k(outcomes: list[RetrievalOutcome], k: int) -> float:
    """Fração das linhas cuja norma exigida apareceu entre os k primeiros."""
    if not outcomes:
        return 0.0
    acertos = sum(
        1
        for o in outcomes
        if (r := o.first_hit_rank()) is not None and r <= k
    )
    return acertos / len(outcomes)


def mrr(outcomes: list[RetrievalOutcome]) -> float:
    """Mean Reciprocal Rank — distingue achar em 1º de achar em 5º."""
    if not outcomes:
        return 0.0
    total = 0.0
    for o in outcomes:
        rank = o.first_hit_rank()
        if rank is not None:
            total += 1.0 / rank
    return total / len(outcomes)


def context_precision_at_k(outcomes: list[RetrievalOutcome], k: int) -> float:
    """
    Fração dos chunks entregues que carregavam a norma exigida.

    Não é decorativa: chunks-lixo comprovadamente induzem alucinação — o LLM
    passou a acusar linhas inocentes citando "Seção: Correto" (spec §1.1).
    """
    if not outcomes:
        return 0.0
    total = 0.0
    for o in outcomes:
        entregues = o.ranked_norm_keys[:k]
        if not entregues:
            continue
        uteis = sum(1 for keys in entregues if o.gold.norm_key in keys)
        total += uteis / len(entregues)
    return total / len(outcomes)
