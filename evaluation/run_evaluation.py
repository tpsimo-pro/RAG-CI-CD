"""
run_evaluation.py — Script principal de avaliação do RAG-Reviewer.

Executa o sistema **real** (retrieval no Qdrant + geração no Groq, via os
módulos de `rag_reviewer/`) contra o dataset do piloto — Seção 5 do guia de
estilo Python (Comparações booleanas e com `None`, D-002) — e produz a
matriz de confusão completa (TP/FP/FN/TN) e as métricas derivadas definidas
em `docs/DECISIONS.md` (D-001, D-003, D-005).

Este script **não usa mocks**. Se `GROQ_API_KEY` não estiver configurada ou
o Qdrant estiver inacessível, a execução falha com uma mensagem de erro
clara — nunca cai silenciosamente em dados simulados.

Uso:
    python -m evaluation.run_evaluation
    python -m evaluation.run_evaluation --dataset evaluation/dataset/pilot_secao5.json
    python -m evaluation.run_evaluation --repeticoes 1   # desenvolvimento — poupa cota da API
    python -m evaluation.run_evaluation --output evaluation/results.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

# Força UTF-8 na saída padrão, independente do console/codepage do SO.
# Evita depender de `set PYTHONIOENCODING=utf-8` no shell que invoca o
# script (frágil no Windows: `make` só passa por um shell POSIX quando a
# receita contém metacaracteres, e nesse caso caminhos com `\` quebram).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        pass  # stream não suporta reconfigure (ex.: redirecionado de forma incomum)

# Raiz do projeto — garante imports independente do cwd
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import groq  # noqa: E402

from evaluation.metrics import (  # noqa: E402
    TARGET_F1,
    TARGET_PRECISION,
    TARGET_RECALL,
    AggregatedEvaluation,
    GoldLine,
    LineResult,
    RepetitionResult,
    check_targets,
    classify_lines,
)
from rag_reviewer.diff_parser import FileDiff  # noqa: E402
from rag_reviewer.embedder import Embedder  # noqa: E402
from rag_reviewer.llm_client import LLMClient  # noqa: E402
from rag_reviewer.retriever import RetrievedContext, Retriever  # noqa: E402
from rag_reviewer.vector_store import VectorStore  # noqa: E402

console = Console(highlight=False)

_DEFAULT_DATASET = _PROJECT_ROOT / "evaluation" / "dataset" / "pilot_secao5.json"
_DEFAULT_OUTPUT = _PROJECT_ROOT / "evaluation" / "results.json"
_DEFAULT_REPETICOES = 3


# ── Carregamento e validação do dataset ─────────────────────────────────────


def _load_dataset(path: Path) -> list[dict]:
    """
    Carrega e valida a forma mínima do dataset contra o contrato do schema.

    Falha ruidosamente (ValueError) se algum PR ou linha adicionada não tiver
    os campos obrigatórios — não há caminho silencioso para dados malformados.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"Dataset vazio ou em formato inválido: {path}")

    for pr in raw:
        for required in ("pr_id", "filename", "patch", "added_lines"):
            if required not in pr:
                raise ValueError(
                    f"PR malformado em {path} (pr_id={pr.get('pr_id', '?')}): "
                    f"campo obrigatório '{required}' ausente."
                )
        for added_line in pr["added_lines"]:
            for required in ("line", "viola"):
                if required not in added_line:
                    raise ValueError(
                        f"Linha adicionada malformada em {pr['pr_id']}: "
                        f"campo obrigatório '{required}' ausente."
                    )
    return raw


def _build_gold_lines(pr_data: dict) -> list[GoldLine]:
    """Converte `added_lines` do dataset no gabarito tipado (GoldLine)."""
    return [
        GoldLine(
            pr_id=pr_data["pr_id"],
            line=al["line"],
            viola=bool(al["viola"]),
            sub_regra=al.get("sub_regra"),
            hard_negative=bool(al.get("hard_negative", False)),
        )
        for al in pr_data["added_lines"]
    ]


def _build_file_diff(pr_data: dict) -> FileDiff:
    """
    Constrói o FileDiff de produção a partir de um PR do dataset.

    As `added_lines` do FileDiff vêm diretamente do gabarito (D-001 define a
    unidade de avaliação como "os itens de added_lines de cada PR do
    dataset") — o mesmo texto que carrega o rótulo é o que alimenta o
    retriever e o LLM reais, garantindo que se avalia exatamente o que foi
    rotulado.
    """
    added_lines = [al["line"] for al in pr_data["added_lines"]]
    return FileDiff(
        filename=pr_data["filename"],
        patch=pr_data.get("patch", ""),
        status="modified",
        additions=len(added_lines),
        deletions=0,
        added_lines=added_lines,
    )


