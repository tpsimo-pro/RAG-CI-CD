"""
gold.py — Gabarito de retrieval, derivado do dataset do piloto.

Para cada uma das 60 linhas POSITIVAS de `pilot_secao5.json`, qual chave
normativa precisa ter chegado ao LLM.

Apenas as positivas entram (spec §6.1): para uma linha negativa como
`if x is not None:`, a Seção 5 é justamente a norma que a declara correta —
seria relevante e ao mesmo tempo não deveria gerar violação. O gabarito
ficaria ambíguo, e métrica sobre ambiguidade não serve.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from evaluation.retrieval.norm_map import NORM_BOOLEANO, NORM_NULO

_SUB_REGRA_PARA_CHAVE = {
    "booleano": NORM_BOOLEANO,
    "nulo": NORM_NULO,
}


@dataclass(frozen=True)
class GoldLine:
    """Uma linha positiva e a norma que deveria ser recuperada para ela."""

    pr_id: str
    line: str
    norm_key: str


def build_gold(dataset_path: Path) -> list[GoldLine]:
    """
    Deriva o gabarito de retrieval do dataset de detecção.

    Raises:
        ValueError: Se alguma linha positiva tiver `sub_regra` desconhecida —
            falha ruidosa, nunca rótulo silenciosamente descartado.
    """
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    gold: list[GoldLine] = []

    for pr in dataset:
        for al in pr["added_lines"]:
            if not al["viola"]:
                continue
            sub = al["sub_regra"]
            if sub not in _SUB_REGRA_PARA_CHAVE:
                raise ValueError(
                    f"{pr['pr_id']}: sub_regra desconhecida {sub!r} "
                    f"na linha {al['line']!r}"
                )
            gold.append(
                GoldLine(
                    pr_id=pr["pr_id"],
                    line=al["line"],
                    norm_key=_SUB_REGRA_PARA_CHAVE[sub],
                )
            )

    return gold
