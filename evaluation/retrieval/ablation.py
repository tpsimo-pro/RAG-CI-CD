# evaluation/retrieval/ablation.py
"""
ablation.py — Consolida os resultados das configurações L0..L4.

Lê os `results_<label>.json` produzidos por `run_retrieval_eval` e monta a
tabela de ablação: o valor de cada métrica por configuração e o ganho
incremental de cada camada sobre a anterior.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console(highlight=False)

_AQUI = Path(__file__).parent
_ORDEM = ["L0", "L1", "L2", "L3", "L4"]
_METRICAS = ["recall_at_1", "recall_at_3", "recall_at_5", "mrr", "context_precision_at_5"]


def carregar() -> list[dict]:
    """Carrega os resultados existentes, na ordem canônica das camadas."""
    resultados = []
    for label in _ORDEM:
        caminho = _AQUI / f"results_{label}.json"
        if caminho.exists():
            resultados.append(json.loads(caminho.read_text(encoding="utf-8")))
        else:
            console.print(f"[yellow]aviso:[/yellow] {caminho.name} ausente — pulando.")
    return resultados


def main() -> None:
    resultados = carregar()
    if not resultados:
        console.print("[red]Nenhum resultado encontrado.[/red]")
        return

    tabela = Table(title="Ablação da camada de RAG", header_style="bold cyan")
    tabela.add_column("Config", style="bold")
    for m in _METRICAS:
        tabela.add_column(m, justify="right")
    tabela.add_column("Δ recall@5", justify="right")

    anterior = None
    for r in resultados:
        if anterior is None:
            delta = "—"
        else:
            d = r["recall_at_5"] - anterior
            delta = f"[green]+{d:.4f}[/green]" if d > 0 else f"[red]{d:.4f}[/red]"
        tabela.add_row(
            r["label"], *[f"{r[m]:.4f}" for m in _METRICAS], delta
        )
        anterior = r["recall_at_5"]

    console.print(tabela)

    melhor = max(resultados, key=lambda r: r["recall_at_5"])
    atingiu = melhor["recall_at_5"] >= 0.95
    icone = "[OK]" if atingiu else "[FAIL]"
    cor = "green" if atingiu else "red"
    console.print(
        f"\n  {icone} [{cor}]Melhor: {melhor['label']} com "
        f"recall@5 = {melhor['recall_at_5']:.4f} (critério: >= 0.95)[/{cor}]\n"
    )


if __name__ == "__main__":
    main()
