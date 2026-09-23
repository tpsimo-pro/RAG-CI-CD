"""
metrics.py — Matriz de confusão e métricas de classificação do RAG-Reviewer.

Unidade de avaliação (D-001, `docs/DECISIONS.md`): cada **linha adicionada**
de um PR do dataset é uma instância binária — "viola alguma regra do piloto"
ou "não viola". O sistema é avaliado como um classificador dessas linhas:

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

# Reconhece "Seção 5" / "Seção: 5" / "Secão 5" / "section 5" (case-insensitive),
# mas NÃO subseções ("5.1 Docstrings" pertence a outro documento). O regex
# antigo exigia "Seção" seguida só de espaço antes do "5" — o corpus real usa
# "Seção: 5. ..." (dois-pontos), então NUNCA casava (spec — Task 11).
_SECTION_5_PATTERN = re.compile(
    r"se[cç][aã]o[:\s]*5(?!\.\d)\b|section[:\s]*5(?!\.\d)\b", re.IGNORECASE
)

# Nomenclatura (emenda de D-002). A norma está na Seção 2 do
# `guia_python_pep8.md` (2 e 2.1) e na Seção 2 do `coding_standards.md`
# (2.1 e 2.2) — citar qualquer uma das duas é correto, subseção inclusive,
# ao contrário da Seção 5, onde "5.1 Docstrings" é outro assunto.
_SECTION_2_PATTERN = re.compile(
    r"se[cç][aã]o[:\s]*2(?:\.\d)?\b|section[:\s]*2(?:\.\d)?\b|nomenclatura|naming",
    re.IGNORECASE,
)

REGRA_SECAO_5 = "secao-5"
REGRA_SECAO_2 = "secao-2"

_NORM_PATTERN_POR_REGRA = {
    REGRA_SECAO_5: _SECTION_5_PATTERN,
    REGRA_SECAO_2: _SECTION_2_PATTERN,
}


def cites_norm_of(regra: str | None, norm_reference: str | None) -> bool:
    """
    Se a `norm_reference` de uma detecção aponta a norma da regra violada.

    Regra ausente ou desconhecida nunca conta como citação correta: não há
    norma definida contra a qual comparar.
    """
    pattern = _NORM_PATTERN_POR_REGRA.get(regra or "")
    if pattern is None:
        return False
    return bool(pattern.search(norm_reference or ""))


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
    regra: str | None = None
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
    regra: str | None
    """
    Regra do piloto à qual a linha pertence: "secao-5", "secao-2" ou `None`.

    Positivas trazem a regra violada; negativos difíceis trazem a regra que
    quase violam; negativos comuns são `None` e não pertencem a regra alguma
    (emenda de D-002).
    """

    sub_regra: str | None
    hard_negative: bool
    signaled: bool
    cell: str
    """Uma de: "TP" | "FP" | "FN" | "TN"."""

    cites_correct_norm: bool | None
    """
    Só definido para TPs: se a detecção atribuída a esta linha citou, na
    `norm_reference`, a norma da regra violada (Seção 5 ou Seção 2). `None`
    para FP/FN/TN, onde a pergunta não se aplica (D-003: citação da norma
    não condiciona o TP).
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
    references_by_norm: dict[str, list[str]] = defaultdict(list)
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
        references_by_norm[norm].append(det.norm_reference or "")

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

        cites = (
            any(
                cites_norm_of(gl.regra, ref)
                for ref in references_by_norm.get(gl.normalized, [])
            )
            if cell == "TP"
            else None
        )

        results.append(
            LineResult(
                pr_id=gl.pr_id,
                line=gl.line,
                expected_viola=gl.viola,
                regra=gl.regra,
                sub_regra=gl.sub_regra,
                hard_negative=gl.hard_negative,
                signaled=signaled,
                cell=cell,
                cites_correct_norm=cites,
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


@dataclass(frozen=True)
class RuleMetrics:
    """Matriz e métricas de uma única regra do piloto (ver `RepetitionResult.per_rule`)."""

    regra: str
    line_results: list[LineResult]

    @property
    def confusion_matrix(self) -> dict[str, int]:
        counts = confusion_counts([r.cell for r in self.line_results])
        counts["n"] = len(self.line_results)
        return counts

    @property
    def precision(self) -> float:
        cm = self.confusion_matrix
        denom = cm["tp"] + cm["fp"]
        return cm["tp"] / denom if denom else 0.0

    @property
    def recall(self) -> float:
        cm = self.confusion_matrix
        denom = cm["tp"] + cm["fn"]
        return cm["tp"] / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def norm_reference_precision(self) -> float | None:
        """Fração dos TPs desta regra que citaram a norma dela. `None` sem TPs."""
        tps = [r for r in self.line_results if r.cell == "TP"]
        if not tps:
            return None
        return sum(1 for r in tps if r.cites_correct_norm) / len(tps)

    def as_dict(self) -> dict:
        return {
            "regra": self.regra,
            "confusion_matrix": self.confusion_matrix,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "norm_reference_precision": (
                round(self.norm_reference_precision, 4)
                if self.norm_reference_precision is not None
                else None
            ),
        }


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
        correct = sum(1 for r in tps if r.cites_correct_norm)
        return correct / len(tps)

    # ── Recorte por regra (emenda de D-002) ─────────────────────────────

    def per_rule(self) -> dict[str, RuleMetrics]:
        """
        Métricas restritas às linhas de cada regra do piloto.

        O recorte de uma regra são as linhas cujo campo `regra` é ela: as
        positivas dessa regra e os negativos difíceis escritos contra ela.
        Negativos comuns (`regra=None`) não pertencem a regra alguma e só
        aparecem na matriz global — por isso a soma das matrizes por regra é
        menor que N, e a precisão por regra não é comparável à global (seu
        denominador exclui os FPs em linha sem regra).
        """
        by_rule: dict[str, list[LineResult]] = defaultdict(list)
        for r in self.line_results:
            if r.regra is not None:
                by_rule[r.regra].append(r)
        return {
            regra: RuleMetrics(regra=regra, line_results=lines)
            for regra, lines in sorted(by_rule.items())
        }

    def per_sub_rule_recall(self) -> dict[str, dict[str, int | float]]:
        """
        Recall por sub-regra (`booleano`, `nulo`, `nome_funcao`, ...).

        Só as positivas entram: uma sub-regra não tem negativos próprios
        (o rótulo `sub_regra` é nulo em toda linha que não viola), então
        precisão e F1 não são definíveis neste recorte.
        """
        by_sub: dict[str, list[LineResult]] = defaultdict(list)
        for r in self.line_results:
            if r.expected_viola and r.sub_regra is not None:
                by_sub[r.sub_regra].append(r)
        return {
            sub: {
                "positivas": len(lines),
                "tp": sum(1 for r in lines if r.cell == "TP"),
                "fn": sum(1 for r in lines if r.cell == "FN"),
                "recall": round(sum(1 for r in lines if r.cell == "TP") / len(lines), 4),
            }
            for sub, lines in sorted(by_sub.items())
        }

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

    def per_rule_summary(self) -> dict[str, dict[str, float]]:
        """Média ± desvio de Precisão/Recall/F1 de cada regra entre as repetições."""
        por_regra: dict[str, list[RuleMetrics]] = defaultdict(list)
        for rep in self.repetitions:
            for regra, rm in rep.per_rule().items():
                por_regra[regra].append(rm)

        return {
            regra: {
                "precision_mean": round(statistics.mean(m.precision for m in ms), 4),
                "precision_stdev": round(self._stdev(m.precision for m in ms), 4),
                "recall_mean": round(statistics.mean(m.recall for m in ms), 4),
                "recall_stdev": round(self._stdev(m.recall for m in ms), 4),
                "f1_mean": round(statistics.mean(m.f1 for m in ms), 4),
                "f1_stdev": round(self._stdev(m.f1 for m in ms), 4),
            }
            for regra, ms in sorted(por_regra.items())
        }

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