# ── Pipeline real (sem mocks) ────────────────────────────────────────────────


def _build_pipeline() -> tuple[Retriever, LLMClient]:
    """
    Instancia os componentes reais do sistema via `rag_reviewer/`.

    Nenhuma dependência é mockada: `Embedder` carrega o modelo
    sentence-transformers real, `VectorStore` conecta ao Qdrant real, e
    `LLMClient` chama a API da Groq real. Falhas de configuração ou rede
    propagam como exceção — ver `main()`.
    """
    embedder = Embedder()
    store = VectorStore()
    retriever = Retriever(embedder=embedder, store=store)
    # Temperatura forçada a 0.0 (D-005), independente do que estiver no
    # .env: a avaliação do TCC não deve depender de configuração externa
    # correta para ser determinística.
    llm = LLMClient(temperature=0.0)
    return retriever, llm


def _review_with_backoff(
    llm: LLMClient, context: RetrievedContext, max_attempts: int = 5
) -> list:
    """
    Chama `llm.review`, reagindo a 429 (rate limit) do Groq com espera e
    nova tentativa — não é um bug do pipeline, é o teto de tokens/minuto do
    plano gratuito (D-006). Sem isso, `--repeticoes 3` em 30 PRs sequenciais
    estoura o limite e a avaliação falha antes de terminar (falha alta,
    conforme o script já faz — aqui só se dá mais chances antes de desistir).

    Usa o tempo sugerido pela própria API (`retry_after`) quando disponível;
    senão, um recuo fixo de 20s.
    """
    for attempt in range(max_attempts):
        try:
            return llm.review(context)
        except groq.RateLimitError as exc:
            if attempt == max_attempts - 1:
                raise
            retry_after = exc.response.headers.get("retry-after")
            espera = float(retry_after) if retry_after else 20.0
            console.log(
                f"[yellow]⚠️  Rate limit da Groq (tentativa {attempt + 1}/"
                f"{max_attempts}); aguardando {espera:.0f}s...[/yellow]"
            )
            time.sleep(espera)
    return []  # inalcançável: o loop sempre retorna ou levanta


def _retrieve_context(retriever: Retriever, file_diff: FileDiff) -> RetrievedContext | None:
    """
    Recupera o contexto normativo real do Qdrant para um arquivo do PR.

    `None` é um resultado legítimo (nenhum chunk atingiu `score_threshold`)
    e não um erro: nesse caso o LLM não é chamado, e todas as linhas do PR
    são avaliadas como não sinalizadas nesta execução — exatamente o que o
    sistema em produção faria.
    """
    context = retriever.retrieve_for_file(file_diff)
    if context is None:
        console.log(
            f"[yellow]⚠️  Nenhum chunk normativo acima do threshold para "
            f"[bold]{file_diff.filename}[/bold] — nenhuma chamada ao LLM será feita; "
            "todas as linhas deste PR contam como não sinalizadas.[/yellow]"
        )
    return context


# ── Checkpoint (resiliência ao rate limit diário da Groq) ──────────────────────
#
# O plano free/on-demand da Groq tem um teto de tokens/dia (TPD) que, sob
# `--repeticoes 3` em 30 PRs, fica no limite e força esperas de vários
# minutos entre chamadas (ver `_review_with_backoff`). Sem checkpoint, uma
# interrupção (kill do processo, sessão reiniciada) perde TODO o progresso —
# `run_evaluation` só devolve resultado ao final do laço inteiro — e a
# próxima tentativa reprocessaria PRs já concluídos, gastando ainda mais da
# cota escassa do dia à toa. O checkpoint grava o resultado de cada PR assim
# que suas `repeticoes` terminam, e é apagado só ao final de uma execução
# bem-sucedida — nunca fica "furtando" trabalho de uma configuração diferente.

_CHECKPOINT_PATH = _PROJECT_ROOT / "evaluation" / ".eval_checkpoint.json"


def _line_result_to_dict(r: LineResult) -> dict:
    return dataclasses.asdict(r)


def _line_result_from_dict(d: dict) -> LineResult:
    return LineResult(**d)


