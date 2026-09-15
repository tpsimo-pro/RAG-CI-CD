from evaluation.retrieval.gold import GoldLine
from evaluation.retrieval.metrics import (
    RetrievalOutcome,
    context_precision_at_k,
    recall_at_k,
)

NORM = "pep8:secao-5:comparacao-booleana"
OUTRA = "outra:norma"


def _outcome(*ranks: set[str]) -> RetrievalOutcome:
    return RetrievalOutcome(
        gold=GoldLine(pr_id="PR-001", line="if x == True:", norm_key=NORM),
        ranked_norm_keys=list(ranks),
    )


def test_recall_at_k_conta_acerto_em_qualquer_posicao_ate_k():
    # norma certa na 3a posicao
    o = _outcome(set(), {OUTRA}, {NORM})
    assert recall_at_k([o], k=5) == 1.0
    assert recall_at_k([o], k=3) == 1.0
    assert recall_at_k([o], k=2) == 0.0


def test_recall_at_k_e_media_entre_linhas():
    acerta = _outcome({NORM})
    erra = _outcome({OUTRA})
    assert recall_at_k([acerta, erra], k=5) == 0.5


def test_context_precision_mede_fracao_util_do_que_foi_entregue():
    # 1 chunk util entre 4 entregues
    o = _outcome({NORM}, {OUTRA}, set(), set())
    assert context_precision_at_k([o], k=4) == 0.25


def test_metricas_com_lista_vazia_nao_quebram():
    assert recall_at_k([], k=5) == 0.0
    assert context_precision_at_k([], k=5) == 0.0
