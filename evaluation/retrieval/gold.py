"""
gold.py — Gabarito de retrieval, derivado do dataset do piloto.

Para cada linha POSITIVA de `pilot_dataset.json`, qual chave
normativa precisa ter chegado ao LLM.

Apenas as positivas entram (spec §6.1): para uma linha negativa como
`if x is not None:`, a PEP 8 é justamente a norma que a declara correta —
seria relevante e ao mesmo tempo não deveria gerar violação. O gabarito
ficaria ambíguo, e métrica sobre ambiguidade não serve.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from evaluation.dataset.norms import NORMAS_POR_ID


@dataclass(frozen=True)
class GoldLine:
    """Uma linha positiva e a norma que deveria ser recuperada para ela."""

    pr_id: str
    filename: str
    line: str
    norm_key: str


def build_gold(dataset_path: Path) -> list[GoldLine]:
    """
    Deriva o gabarito de retrieval do dataset de detecção.

    A chave da norma é a própria `sub_regra` da linha (id do catálogo).

    Raises:
        ValueError: Se alguma linha positiva tiver `sub_regra` fora do
            catálogo — falha ruidosa, nunca rótulo silenciosamente descartado.
    """
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    gold: list[GoldLine] = []

    for pr in dataset:
        for arquivo in pr["files"]:
            for al in arquivo["added_lines"]:
                if not al["viola"]:
                    continue
                sub = al["sub_regra"]
                if sub not in NORMAS_POR_ID:
                    raise ValueError(
                        f"{pr['pr_id']}: sub_regra desconhecida {sub!r} "
                        f"na linha {al['line']!r}"
                    )
                gold.append(
                    GoldLine(
                        pr_id=pr["pr_id"],
                        filename=arquivo["filename"],
                        line=al["line"],
                        norm_key=sub,
                    )
                )

    return gold