def _load_checkpoint(dataset_path: Path, repeticoes: int) -> dict:
    """
    Carrega o checkpoint se existir e for compatível com esta execução
    (mesmo dataset e número de repetições). Checkpoint de uma configuração
    diferente é ignorado — nunca aplicado por engano a outra.
    """
    if not _CHECKPOINT_PATH.exists():
        return {}
    try:
        data = json.loads(_CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}  # checkpoint corrompido (ex.: kill a meio da escrita) — ignora
    if data.get("dataset_path") != str(dataset_path) or data.get("repeticoes") != repeticoes:
        return {}
    return data.get("completed_prs", {})


def _save_checkpoint(dataset_path: Path, repeticoes: int, completed_prs: dict) -> None:
    """Escrita atômica (arquivo temporário + rename) — nunca deixa o checkpoint pela metade."""
    payload = {
        "dataset_path": str(dataset_path),
        "repeticoes": repeticoes,
        "completed_prs": completed_prs,
    }
    tmp = _CHECKPOINT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_CHECKPOINT_PATH)


# ── Execução ──────────────────────────────────────────────────────────────────


def run_evaluation(dataset_path: Path, repeticoes: int) -> tuple[AggregatedEvaluation, str]:
    """
    Executa o RAG-Reviewer real contra todos os PRs do dataset, `repeticoes`
    vezes cada (D-005), e agrega o resultado.

    O retrieval é determinístico (embedding + busca por cosine similarity
    não têm componente aleatório) e por isso é feito uma única vez por PR;
    apenas a chamada ao LLM é repetida, que é onde a variância entra mesmo
    com temperatura 0.0.

    Returns:
        Tupla (AggregatedEvaluation, nome do modelo Groq efetivamente usado)
        — o nome do modelo é registrado em `results.json` para
        reprodutibilidade: qual modelo produziu quais números.
    """
    dataset = _load_dataset(dataset_path)
    retriever, llm = _build_pipeline()

    console.rule("[bold cyan]RAG-Reviewer — Avaliação (sistema real)[/bold cyan]")
    console.print(
        f"\n[+] Dataset: [bold]{dataset_path}[/bold] ({len(dataset)} PRs) | "
        f"Modelo: [bold]{llm.model}[/bold] | "
        f"Temperatura: [bold]{llm.temperature}[/bold] | "
        f"Repetições: [bold]{repeticoes}[/bold]\n"
    )

    per_repetition_lines: list[list[LineResult]] = [[] for _ in range(repeticoes)]
    per_repetition_detections = [0] * repeticoes
    per_repetition_hallucinations = [0] * repeticoes

    completed_prs = _load_checkpoint(dataset_path, repeticoes)
    if completed_prs:
        console.log(
            f"[yellow]↺ Checkpoint encontrado:[/yellow] {len(completed_prs)} PR(s) já "
            "concluído(s) nesta configuração — pulando reprocessamento."
        )

    for pr_data in dataset:
        pr_id = pr_data["pr_id"]
        gold_lines = _build_gold_lines(pr_data)

        if pr_id in completed_prs:
            per_pr_reps = completed_prs[pr_id]
        else:
            file_diff = _build_file_diff(pr_data)

            console.log(
                f"[cyan]-> Avaliando [bold]{pr_id}[/bold]:[/cyan] "
                f"{pr_data.get('description', '')} ({len(gold_lines)} linha(s))"
            )

            context = _retrieve_context(retriever, file_diff)

            per_pr_reps = []
            for rep in range(repeticoes):
                detections = _review_with_backoff(llm, context) if context is not None else []
                line_results, total_det, hallucinated = classify_lines(gold_lines, detections)
                per_pr_reps.append(
                    {
                        "line_results": [_line_result_to_dict(r) for r in line_results],
                        "total_detections": total_det,
                        "hallucinated_detections": hallucinated,
                    }
                )
                _log_pr_repetition(rep, line_results)

            completed_prs[pr_id] = per_pr_reps
            _save_checkpoint(dataset_path, repeticoes, completed_prs)

        for rep, rep_data in enumerate(per_pr_reps):
            per_repetition_lines[rep].extend(
                _line_result_from_dict(d) for d in rep_data["line_results"]
            )
            per_repetition_detections[rep] += rep_data["total_detections"]
            per_repetition_hallucinations[rep] += rep_data["hallucinated_detections"]

    _CHECKPOINT_PATH.unlink(missing_ok=True)  # execução completa — checkpoint não serve mais

    repetitions = [
        RepetitionResult(
            repetition_index=i,
            line_results=per_repetition_lines[i],
            total_detections=per_repetition_detections[i],
            hallucinated_detections=per_repetition_hallucinations[i],
        )
        for i in range(repeticoes)
    ]
    return AggregatedEvaluation(repetitions=repetitions), llm.model


