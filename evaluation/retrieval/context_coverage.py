"""
context_coverage.py — A norma da linha positiva chegou ao contexto do LLM?

O `recall@k` mede cada linha isolada. O LLM, porém, recebe o contexto que o
`Retriever` monta por arquivo (busca por linha, união, corte em 8 chunks). Este
módulo mede o que de fato chega: para cada linha positiva do dataset, se o
enunciado da norma está em algum dos chunks entregues ao LLM do arquivo, e
quantas palavras de contexto o arquivo carrega (proxy do custo em tokens).

Instrumentação de avaliação; o sistema em produção não a usa.

Uso:
    python -m evaluation.retrieval.context_coverage --output cobertura.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.retrieval.norm_map import norm_keys_of_chunk
from evaluation.run_evaluation import _build_file_diff

_DATASET = Path(__file__).resolve().parents[1] / "dataset" / "pilot_dataset.json"


def cobertura_de_contexto(dataset: list[dict], retriever) -> list[dict]:
    """
    Para cada linha positiva: a norma está no contexto entregue ao LLM?

    Args:
        dataset: PRs no schema v2 (`files` com `added_lines`).
        retriever: Objeto com `retrieve_for_file(FileDiff)`, que devolve um
            contexto com `chunks` (lista de dicts com `text`) ou `None`.

    Returns:
        Uma entrada por linha positiva: `pr_id`, `filename`, `line`,
        `sub_regra`, `no_contexto` e `palavras_contexto` (do arquivo).
    """
    saida: list[dict] = []
    for pr in dataset:
        for arquivo in pr["files"]:
            contexto = retriever.retrieve_for_file(_build_file_diff(arquivo))
            chunks = contexto.chunks if contexto is not None else []
            chaves: set[str] = set()
            for chunk in chunks:
                chaves |= norm_keys_of_chunk(chunk["text"])
            palavras = sum(len(c["text"].split()) for c in chunks)
            for entrada in arquivo["added_lines"]:
                if entrada["viola"]:
                    saida.append(
                        {
                            "pr_id": pr["pr_id"],
                            "filename": arquivo["filename"],
                            "line": entrada["line"],
                            "sub_regra": entrada["sub_regra"],
                            "no_contexto": entrada["sub_regra"] in chaves,
                            "palavras_contexto": palavras,
                        }
                    )
    return saida


def main() -> None:
    from rag_reviewer.embedder import Embedder
    from rag_reviewer.retriever import Retriever
    from rag_reviewer.vector_store import VectorStore

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=_DATASET)
    parser.add_argument("--collection", default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_bytes().decode("utf-8"))
    store = VectorStore(collection_name=args.collection)
    retriever = Retriever(embedder=Embedder(), store=store)
    linhas = cobertura_de_contexto(dataset, retriever)
    args.output.write_text(
        json.dumps(linhas, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    cobertas = sum(1 for linha in linhas if linha["no_contexto"])
    print(f"{cobertas}/{len(linhas)} linhas positivas com a norma no contexto")


if __name__ == "__main__":
    main()
