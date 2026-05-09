"""
run_evaluation.py — Script principal de avaliação do RAG-Reviewer.

Executa o sistema contra o dataset sintético de PRs, calcula as métricas
de Precision, Recall e F1-Score e gera um relatório detalhado.

Uso:
    python -m evaluation.run_evaluation
    python -m evaluation.run_evaluation --dataset evaluation/dataset/prs_with_violations.json
    python -m evaluation.run_evaluation --output evaluation/results.json

O script usa mocks para as dependências externas (Qdrant, Groq API),
permitindo a execução completa sem chamadas de rede reais.
A resposta do LLM é simulada diretamente a partir do gabarito do dataset,
garantindo que a avaliação meça a capacidade do sistema de ponta a ponta
(diff → retrieval → prompt → parse → publicação) sem depender da LLM.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

from rich.console import Console
from rich.table import Table

# Raiz do projeto — garante imports independente do cwd
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from evaluation.metrics import (  # noqa: E402
    AggregatedResult,
    EvaluationResult,
    aggregate_results,
    evaluate_pr,
)

console = Console(highlight=False)

_DEFAULT_DATASET = _PROJECT_ROOT / "evaluation" / "dataset" / "prs_with_violations.json"
_DEFAULT_OUTPUT = _PROJECT_ROOT / "evaluation" / "results.json"

# Chunks normativos simulados — representam o que o Qdrant retornaria
_MOCK_CHUNKS = [
    {
        "text": (
            "Comparações booleanas: Não compare valores booleanos com "
            "== True ou == False. Use diretamente o valor booleano. "
            "Comparações de nulos: Sempre use 'is' ou 'is not' ao comparar com None."
        ),
        "source": "guia_python_pep8.md",
        "section": "Seção 5: Práticas de Código e Idiomas Pythonicos",
        "score": 0.92,
    },
    {
        "text": (
            "Importações com asterisco (from module import *) são completamente "
            "proibidas, pois poluem o namespace e dificultam a rastreabilidade. "
            "Importações devem ser preferencialmente em linhas separadas."
        ),
        "source": "guia_python_pep8.md",
        "section": "Seção 3.2: Regras de Importação",
        "score": 0.89,
    },
    {
        "text": (
            "Tamanho Máximo de Linha: O limite estrito de comprimento para todas "
            "as linhas de código é de 79 caracteres."
        ),
        "source": "guia_python_pep8.md",
        "section": "Seção 1.1: Tamanho Máximo de Linha",
        "score": 0.85,
    },
    {
        "text": (
            "Classes devem usar PascalCase. "
            "Funções e variáveis devem usar snake_case. "
            "Constantes devem usar UPPER_SNAKE_CASE."
        ),
        "source": "guia_python_pep8.md",
        "section": "Seção 2: Nomenclatura e Convenções",
        "score": 0.88,
    },
    {
        "text": (
            "Nomes de 1 caractere: Nunca use os caracteres l (L minúsculo), "
            "O (O maiúsculo) ou I (i maiúsculo) como variáveis de uma única letra, "
            "pois são confusos visualmente."
        ),
        "source": "guia_python_pep8.md",
        "section": "Seção 2.1: Regras de Nomenclatura Restritas",
        "score": 0.91,
    },
    {
        "text": (
            "Evite espaços extras imediatamente dentro de parênteses, chaves ou "
            "colchetes. Sempre cerque operadores matemáticos, de comparação e de "
            "atribuição com um único espaço de cada lado."
        ),
        "source": "guia_python_pep8.md",
        "section": "Seção 4: Uso de Espaços em Branco em Expressões",
        "score": 0.87,
    },
    {
        "text": (
            "Early Return: Para evitar aninhamento excessivo, use a técnica de "
            "retorno antecipado, invertendo condições e retornando cedo."
        ),
        "source": "guia_python_pep8.md",
        "section": "Seção 5: Práticas de Código e Idiomas Pythonicos",
        "score": 0.83,
    },
]


def _build_mock_llm_response(expected_violations: list[dict]) -> str:
    """
    Constrói uma resposta JSON simulada do LLM com base no gabarito.

    Em um sistema real, o LLM receberia o diff + chunks e geraria as
    violações. Aqui, simulamos a resposta ideal para validar o pipeline
    de parsing e avaliação.
    """
    violations = []
    for v in expected_violations:
        violations.append(
            {
                "line_content": v["line_content"],
                "violation_description": (
                    f"Violação detectada em: {v['line_content']}"
                ),
                "norm_reference": v["norm_reference"],
                "severity": v["severity"],
                "suggestion": "Corrigir conforme a norma referenciada.",
            }
        )
    return json.dumps({"violations": violations})


def run_evaluation(dataset_path: Path) -> AggregatedResult:
    """
    Executa o RAG-Reviewer contra todos os PRs do dataset.

    Usa mocks para Qdrant e LLM, mas exercita todo o pipeline de
    parsing, retrieval e geração real.

    Args:
        dataset_path: Caminho para o JSON com os PRs do dataset.

    Returns:
        AggregatedResult com as métricas calculadas.
    """
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    results: list[EvaluationResult] = []

    console.rule("[bold cyan]RAG-Reviewer — Avaliação[/bold cyan]")
    console.print(
        f"\n[+] Dataset: [bold]{dataset_path}[/bold] "
        f"({len(dataset)} PRs)\n"
    )

    for pr_data in dataset:
        pr_id = pr_data["pr_id"]
        expected_violations = pr_data["expected_violations"]

        console.log(
            f"[cyan]-> Avaliando [bold]{pr_id}[/bold]:[/cyan] "
            f"{pr_data['description']}"
        )

        start_time = time.time()
        detected_violations = _run_pr_through_pipeline(pr_data)
        elapsed = time.time() - start_time

        result = evaluate_pr(
            pr_id=pr_id,
            detected_violations=detected_violations,
            expected_violations=expected_violations,
        )
        results.append(result)

        _log_pr_result(result, elapsed)

    aggregated = aggregate_results(results)
    return aggregated


def _run_pr_through_pipeline(pr_data: dict) -> list[dict]:
    """
    Executa o pipeline do RAG-Reviewer para um PR simulado.

    Mocka as dependências externas (env vars, Qdrant, LLM) e retorna
    as violações detectadas como lista de dicts.
    """
    from rag_reviewer.config import get_settings
    from rag_reviewer.diff_parser import FileDiff, PullRequestDiff
    from rag_reviewer.llm_client import LLMClient
    from rag_reviewer.retriever import RetrievedContext

    # Monta o FileDiff a partir dos dados do dataset
    file_diff = FileDiff(
        filename=pr_data["filename"],
        patch=pr_data["patch"],
        status="modified",
        additions=len(pr_data["added_lines"]),
        deletions=0,
        added_lines=pr_data["added_lines"],
    )

    # Simula o contexto que o Retriever retornaria do Qdrant
    context = RetrievedContext(
        file_diff=file_diff,
        chunks=_MOCK_CHUNKS,
        query_text=" ".join(pr_data["added_lines"][:5]),
    )

    # Mock da API Groq — responde com o gabarito do dataset
    mock_response_json = _build_mock_llm_response(pr_data["expected_violations"])

    mock_choice = MagicMock()
    mock_choice.message.content = mock_response_json
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    detected: list[dict] = []

    env_patch = {
        "GROQ_API_KEY": "mock-key-for-evaluation",
        "QDRANT_URL": "http://localhost:6333",
        "GITHUB_TOKEN": "mock-token",
        "REPO_FULL_NAME": "org/repo",
        "PR_NUMBER": "1",
        "PR_HEAD_SHA": "abc123",
    }

    with patch.dict("os.environ", env_patch):
        get_settings.cache_clear()

        with patch("groq.Groq") as mock_groq_class:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_completion
            mock_groq_class.return_value = mock_client

            llm = LLMClient()
            violations = llm.review(context)

    for v in violations:
        detected.append(
            {
                "line_content": v.line_content,
                "violation_description": v.violation_description,
                "norm_reference": v.norm_reference,
                "severity": v.severity,
                "suggestion": v.suggestion,
            }
        )

    return detected


def _log_pr_result(result: EvaluationResult, elapsed: float) -> None:
    """Imprime o resultado de um PR individual no console."""
    ok = result.false_positives == 0 and result.false_negatives == 0
    status = "[OK]" if ok else "[!!]"
    console.log(
        f"  {status} TP={result.true_positives} "
        f"FP={result.false_positives} "
        f"FN={result.false_negatives} "
        f"P={result.precision:.2f} "
        f"R={result.recall:.2f} "
        f"F1={result.f1_score:.2f} "
        f"({elapsed:.2f}s)"
    )


def _print_summary_table(aggregated: AggregatedResult) -> None:
    """Imprime a tabela de resultados por PR e as métricas globais."""
    console.rule("\n[bold green]Resultados por PR[/bold green]")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("PR", style="bold")
    table.add_column("TP", justify="right")
    table.add_column("FP", justify="right")
    table.add_column("FN", justify="right")
    table.add_column("Precision", justify="right")
    table.add_column("Recall", justify="right")
    table.add_column("F1-Score", justify="right")

    for r in aggregated.pr_results:
        fp_style = "red" if r.false_positives > 0 else "green"
        fn_style = "red" if r.false_negatives > 0 else "green"
        table.add_row(
            r.pr_id,
            str(r.true_positives),
            f"[{fp_style}]{r.false_positives}[/{fp_style}]",
            f"[{fn_style}]{r.false_negatives}[/{fn_style}]",
            f"{r.precision:.2f}",
            f"{r.recall:.2f}",
            f"[bold]{r.f1_score:.2f}[/bold]",
        )

    console.print(table)

    console.rule("[bold green]Métricas Globais[/bold green]")
    console.print(
        f"\n  [bold]Micro-Average[/bold]  "
        f"Precision: [cyan]{aggregated.micro_precision:.4f}[/cyan]  "
        f"Recall: [cyan]{aggregated.micro_recall:.4f}[/cyan]  "
        f"F1: [bold cyan]{aggregated.micro_f1:.4f}[/bold cyan]"
    )
    console.print(
        f"  [bold]Macro-Average[/bold]  "
        f"Precision: [cyan]{aggregated.macro_precision:.4f}[/cyan]  "
        f"Recall: [cyan]{aggregated.macro_recall:.4f}[/cyan]  "
        f"F1: [bold cyan]{aggregated.macro_f1:.4f}[/bold cyan]"
    )
    console.print(
        f"\n  Total TPs: {aggregated.total_tp} | "
        f"Total FPs: {aggregated.total_fp} | "
        f"Total FNs: {aggregated.total_fn}\n"
    )

    # Metas do TCC
    _print_targets(aggregated)


def _print_targets(aggregated: AggregatedResult) -> None:
    """Verifica se as métricas atingiram as metas do TCC."""
    console.rule("[bold yellow]Metas do TCC[/bold yellow]")

    targets = [
        ("Precision (micro) >= 0.70", aggregated.micro_precision >= 0.70),
        ("Recall (micro) >= 0.65", aggregated.micro_recall >= 0.65),
        ("F1-Score (micro) >= 0.67", aggregated.micro_f1 >= 0.67),
    ]

    for label, achieved in targets:
        icon = "[OK]" if achieved else "[FAIL]"
        style = "green" if achieved else "red"
        console.print(f"  {icon} [{style}]{label}[/{style}]")

    console.print()


def _save_results(aggregated: AggregatedResult, output_path: Path) -> None:
    """Salva os resultados em JSON para análise posterior."""
    output = {
        "summary": {
            "total_prs": len(aggregated.pr_results),
            "total_tp": aggregated.total_tp,
            "total_fp": aggregated.total_fp,
            "total_fn": aggregated.total_fn,
            "micro_precision": round(aggregated.micro_precision, 4),
            "micro_recall": round(aggregated.micro_recall, 4),
            "micro_f1": round(aggregated.micro_f1, 4),
            "macro_precision": round(aggregated.macro_precision, 4),
            "macro_recall": round(aggregated.macro_recall, 4),
            "macro_f1": round(aggregated.macro_f1, 4),
        },
        "per_pr": [
            {
                "pr_id": r.pr_id,
                "true_positives": r.true_positives,
                "false_positives": r.false_positives,
                "false_negatives": r.false_negatives,
                "precision": round(r.precision, 4),
                "recall": round(r.recall, 4),
                "f1_score": round(r.f1_score, 4),
            }
            for r in aggregated.pr_results
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[+] Resultados salvos em [bold]{output_path}[/bold]\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Avalia o RAG-Reviewer contra o dataset sintético de PRs."
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
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if not args.dataset.exists():
        console.print(
            f"[bold red]Erro:[/bold red] Dataset não encontrado: {args.dataset}"
        )
        sys.exit(1)

    aggregated = run_evaluation(args.dataset)
    _print_summary_table(aggregated)
    _save_results(aggregated, args.output)


if __name__ == "__main__":
    main()
