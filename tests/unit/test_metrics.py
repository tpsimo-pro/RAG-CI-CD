"""Testes unitários para evaluation/metrics.py."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from evaluation.metrics import (
    TARGET_F1,
    TARGET_PRECISION,
    TARGET_RECALL,
    AggregatedEvaluation,
    GoldLine,
    LineResult,
    PRGateResult,
    RepetitionResult,
    _SECTION_5_PATTERN,
    check_targets,
    classify_lines,
    confusion_counts,
    normalize_line,
)


@dataclass
class _Det:
    """Dublê mínimo de `DetectionLike`."""

    line_content: str
    norm_reference: str = ""


# ── _SECTION_5_PATTERN ──────────────────────────────────────────────────────


def test_regex_casa_o_nome_de_secao_que_o_corpus_realmente_usa():
    """
    O corpus rotula a norma como "5. Práticas de Código e Idiomas Pythonicos",
    sem a palavra "Seção". O regex antigo exigia "Seção 5" e portanto NUNCA
    casaria uma citação correta — norm_reference_precision saía 0.0 por bug,
    não por desempenho.
    """
    assert _SECTION_5_PATTERN.search(
        "guia_python_pep8.md | Seção: 5. Práticas de Código e Idiomas Pythonicos"
    )
    assert _SECTION_5_PATTERN.search("guia_python_pep8.md — Seção 5")


def test_regex_nao_casa_outras_secoes():
    assert not _SECTION_5_PATTERN.search("guia_python_pep8.md | Seção: 1.1 Tamanho Máximo")
    assert not _SECTION_5_PATTERN.search("coding_standards.md | Seção: Correto")
    assert not _SECTION_5_PATTERN.search("guia_python_pep8.md | Seção: 5.1 Docstrings")


# ── normalize_line (D-003) ──────────────────────────────────────────────────


class TestNormalizeLine:
    def test_remove_espacos_das_bordas(self):
        assert normalize_line("   if x is None:   ") == "if x is None:"

    def test_colapsa_espacos_internos(self):
        assert normalize_line("if   x   is    None:") == "if x is None:"

    def test_colapsa_tabs_internos(self):
        assert normalize_line("if\tx\tis None:") == "if x is None:"

    def test_sensivel_a_maiusculas(self):
        """Código Python: `True` e `true` são coisas distintas."""
        assert normalize_line("if x == True:") != normalize_line("if x == true:")

    def test_string_ja_normalizada_fica_igual(self):
        assert normalize_line("if x is None:") == "if x is None:"


# ── classify_lines ───────────────────────────────────────────────────────────


class TestClassifyLines:
    def test_linha_violadora_sinalizada_vira_tp(self):
        gold = [GoldLine(pr_id="PR-1", line="if x == True:", viola=True)]
        dets = [_Det(line_content="if x == True:")]

        results, total, hallucinated = classify_lines(gold, dets)

        assert len(results) == 1
        assert results[0].cell == "TP"
        assert total == 1
        assert hallucinated == 0

    def test_linha_violadora_nao_sinalizada_vira_fn(self):
        gold = [GoldLine(pr_id="PR-1", line="if x == True:", viola=True)]

        results, total, hallucinated = classify_lines(gold, [])

        assert results[0].cell == "FN"
        assert total == 0
        assert hallucinated == 0

    def test_linha_correta_sinalizada_por_engano_vira_fp(self):
        gold = [GoldLine(pr_id="PR-1", line="if x is not None:", viola=False)]
        dets = [_Det(line_content="if x is not None:")]

        results, _, _ = classify_lines(gold, dets)

        assert results[0].cell == "FP"

    def test_linha_correta_nao_sinalizada_vira_tn(self):
        gold = [GoldLine(pr_id="PR-1", line="if x is not None:", viola=False)]

        results, _, _ = classify_lines(gold, [])

        assert results[0].cell == "TN"

    def test_deteccao_sem_linha_correspondente_e_alucinacao_excluida_da_matriz(self):
        """
        Uma detecção cujo `line_content` não bate com nenhuma linha do
        gabarito não pode virar FP — isso quebraria TP+FP+FN+TN == N
        (D-003). É excluída da matriz e contada à parte.
        """
        gold = [GoldLine(pr_id="PR-1", line="if x is not None:", viola=False)]
        dets = [_Det(line_content="esta linha nem existe no PR")]

        results, total, hallucinated = classify_lines(gold, dets)

        assert results[0].cell == "TN"  # não virou FP
        assert total == 1
        assert hallucinated == 1

    def test_deteccoes_duplicadas_na_mesma_linha_sao_deduplicadas(self):
        """
        Duas detecções apontando para a MESMA linha não devem produzir dois
        TPs — só existe uma linha no gabarito para classificar.
        """
        gold = [GoldLine(pr_id="PR-1", line="if x == True:", viola=True)]
        dets = [
            _Det(line_content="if x == True:"),
            _Det(line_content="if x == True:"),  # duplicata
        ]

        results, total, hallucinated = classify_lines(gold, dets)

        assert len(results) == 1
        assert results[0].cell == "TP"
        assert total == 2  # ambas as detecções são contadas no total...
        assert hallucinated == 0  # ...mas nenhuma é alucinação

    def test_normalizacao_ignora_diferenca_de_espacamento_entre_deteccao_e_gabarito(self):
        gold = [GoldLine(pr_id="PR-1", line="if x == True:", viola=True)]
        dets = [_Det(line_content="  if   x == True:  ")]  # espaçamento diferente

        results, _, hallucinated = classify_lines(gold, dets)

        assert results[0].cell == "TP"
        assert hallucinated == 0

    def test_cites_section_5_e_none_para_fp_fn_tn(self):
        gold = [
            GoldLine(pr_id="PR-1", line="fn viola", viola=True),  # FN
            GoldLine(pr_id="PR-1", line="fn correta", viola=False),  # TN
        ]
        results, _, _ = classify_lines(gold, [])
        for r in results:
            assert r.cites_section_5 is None

    def test_cites_section_5_verdadeiro_quando_tp_cita_secao_5(self):
        gold = [GoldLine(pr_id="PR-1", line="if x == True:", viola=True)]
        dets = [
            _Det(
                line_content="if x == True:",
                norm_reference="guia_python_pep8.md | Seção: 5. Práticas",
            )
        ]

        results, _, _ = classify_lines(gold, dets)

        assert results[0].cell == "TP"
        assert results[0].cites_section_5 is True

    def test_cites_section_5_falso_quando_tp_cita_outra_secao(self):
        gold = [GoldLine(pr_id="PR-1", line="if x == True:", viola=True)]
        dets = [
            _Det(
                line_content="if x == True:",
                norm_reference="coding_standards.md | Seção: Correto",
            )
        ]

        results, _, _ = classify_lines(gold, dets)

        assert results[0].cell == "TP"
        assert results[0].cites_section_5 is False

    def test_multiplas_linhas_do_gabarito_sao_classificadas_independentemente(self):
        gold = [
            GoldLine(pr_id="PR-1", line="if x == True:", viola=True),
            GoldLine(pr_id="PR-1", line="if y is not None:", viola=False),
            GoldLine(pr_id="PR-1", line="if z != None:", viola=True),
        ]
        dets = [_Det(line_content="if x == True:")]  # só a primeira é sinalizada

        results, _, _ = classify_lines(gold, dets)

        cells = {r.line: r.cell for r in results}
        assert cells["if x == True:"] == "TP"
        assert cells["if y is not None:"] == "TN"
        assert cells["if z != None:"] == "FN"


# ── confusion_counts ─────────────────────────────────────────────────────────


def test_confusion_counts_conta_cada_celula():
    assert confusion_counts(["TP", "TP", "FP", "FN", "TN", "TN", "TN"]) == {
        "tp": 2,
        "fp": 1,
        "fn": 1,
        "tn": 3,
    }


def test_confusion_counts_lista_vazia():
    assert confusion_counts([]) == {"tp": 0, "fp": 0, "fn": 0, "tn": 0}


# ── RepetitionResult ──────────────────────────────────────────────────────────


def _line_result(pr_id: str, cell: str, viola: bool | None = None, signaled: bool | None = None) -> LineResult:
    if viola is None:
        viola = cell in ("TP", "FN")
    if signaled is None:
        signaled = cell in ("TP", "FP")
    return LineResult(
        pr_id=pr_id,
        line=f"linha-{cell}",
        expected_viola=viola,
        sub_regra=None,
        hard_negative=False,
        signaled=signaled,
        cell=cell,
        cites_section_5=True if cell == "TP" else None,
    )


class TestRepetitionResult:
    def test_invariante_tp_fp_fn_tn_bate_com_n(self):
        results = [
            _line_result("PR-1", "TP"),
            _line_result("PR-1", "FP"),
            _line_result("PR-1", "FN"),
            _line_result("PR-1", "TN"),
        ]
        rep = RepetitionResult(repetition_index=0, line_results=results)
        assert rep.n == 4
        assert rep.confusion_matrix == {"tp": 1, "fp": 1, "fn": 1, "tn": 1, "n": 4}

    def test_invariante_violada_levanta_assertion_error(self):
        """
        Um `LineResult` com `cell` fora de {"TP","FP","FN","TN"} quebraria a
        soma sem quebrar `len(line_results)` — a asserção explícita existe
        para pegar exatamente esse tipo de bug, não só o caminho feliz.
        """
        bad = LineResult(
            pr_id="PR-1",
            line="x",
            expected_viola=True,
            sub_regra=None,
            hard_negative=False,
            signaled=True,
            cell="BOGUS",
            cites_section_5=None,
        )
        with pytest.raises(AssertionError):
            RepetitionResult(repetition_index=0, line_results=[bad])

    def test_precision_recall_f1(self):
        results = [
            _line_result("PR-1", "TP"),
            _line_result("PR-1", "TP"),
            _line_result("PR-1", "FP"),
            _line_result("PR-1", "FN"),
        ]
        rep = RepetitionResult(repetition_index=0, line_results=results)
        assert rep.precision == pytest.approx(2 / 3)
        assert rep.recall == pytest.approx(2 / 3)
        assert rep.f1 == pytest.approx(2 / 3)

    def test_precision_recall_f1_sao_zero_sem_denominador(self):
        results = [_line_result("PR-1", "TN"), _line_result("PR-1", "TN")]
        rep = RepetitionResult(repetition_index=0, line_results=results)
        assert rep.precision == 0.0
        assert rep.recall == 0.0
        assert rep.f1 == 0.0

    def test_accuracy(self):
        results = [
            _line_result("PR-1", "TP"),
            _line_result("PR-1", "TN"),
            _line_result("PR-1", "TN"),
            _line_result("PR-1", "FP"),
        ]
        rep = RepetitionResult(repetition_index=0, line_results=results)
        assert rep.accuracy == pytest.approx(3 / 4)

    def test_hallucination_rate(self):
        rep = RepetitionResult(
            repetition_index=0,
            line_results=[_line_result("PR-1", "TP")],
            total_detections=4,
            hallucinated_detections=1,
        )
        assert rep.hallucination_rate == pytest.approx(0.25)

    def test_hallucination_rate_zero_sem_deteccoes(self):
        rep = RepetitionResult(repetition_index=0, line_results=[])
        assert rep.hallucination_rate == 0.0

    def test_norm_reference_precision_none_sem_tps(self):
        rep = RepetitionResult(
            repetition_index=0, line_results=[_line_result("PR-1", "TN")]
        )
        assert rep.norm_reference_precision is None

    def test_norm_reference_precision_fracao_correta(self):
        tp_certo = _line_result("PR-1", "TP")  # cites_section_5=True por default
        tp_errado = LineResult(
            pr_id="PR-1",
            line="tp-errado",
            expected_viola=True,
            sub_regra=None,
            hard_negative=False,
            signaled=True,
            cell="TP",
            cites_section_5=False,
        )
        rep = RepetitionResult(repetition_index=0, line_results=[tp_certo, tp_errado])
        assert rep.norm_reference_precision == pytest.approx(0.5)

    def test_pr_gate_results_positivo_quando_qualquer_linha_viola_e_sinalizada(self):
        results = [
            _line_result("PR-1", "TP"),
            _line_result("PR-1", "TN"),
            _line_result("PR-2", "FN"),  # violava mas não foi sinalizada
        ]
        rep = RepetitionResult(repetition_index=0, line_results=results)
        gates = {g.pr_id: g for g in rep.pr_gate_results()}

        assert gates["PR-1"].expected_positive is True
        assert gates["PR-1"].predicted_positive is True
        assert gates["PR-1"].cell == "TP"

        assert gates["PR-2"].expected_positive is True
        assert gates["PR-2"].predicted_positive is False
        assert gates["PR-2"].cell == "FN"

    def test_pr_gate_confusion_matrix_agrega_por_pr_nao_por_linha(self):
        results = [
            _line_result("PR-1", "TP"),
            _line_result("PR-1", "TP"),  # mesmo PR, não deve contar 2 PRs
            _line_result("PR-2", "TN"),
        ]
        rep = RepetitionResult(repetition_index=0, line_results=results)
        matrix = rep.pr_gate_confusion_matrix()
        assert matrix["n"] == 2  # 2 PRs, não 3 linhas


# ── PRGateResult ──────────────────────────────────────────────────────────────


class TestPRGateResult:
    @pytest.mark.parametrize(
        "expected_positive,predicted_positive,cell",
        [
            (True, True, "TP"),
            (True, False, "FN"),
            (False, True, "FP"),
            (False, False, "TN"),
        ],
    )
    def test_cell(self, expected_positive, predicted_positive, cell):
        g = PRGateResult(
            pr_id="PR-1",
            expected_positive=expected_positive,
            predicted_positive=predicted_positive,
        )
        assert g.cell == cell


# ── AggregatedEvaluation (D-005) ──────────────────────────────────────────────


class TestAggregatedEvaluation:
    def test_requer_ao_menos_uma_repeticao(self):
        with pytest.raises(ValueError):
            AggregatedEvaluation(repetitions=[])

    def test_media_e_desvio_padrao_entre_repeticoes(self):
        reps = [
            RepetitionResult(
                repetition_index=i,
                line_results=[_line_result("PR-1", "TP") for _ in range(n)]
                + [_line_result("PR-1", "FN") for _ in range(4 - n)],
            )
            for i, n in enumerate([2, 3, 4])  # recall 0.5, 0.75, 1.0
        ]
        agg = AggregatedEvaluation(repetitions=reps)
        assert agg.recall_mean == pytest.approx((0.5 + 0.75 + 1.0) / 3)
        assert agg.recall_stdev > 0.0

    def test_stdev_e_zero_com_uma_unica_repeticao(self):
        rep = RepetitionResult(
            repetition_index=0, line_results=[_line_result("PR-1", "TP")]
        )
        agg = AggregatedEvaluation(repetitions=[rep])
        assert agg.precision_stdev == 0.0
        assert agg.recall_stdev == 0.0
        assert agg.f1_stdev == 0.0

    def test_median_f1_repetition_numero_impar_pega_o_elemento_central(self):
        baixo = RepetitionResult(
            repetition_index=0, line_results=[_line_result("PR-1", "FN")]
        )
        medio = RepetitionResult(
            repetition_index=1,
            line_results=[_line_result("PR-1", "TP"), _line_result("PR-1", "FN")],
        )
        alto = RepetitionResult(
            repetition_index=2, line_results=[_line_result("PR-1", "TP")]
        )
        agg = AggregatedEvaluation(repetitions=[alto, baixo, medio])
        assert agg.median_f1_repetition is medio

    def test_median_f1_repetition_numero_par_pega_a_mediana_inferior(self):
        """Com N par, a escolha precisa ser determinística — não pode depender da ordem de execução."""
        f1_zero_a = RepetitionResult(
            repetition_index=0, line_results=[_line_result("PR-1", "FN")]
        )
        f1_zero_b = RepetitionResult(
            repetition_index=1, line_results=[_line_result("PR-2", "FN")]
        )
        f1_um_a = RepetitionResult(
            repetition_index=2, line_results=[_line_result("PR-1", "TP")]
        )
        f1_um_b = RepetitionResult(
            repetition_index=3, line_results=[_line_result("PR-2", "TP")]
        )
        agg = AggregatedEvaluation(
            repetitions=[f1_um_a, f1_zero_a, f1_um_b, f1_zero_b]
        )
        # Duas centrais empatam em f1=0.0 (ordenado: zero_a, zero_b, um_a, um_b
        # ou equivalente) — mediana inferior é determinística por `sorted`
        # ser estável, não por reordenar os empates.
        escolhida = agg.median_f1_repetition
        assert escolhida.f1 == 0.0


# ── check_targets ─────────────────────────────────────────────────────────────


class TestCheckTargets:
    def test_todas_as_metas_atingidas(self):
        checks = check_targets(TARGET_PRECISION, TARGET_RECALL, TARGET_F1)
        assert checks == {"precision": True, "recall": True, "f1": True, "all": True}

    def test_uma_meta_nao_atingida_derruba_all(self):
        checks = check_targets(TARGET_PRECISION, TARGET_RECALL - 0.01, TARGET_F1)
        assert checks["recall"] is False
        assert checks["all"] is False

    def test_nenhuma_meta_atingida(self):
        checks = check_targets(0.0, 0.0, 0.0)
        assert checks == {
            "precision": False,
            "recall": False,
            "f1": False,
            "all": False,
        }