def _log_pr_repetition(rep_index: int, line_results: list[LineResult]) -> None:
    """Imprime a contagem de células de uma repetição de um PR no console."""
    tp = sum(1 for r in line_results if r.cell == "TP")
    fp = sum(1 for r in line_results if r.cell == "FP")
    fn = sum(1 for r in line_results if r.cell == "FN")
    tn = sum(1 for r in line_results if r.cell == "TN")
    ok = fp == 0 and fn == 0
    status = "[OK]" if ok else "[!!]"
    console.log(f"  {status} rep={rep_index} TP={tp} FP={fp} FN={fn} TN={tn}")


# ── Apresentação ──────────────────────────────────────────────────────────────


def _print_summary(agg: AggregatedEvaluation) -> None:
    """Imprime as métricas agregadas: média±desvio entre repetições e as matrizes publicadas."""
    console.rule("\n[bold green]Métricas primárias — média ± desvio-padrão entre repetições[/bold green]")
    console.print(
        f"\n  Precisão: [cyan]{agg.precision_mean:.4f}[/cyan] ± {agg.precision_stdev:.4f}\n"
        f"  Recall:   [cyan]{agg.recall_mean:.4f}[/cyan] ± {agg.recall_stdev:.4f}\n"
        f"  F1-Score: [bold cyan]{agg.f1_mean:.4f}[/bold cyan] ± {agg.f1_stdev:.4f}\n"
    )

    published = agg.median_f1_repetition
    console.rule(
        f"[bold green]Matriz de confusão — linha adicionada "
        f"(repetição de F1 mediano, idx={published.repetition_index})[/bold green]"
    )
    cm = published.confusion_matrix
    line_table = Table(show_header=True, header_style="bold cyan")
    line_table.add_column("")
    line_table.add_column("Sistema sinalizou", justify="right")
    line_table.add_column("Sistema não sinalizou", justify="right")
    line_table.add_row("Linha viola", f"TP = {cm['tp']}", f"FN = {cm['fn']}")
    line_table.add_row("Linha não viola", f"FP = {cm['fp']}", f"TN = {cm['tn']}")
    console.print(line_table)
    console.print(f"\n  N = {cm['n']} linha(s) avaliada(s) (TP+FP+FN+TN == N)\n")

    console.print(
        f"  [yellow]Acurácia (SECUNDÁRIA, NÃO-REPRESENTATIVA — conjunto desbalanceado, "
        f"~80% negativos):[/yellow] {published.accuracy:.4f}"
    )
    console.print(
        f"  Taxa de alucinação de localização: {published.hallucination_rate:.4f} "
        f"({published.hallucinated_detections}/{published.total_detections} detecções)"
    )
    norm_prec = published.norm_reference_precision
    norm_prec_str = f"{norm_prec:.4f}" if norm_prec is not None else "N/A (nenhum TP nesta execução)"
    console.print(f"  Precisão de referência normativa (entre os TPs): {norm_prec_str}\n")

    gate_cm = published.pr_gate_confusion_matrix()
    console.rule("[bold green]Matriz de confusão — nível de PR (gate de CI/CD)[/bold green]")
    gate_table = Table(show_header=True, header_style="bold cyan")
    gate_table.add_column("")
    gate_table.add_column("Sistema bloqueia", justify="right")
    gate_table.add_column("Sistema não bloqueia", justify="right")
    gate_table.add_row("PR viola", f"TP = {gate_cm['tp']}", f"FN = {gate_cm['fn']}")
    gate_table.add_row("PR limpo", f"FP = {gate_cm['fp']}", f"TN = {gate_cm['tn']}")
    console.print(gate_table)
    console.print(f"\n  N = {gate_cm['n']} PR(s) avaliado(s)\n")

    _print_targets(agg)


def _print_targets(agg: AggregatedEvaluation) -> None:
    """Verifica as métricas médias contra as metas de §15.3 do planejamento."""
    console.rule("[bold yellow]Metas do TCC (§15.3)[/bold yellow]")

    checks = check_targets(agg.precision_mean, agg.recall_mean, agg.f1_mean)
    labels = {
        "precision": f"Precisão (média) >= {TARGET_PRECISION:.2f}",
        "recall": f"Recall (média) >= {TARGET_RECALL:.2f}",
        "f1": f"F1-Score (média) >= {TARGET_F1:.2f}",
    }
    for key in ("precision", "recall", "f1"):
        achieved = checks[key]
        icon = "[OK]" if achieved else "[FAIL]"
        style = "green" if achieved else "red"
        console.print(f"  {icon} [{style}]{labels[key]}[/{style}]")
    console.print()


