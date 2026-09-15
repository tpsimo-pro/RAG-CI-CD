# evaluation/retrieval/run_retrieval_eval.py
"""
run_retrieval_eval.py — Avaliação da camada de recuperação.

NÃO chama o LLM. É offline, determinística e de custo zero de API, então
pode rodar quantas vezes for necessário durante a calibração (spec §6.3).

Uso:
    python -m evaluation.retrieval.run_retrieval_eval --label L0
    python -m evaluation.retrieval.run_retrieval_eval --label L2 --per-line
    python -m evaluation.retrieval.run_retrieval_eval --label L4 --per-line --hybrid
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from evaluation.retrieval.gold import GoldLine, build_gold
from evaluation.retrieval.metrics import (
    RetrievalOutcome,
    context_precision_at_k,
    recall_at_k,
)
from evaluation.retrieval.norm_map import norm_keys_of_chunk
from rag_reviewer.config import get_settings
from rag_reviewer.embedder import Embedder
from rag_reviewer.sparse_encoder import SparseEncoder
from rag_reviewer.vector_store import VectorStore

console = Console(highlight=False)

_ROOT = Path(__file__).parent.parent.parent
_DATASET = _ROOT / "evaluation" / "dataset" / "pilot_secao5.json"


def _retrieve_for_line(
    embedder: Embedder,
    store: VectorStore,
    line: str,
    top_k: int,
    score_threshold: float,
) -> list[dict]:
    """Recupera chunks para UMA linha, só denso (configurações L2/L3)."""
    vector = embedder.embed_single(line).tolist()
    return store.search(
        query_vector=vector,
        top_k=top_k,
        score_threshold=score_threshold,
    )


def _retrieve_for_line_hybrid(
    embedder: Embedder,
    sparse_encoder: SparseEncoder,
    store: VectorStore,
    line: str,
    top_k: int,
) -> list[dict]:
    """
    Recupera chunks para UMA linha, denso + esparso BM25 com fusão RRF (L4).

    Sem `score_threshold`: o score pós-fusão é de posto, não cosseno
    (spec §4.4) — mesma razão pela qual `VectorStore.search_hybrid` não
    aceita esse parâmetro.
    """
    vector = embedder.embed_single(line).tolist()
    sparse = sparse_encoder.encode(line)
    return store.search_hybrid(dense=vector, sparse=sparse, top_k=top_k)


def _retrieve_for_file(
    embedder: Embedder,
    store: VectorStore,
    lines: list[str],
    filename: str,
    top_k: int,
    score_threshold: float,
) -> list[dict]:
    """
    Recupera chunks para o ARQUIVO inteiro (comportamento L0/L1).

    Replica `build_query_text`: nome do arquivo + linhas adicionadas
    concatenadas. É a média semântica que a spec §3 identifica como causa
    dos scores comprimidos — preservada aqui para que L0 seja fiel.
    """
    query = f"Arquivo: {filename}\n" + "\n".join(lines)
    vector = embedder.embed_single(query).tolist()
    return store.search(
        query_vector=vector,
        top_k=top_k,
        score_threshold=score_threshold,
    )


def run_retrieval_eval(
    dataset_path: Path, label: str, per_line: bool, hybrid: bool = False
) -> dict:
    """
    Executa a avaliação de retrieval e devolve o dicionário de resultados.

    Args:
        hybrid: Ativa a busca híbrida densa+esparsa com fusão RRF (L4).
            Exige `per_line=True` — a busca híbrida só existe por linha,
            igual ao Retriever de produção (spec — Task 9).

    Raises:
        ValueError: Se `hybrid=True` e `per_line=False`.
    """
    if hybrid and not per_line:
        raise ValueError(
            "--hybrid exige --per-line: a busca híbrida só existe por linha."
        )

    settings = get_settings()
    gold = build_gold(dataset_path)
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    embedder = Embedder()
    store = VectorStore()
    # Falha alto se a coleção foi indexada com outro modelo de embedding
    # (spec §8.1) — buscar com modelos divergentes produz lixo silencioso,
    # o que contaminaria justamente a métrica que esta avaliação mede.
    store.assert_model_matches(settings.embedding_model)
    sparse_encoder = SparseEncoder() if hybrid else None

    # Índice auxiliar: pr_id -> (filename, todas as linhas adicionadas)
    por_pr = {
        pr["pr_id"]: (pr["filename"], [al["line"] for al in pr["added_lines"]])
        for pr in dataset
    }

    # Cache por PR quando a consulta é por arquivo — a mesma consulta serve
    # todas as linhas positivas daquele PR.
    cache_arquivo: dict[str, list[dict]] = {}
    outcomes: list[RetrievalOutcome] = []

    for g in gold:
        filename, linhas = por_pr[g.pr_id]
        if hybrid:
            chunks = _retrieve_for_line_hybrid(
                embedder, sparse_encoder, store, g.line, settings.top_k_chunks
            )
        elif per_line:
            chunks = _retrieve_for_line(
                embedder, store, g.line, settings.top_k_chunks, settings.score_threshold
            )
        else:
            if g.pr_id not in cache_arquivo:
                cache_arquivo[g.pr_id] = _retrieve_for_file(
                    embedder,
                    store,
                    linhas,
                    filename,
                    settings.top_k_chunks,
                    settings.score_threshold,
                )
            chunks = cache_arquivo[g.pr_id]

        outcomes.append(
            RetrievalOutcome(
                gold=g,
                ranked_norm_keys=[norm_keys_of_chunk(c["text"]) for c in chunks],
            )
        )

    resultado = {
        "label": label,
        "config": {
            "per_line": per_line,
            "hybrid": hybrid,
            "embedding_model": settings.embedding_model,
            "top_k": settings.top_k_chunks,
            "score_threshold": settings.score_threshold,
            "collection": settings.qdrant_collection,
        },
        "n_gold_lines": len(gold),
        "recall_at_1": round(recall_at_k(outcomes, 1), 4),
        "recall_at_3": round(recall_at_k(outcomes, 3), 4),
        "recall_at_5": round(recall_at_k(outcomes, 5), 4),
        "context_precision_at_5": round(context_precision_at_k(outcomes, 5), 4),
    }
    return resultado


def _print_result(r: dict) -> None:
    table = Table(title=f"Retrieval — {r['label']}", header_style="bold cyan")
    table.add_column("Métrica")
    table.add_column("Valor", justify="right")
    for chave in (
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "context_precision_at_5",
    ):
        table.add_row(chave, f"{r[chave]:.4f}")
    console.print(table)

    meta = r["recall_at_5"] >= 0.95
    icone = "[OK]" if meta else "[FAIL]"
    cor = "green" if meta else "red"
    console.print(f"  {icone} [{cor}]Critério: recall@5 >= 0.95[/{cor}]\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Avalia a camada de recuperação.")
    parser.add_argument("--label", required=True, help="Rótulo da configuração (L0..L4).")
    parser.add_argument("--per-line", action="store_true", help="Consulta por linha.")
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Busca híbrida densa+esparsa com fusão RRF (L4). Exige --per-line.",
    )
    parser.add_argument("--dataset", type=Path, default=_DATASET)
    args = parser.parse_args()

    r = run_retrieval_eval(args.dataset, args.label, args.per_line, args.hybrid)
    _print_result(r)

    saida = Path(__file__).parent / f"results_{args.label}.json"
    saida.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[+] Resultado salvo em [bold]{saida}[/bold]\n")


if __name__ == "__main__":
    main()
