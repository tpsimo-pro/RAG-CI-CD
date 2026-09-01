"""
metrics.py — Matriz de confusão e métricas de classificação do RAG-Reviewer.

Unidade de avaliação (D-001, `docs/DECISIONS.md`): cada **linha adicionada**
de um PR do dataset é uma instância binária — "viola a regra do piloto" ou
"não viola". O sistema é avaliado como um classificador dessas linhas:

    | | Sistema sinalizou | Sistema não sinalizou |
    |---|---|---|
    | **Linha viola**     | TP | FN |
    | **Linha não viola** | FP | TN |

Critério de atribuição detecção→linha (D-003): uma violação retornada pelo
LLM é atribuída a uma linha adicionada apenas quando os dois textos
coincidem **exatamente** após normalização (strip + colapso de espaço/tab
interno), com distinção de maiúsculas/minúsculas. Uma detecção sem
correspondência é uma **alucinação de localização**: é excluída da matriz
(preserva TP+FP+FN+TN == N) e contabilizada à parte.

Este módulo é deliberadamente puro — sem I/O, sem `rich`, sem dependência de
`rag_reviewer` — para que a lógica de classificação seja testável de forma
isolada. A integração com Qdrant/Groq (via `rag_reviewer/`) e a apresentação
dos resultados vivem em `evaluation/run_evaluation.py`.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

# ── Metas do TCC (§15.3 do planejamento) ────────────────────────────────────

TARGET_PRECISION = 0.70
TARGET_RECALL = 0.65
TARGET_F1 = 0.67

# Reconhece "Seção 5" / "Secão 5" / "seção 5.x" / "section 5" (case-insensitive).
_SECTION_5_PATTERN = re.compile(r"se[cç][aã]o\s*5\b|section\s*5\b", re.IGNORECASE)


# ── Normalização (D-003) ────────────────────────────────────────────────────


def normalize_line(text: str) -> str:
    """
    Normaliza uma linha de código para comparação exata (D-003).

    1. Remove espaços no início e no fim.
    2. Colapsa sequências internas de espaço/tab em um único espaço.

    Sensível a maiúsculas/minúsculas — o objeto avaliado é código Python,
    onde `True` e `true` são coisas distintas.
    """
    return re.sub(r"[ \t]+", " ", text.strip())


# ── Modelos de dados: entrada ────────────────────────────────────────────────


@dataclass(frozen=True)
class GoldLine:
    """Uma linha adicionada rotulada no gabarito (item de `added_lines` do dataset)."""

    pr_id: str
    line: str
    viola: bool
    sub_regra: str | None = None
    hard_negative: bool = False

    @property
    def normalized(self) -> str:
        return normalize_line(self.line)


class DetectionLike(Protocol):
    """
    Forma mínima de uma violação retornada pelo LLM, usada na atribuição.

    Compatível tanto com `rag_reviewer.llm_client.Violation` quanto com
    dicts equivalentes — `metrics.py` não importa `rag_reviewer` para
    permanecer testável sem as dependências de rede do sistema real.
    """

    line_content: str
    norm_reference: str


# ── Modelos de dados: resultado por linha ───────────────────────────────────


@dataclass(frozen=True)
class LineResult:
    """Classificação (TP/FP/FN/TN) de uma única linha adicionada."""

    pr_id: str
    line: str
    expected_viola: bool
    sub_regra: str | None
    hard_negative: bool
    signaled: bool
    cell: str
    """Uma de: "TP" | "FP" | "FN" | "TN"."""

    cites_section_5: bool | None
    """
    Só definido para TPs: se a detecção atribuída a esta linha citou a
    Seção 5 na `norm_reference`. `None` para FP/FN/TN, onde a pergunta não
    se aplica (D-003: citação da norma não condiciona o TP).
    """


def classify_lines(
    gold_lines: Sequence[GoldLine],
    detections: Sequence[DetectionLike],
) -> tuple[list[LineResult], int, int]:
    """
    Classifica cada linha adicionada de um PR e conta as alucinações.

    Args:
        gold_lines: Linhas adicionadas rotuladas do PR (o gabarito).
        detections: Violações retornadas pelo LLM para esse PR.

    Returns:
        Tupla (line_results, total_detections, hallucinated_detections).
        `line_results` tem exatamente `len(gold_lines)` elementos — a
        invariante TP+FP+FN+TN == N é garantida por construção aqui e
        reverificada explicitamente em `RepetitionResult`.
    """
    # Agrupa linhas do gabarito por texto normalizado (podem existir
    # múltiplas linhas com o mesmo texto — cada uma é uma instância própria).
    gold_by_norm: dict[str, list[int]] = defaultdict(list)
    for i, gl in enumerate(gold_lines):
        gold_by_norm[gl.normalized].append(i)

    signaled_norms: set[str] = set()
    cites_section_5_by_norm: dict[str, bool] = defaultdict(bool)
    hallucinated = 0
    total = 0

    for det in detections:
        total += 1
        norm = normalize_line(det.line_content)
        if norm not in gold_by_norm:
            # LLM alucinou a localização: não corresponde a nenhuma linha
            # adicionada. Excluída da matriz (D-003) — contada à parte.
            hallucinated += 1
            continue
        signaled_norms.add(norm)
        if _SECTION_5_PATTERN.search(det.norm_reference or ""):
            cites_section_5_by_norm[norm] = True

    results: list[LineResult] = []
    for gl in gold_lines:
        signaled = gl.normalized in signaled_norms
        if gl.viola and signaled:
            cell = "TP"
        elif gl.viola and not signaled:
            cell = "FN"
        elif not gl.viola and signaled:
            cell = "FP"
        else:
            cell = "TN"

        cites_section_5 = cites_section_5_by_norm.get(gl.normalized, False) if cell == "TP" else None

        results.append(
            LineResult(
                pr_id=gl.pr_id,
                line=gl.line,
                expected_viola=gl.viola,
                sub_regra=gl.sub_regra,
                hard_negative=gl.hard_negative,
                signaled=signaled,
                cell=cell,
                cites_section_5=cites_section_5,
            )
        )

    return results, total, hallucinated


# ── Agregação a nível de PR (gate de CI/CD) ─────────────────────────────────


@dataclass(frozen=True)
class PRGateResult:
    """
    Classificação de um PR inteiro como unidade de decisão de CI/CD.

    Um PR é positivo se contém ao menos uma linha que viola; o sistema
    "bloqueia" se sinalizou ao menos uma linha do PR (métrica complementar
    de D-001 — "o gate de CI/CD tomaria a decisão certa neste PR?").
    """

    pr_id: str
    expected_positive: bool
    predicted_positive: bool

    @property
    def cell(self) -> str:
        if self.expected_positive and self.predicted_positive:
            return "TP"
        if self.expected_positive and not self.predicted_positive:
            return "FN"
        if not self.expected_positive and self.predicted_positive:
            return "FP"
        return "TN"


def confusion_counts(cells: Sequence[str]) -> dict[str, int]:
    """Conta ocorrências de cada célula ("TP"/"FP"/"FN"/"TN") em uma sequência."""
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for cell in cells:
        counts[cell.lower()] += 1
    return counts


# ── Resultado de uma execução completa do dataset (uma repetição) ──────────


@dataclass
class RepetitionResult:
    """
    Resultado de uma repetição completa da avaliação (todos os PRs).

    D-005 exige `--repeticoes` execuções completas e independentes do
    dataset (por padrão 3), cada uma produzindo seu próprio conjunto de
    métricas. `AggregatedEvaluation` combina várias `RepetitionResult`.
    """

    repetition_index: int
    line_results: list[LineResult] = field(default_factory=list)
    total_detections: int = 0
    hallucinated_detections: int = 0

    def __post_init__(self) -> None:
        self._validate_invariant()

    def _validate_invariant(self) -> None:
        """
        TP + FP + FN + TN == N (total de linhas avaliadas) — D-003.

        Se alucinações fossem contadas como FP, essa soma ultrapassaria N e
        o resultado deixaria de ser uma matriz de confusão. Tratada como
        asserção explícita, não apenas como consequência implícita do código.
        """
        total_cells = self.tp + self.fp + self.fn + self.tn
        n = len(self.line_results)
        assert total_cells == n, (
            f"Invariante TP+FP+FN+TN == N violada na repetição "
            f"{self.repetition_index}: {total_cells} != {n}"
        )

    # ── Contagens brutas ─────────────────────────────────────────────────

    @property
    def n(self) -> int:
        return len(self.line_results)

    @property
    def tp(self) -> int:
        return sum(1 for r in self.line_results if r.cell == "TP")

    @property
    def fp(self) -> int:
        return sum(1 for r in self.line_results if r.cell == "FP")

    @property
    def fn(self) -> int:
        return sum(1 for r in self.line_results if r.cell == "FN")

    @property
    def tn(self) -> int:
        return sum(1 for r in self.line_results if r.cell == "TN")

    @property
    def confusion_matrix(self) -> dict[str, int]:
        return {"tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn, "n": self.n}

    # ── Métricas primárias (classe positiva) ────────────────────────────

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    # ── Métricas secundárias ─────────────────────────────────────────────

    @property
    def accuracy(self) -> float:
        """
        Acurácia — SECUNDÁRIA e explicitamente NÃO-REPRESENTATIVA.

        O conjunto é fortemente desbalanceado (~80% de linhas negativas,
        D-004); a acurácia fica artificialmente alta e não discrimina
        desempenho. Reportada por completude metodológica (D-001).
        """
        return (self.tp + self.tn) / self.n if self.n else 0.0

    @property
    def hallucination_rate(self) -> float:
        """Fração das detecções cujo `line_content` não casou com nenhuma linha adicionada."""
        return (
            self.hallucinated_detections / self.total_detections
            if self.total_detections
            else 0.0
        )

    @property
    def norm_reference_precision(self) -> float | None:
        """
        Fração dos TPs cuja `norm_reference` citou corretamente a Seção 5.

        `None` quando não há TPs — a pergunta não tem denominador definível
        nesse caso (não confundir com 0.0, que afirmaria "citou tudo errado").
        """
        tps = [r for r in self.line_results if r.cell == "TP"]
        if not tps:
            return None
        correct = sum(1 for r in tps if r.cites_section_5)
        return correct / len(tps)

    # ── Agregação a nível de PR (gate de CI/CD) ─────────────────────────

    def pr_gate_results(self) -> list[PRGateResult]:
        """Deriva a classificação por PR a partir das linhas desta repetição."""
        by_pr: dict[str, list[LineResult]] = defaultdict(list)
        for r in self.line_results:
            by_pr[r.pr_id].append(r)

        gate_results = [
            PRGateResult(
                pr_id=pr_id,
                expected_positive=any(r.expected_viola for r in lines),
                predicted_positive=any(r.signaled for r in lines),
            )
            for pr_id, lines in by_pr.items()
        ]

        counts = confusion_counts([g.cell for g in gate_results])
        total = sum(counts.values())
        assert total == len(gate_results), (
            "Invariante TP+FP+FN+TN == N (nível de PR) violada na repetição "
            f"{self.repetition_index}: {total} != {len(gate_results)}"
        )
        return gate_results

    def pr_gate_confusion_matrix(self) -> dict[str, int]:
        gate_results = self.pr_gate_results()
        counts = confusion_counts([g.cell for g in gate_results])
        counts["n"] = len(gate_results)
        return counts


# ── Agregação entre repetições (D-005) ──────────────────────────────────────


@dataclass
class AggregatedEvaluation:
    """
    Combina as `repeticoes` execuções completas do dataset (D-005).

    Reporta média ± desvio-padrão de Precisão/Recall/F1 entre as repetições.
    A matriz de confusão (linha e PR) publicada é a da repetição de **F1
    mediano**, não a média — médias de matrizes de confusão discretas não
    são inteiras e perderiam a interpretação de contagem.
    """

    repetitions: list[RepetitionResult]

    def __post_init__(self) -> None:
        if not self.repetitions:
            raise ValueError("AggregatedEvaluation requer ao menos uma repetição.")

    @property
    def precision_mean(self) -> float:
        return statistics.mean(r.precision for r in self.repetitions)

    @property
    def precision_stdev(self) -> float:
        return self._stdev(r.precision for r in self.repetitions)

    @property
    def recall_mean(self) -> float:
        return statistics.mean(r.recall for r in self.repetitions)

    @property
    def recall_stdev(self) -> float:
        return self._stdev(r.recall for r in self.repetitions)

    @property
    def f1_mean(self) -> float:
        return statistics.mean(r.f1 for r in self.repetitions)

    @property
    def f1_stdev(self) -> float:
        return self._stdev(r.f1 for r in self.repetitions)

    @property
    def median_f1_repetition(self) -> RepetitionResult:
        """
        Repetição escolhida para publicar as matrizes de confusão (D-005).

        Com número ímpar de repetições (o padrão, 3), é o elemento central.
        Com número par, escolhe deterministicamente a de menor F1 entre as
        duas centrais (mediana inferior), para que o resultado publicado
        não dependa da ordem de execução.
        """
        ordered = sorted(self.repetitions, key=lambda r: r.f1)
        mid = len(ordered) // 2
        if len(ordered) % 2 == 1:
            return ordered[mid]
        return ordered[mid - 1]

    @staticmethod
    def _stdev(values: Iterable[float]) -> float:
        values_list = list(values)
        if len(values_list) < 2:
            return 0.0
        return statistics.stdev(values_list)


# ── Metas do TCC ─────────────────────────────────────────────────────────────


def check_targets(precision: float, recall: float, f1: float) -> dict[str, bool]:
    """Verifica as métricas médias contra as metas de §15.3 do planejamento."""
    checks = {
        "precision": precision >= TARGET_PRECISION,
        "recall": recall >= TARGET_RECALL,
        "f1": f1 >= TARGET_F1,
    }
    checks["all"] = all(checks.values())
    return checks