def _save_results(
    agg: AggregatedEvaluation,
    dataset_path: Path,
    repeticoes: int,
    model: str,
    output_path: Path,
) -> None:
    """Salva o conjunto completo de métricas em JSON para análise posterior."""
    published = agg.median_f1_repetition
    checks = check_targets(agg.precision_mean, agg.recall_mean, agg.f1_mean)

    output = {
        "config": {
            "dataset": str(dataset_path),
            "repeticoes": repeticoes,
            "model": model,
            "temperature": 0.0,
        },
        "repetitions": [
            {
                "repetition_index": r.repetition_index,
                "confusion_matrix": r.confusion_matrix,
                "precision": round(r.precision, 4),
                "recall": round(r.recall, 4),
                "f1": round(r.f1, 4),
                "accuracy": round(r.accuracy, 4),
                "hallucination_rate": round(r.hallucination_rate, 4),
                "norm_reference_precision": (
                    round(r.norm_reference_precision, 4)
                    if r.norm_reference_precision is not None
                    else None
                ),
                "total_detections": r.total_detections,
                "hallucinated_detections": r.hallucinated_detections,
            }
            for r in agg.repetitions
        ],
        "summary": {
            "precision_mean": round(agg.precision_mean, 4),
            "precision_stdev": round(agg.precision_stdev, 4),
            "recall_mean": round(agg.recall_mean, 4),
            "recall_stdev": round(agg.recall_stdev, 4),
            "f1_mean": round(agg.f1_mean, 4),
            "f1_stdev": round(agg.f1_stdev, 4),
            "median_f1_repetition_index": published.repetition_index,
        },
        "published": {
            "line_confusion_matrix": published.confusion_matrix,
            "pr_gate_confusion_matrix": published.pr_gate_confusion_matrix(),
            "accuracy": {
                "value": round(published.accuracy, 4),
                "note": (
                    "SECUNDÁRIA e NÃO-REPRESENTATIVA: conjunto desbalanceado "
                    "(~80% de linhas negativas, D-004). Não usar para comparar desempenho."
                ),
            },
            "hallucination_rate": round(published.hallucination_rate, 4),
            "norm_reference_precision": (
                round(published.norm_reference_precision, 4)
                if published.norm_reference_precision is not None
                else None
            ),
        },
        "targets": checks,
        "per_pr_gate": [
            {
                "pr_id": g.pr_id,
                "expected_positive": g.expected_positive,
                "predicted_positive": g.predicted_positive,
                "cell": g.cell,
            }
            for g in published.pr_gate_results()
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[+] Resultados salvos em [bold]{output_path}[/bold]\n")


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Avalia o RAG-Reviewer contra o dataset do piloto (Seção 5 do guia "
            "Python — Comparações), usando Qdrant e Groq reais."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=_DEFAULT_DATASET,
        help="Caminho para o arquivo JSON do dataset.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help="Caminho para salvar os resultados em JSON.",
    )
    parser.add_argument(
        "--repeticoes",
        type=int,
        default=_DEFAULT_REPETICOES,
        help=(
            "Número de execuções completas e independentes do dataset (D-005). "
            f"Padrão: {_DEFAULT_REPETICOES} (execução oficial). Use 1 em "
            "desenvolvimento para poupar cota da API Groq."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if not args.dataset.exists():
        console.print(f"[bold red]Erro:[/bold red] Dataset não encontrado: {args.dataset}")
        sys.exit(1)

    if args.repeticoes < 1:
        console.print("[bold red]Erro:[/bold red] --repeticoes deve ser >= 1.")
        sys.exit(1)

    try:
        aggregated, model = run_evaluation(args.dataset, args.repeticoes)
    except Exception as exc:  # noqa: BLE001 — erro fatal, sem fallback para mocks
        # show_locals=False: locals de LLMClient/VectorStore podem conter
        # segredos (API keys) — nunca imprimir isso, mesmo em erro.
        console.print_exception(show_locals=False)
        console.print(
            f"\n[bold red]Erro fatal durante a avaliação:[/bold red] {exc}\n"
            "[dim]Nenhum fallback para dados simulados é aplicado. Verifique "
            "GROQ_API_KEY, QDRANT_URL/QDRANT_API_KEY e a conectividade de rede.[/dim]"
        )
        sys.exit(1)

    _print_summary(aggregated)
    _save_results(aggregated, args.dataset, args.repeticoes, model, args.output)


if __name__ == "__main__":
    main()
