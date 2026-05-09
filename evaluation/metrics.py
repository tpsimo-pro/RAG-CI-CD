"""
metrics.py — Cálculo de Precision, Recall e F1-Score do RAG-Reviewer.

Compara as violações detectadas pelo sistema com o gabarito do dataset,
produzindo métricas científicas para avaliação do TCC.

Critério de match (True Positive):
    Uma violação detectada é considerada correta (TP) quando:
    - O `line_content` do gabarito é substring da linha detectada, OU
    - A `norm_reference` do gabarito aparece na referência detectada.
    Ambas as condições usam comparação case-insensitive.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvaluationResult:
    """Resultado de avaliação de um único PR."""

    pr_id: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    detected_violations: list[dict] = field(default_factory=list)
    expected_violations: list[dict] = field(default_factory=list)

    @property
    def precision(self) -> float:
        """Fração das violações detectadas que eram reais."""
        denom = self.true_positives + self.false_positives
        if denom == 0:
            return 1.0  # sem detecções = precision perfeita (não "errou")
        return self.true_positives / denom

    @property
    def recall(self) -> float:
        """Fração das violações reais que foram detectadas."""
        denom = self.true_positives + self.false_negatives
        if denom == 0:
            return 1.0  # sem violações esperadas = recall perfeito
        return self.true_positives / denom

    @property
    def f1_score(self) -> float:
        """Média harmônica entre Precision e Recall."""
        denom = self.precision + self.recall
        if denom == 0:
            return 0.0
        return 2 * (self.precision * self.recall) / denom


@dataclass
class AggregatedResult:
    """Resultado agregado de todos os PRs avaliados."""

    pr_results: list[EvaluationResult] = field(default_factory=list)

    @property
    def total_tp(self) -> int:
        return sum(r.true_positives for r in self.pr_results)

    @property
    def total_fp(self) -> int:
        return sum(r.false_positives for r in self.pr_results)

    @property
    def total_fn(self) -> int:
        return sum(r.false_negatives for r in self.pr_results)

    @property
    def macro_precision(self) -> float:
        """Média da precision por PR (macro-average)."""
        if not self.pr_results:
            return 0.0
        return sum(r.precision for r in self.pr_results) / len(self.pr_results)

    @property
    def macro_recall(self) -> float:
        """Média do recall por PR (macro-average)."""
        if not self.pr_results:
            return 0.0
        return sum(r.recall for r in self.pr_results) / len(self.pr_results)

    @property
    def macro_f1(self) -> float:
        """Média do F1-Score por PR (macro-average)."""
        if not self.pr_results:
            return 0.0
        return sum(r.f1_score for r in self.pr_results) / len(self.pr_results)

    @property
    def micro_precision(self) -> float:
        """Precision global (micro-average) considerando todos os TPs/FPs."""
        denom = self.total_tp + self.total_fp
        if denom == 0:
            return 1.0
        return self.total_tp / denom

    @property
    def micro_recall(self) -> float:
        """Recall global (micro-average) considerando todos os TPs/FNs."""
        denom = self.total_tp + self.total_fn
        if denom == 0:
            return 1.0
        return self.total_tp / denom

    @property
    def micro_f1(self) -> float:
        """F1-Score global (micro-average)."""
        denom = self.micro_precision + self.micro_recall
        if denom == 0:
            return 0.0
        return 2 * (self.micro_precision * self.micro_recall) / denom


def match_violation(detected: dict, expected: dict) -> bool:
    """
    Verifica se uma violação detectada corresponde a uma esperada.

    Critérios (basta um ser verdadeiro):
    1. O `line_content` esperado é substring do `line_content` detectado.
    2. A `norm_reference` esperada é substring da `norm_reference` detectada.

    Args:
        detected: Violação retornada pelo sistema (dict com campos Violation).
        expected: Violação do gabarito (dict com campos do dataset JSON).

    Returns:
        True se houver correspondência, False caso contrário.
    """
    detected_line = detected.get("line_content", "").lower()
    detected_ref = detected.get("norm_reference", "").lower()

    expected_line = expected.get("line_content", "").lower()
    expected_ref = expected.get("norm_reference", "").lower()

    line_match = expected_line and expected_line in detected_line
    ref_match = expected_ref and expected_ref in detected_ref

    return bool(line_match or ref_match)


def evaluate_pr(
    pr_id: str,
    detected_violations: list[dict],
    expected_violations: list[dict],
) -> EvaluationResult:
    """
    Avalia as violações detectadas em um PR contra o gabarito.

    Para cada violação esperada, verifica se há ao menos uma detecção
    correspondente (True Positive). Detecções sem correspondência são
    False Positives. Violações esperadas sem correspondência são False
    Negatives.

    Args:
        pr_id: Identificador do PR (ex: "PR-001").
        detected_violations: Lista de dicts com as violações detectadas.
        expected_violations: Lista de dicts do gabarito.

    Returns:
        EvaluationResult com as contagens de TP, FP e FN.
    """
    result = EvaluationResult(
        pr_id=pr_id,
        detected_violations=detected_violations,
        expected_violations=expected_violations,
    )

    matched_detected = set()

    # Para cada violação esperada, procura um match nas detectadas
    for expected in expected_violations:
        found = False
        for i, detected in enumerate(detected_violations):
            if i in matched_detected:
                continue  # já "consumida" por outro match
            if match_violation(detected, expected):
                result.true_positives += 1
                matched_detected.add(i)
                found = True
                break
        if not found:
            result.false_negatives += 1

    # Detecções sem correspondência são FPs
    result.false_positives = len(detected_violations) - len(matched_detected)

    return result


def aggregate_results(results: list[EvaluationResult]) -> AggregatedResult:
    """
    Agrega os resultados individuais de cada PR em métricas globais.

    Args:
        results: Lista de EvaluationResult, um por PR avaliado.

    Returns:
        AggregatedResult com métricas macro e micro.
    """
    return AggregatedResult(pr_results=results)
