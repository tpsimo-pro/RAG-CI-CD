"""Leitura do unified diff do dataset (D-010).

So o necessario ao validador: para cada linha do patch, o tipo (' ', '+', '-')
e, quando existe no arquivo novo, o numero da linha (1-based).
"""
from __future__ import annotations

import re

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(ValueError):
    """Patch malformado ou inconsistente."""


def parse_patch(patch: str) -> list[tuple[str, int | None, str]]:
    """Linhas do patch como (tipo, numero na versao nova ou None, texto).

    Valida os contadores de cada hunk contra o corpo.
    """
    out: list[tuple[str, int | None, str]] = []
    linhas = patch.split("\n")
    i = 0
    while i < len(linhas):
        m = _HUNK.match(linhas[i])
        if not m:
            raise PatchError(f"esperado cabecalho de hunk, obtido {linhas[i]!r}")
        velho = int(m.group(2)) if m.group(2) is not None else 1
        novo = int(m.group(4)) if m.group(4) is not None else 1
        n_novo = int(m.group(3))
        i += 1
        vistos_velho = vistos_novo = 0
        while i < len(linhas) and not linhas[i].startswith("@@"):
            tipo, texto = linhas[i][:1], linhas[i][1:]
            if tipo == " ":
                out.append((" ", n_novo + vistos_novo, texto))
                vistos_velho += 1
                vistos_novo += 1
            elif tipo == "+":
                out.append(("+", n_novo + vistos_novo, texto))
                vistos_novo += 1
            elif tipo == "-":
                out.append(("-", None, texto))
                vistos_velho += 1
            else:
                raise PatchError(f"linha de patch sem prefixo: {linhas[i]!r}")
            i += 1
        if (vistos_velho, vistos_novo) != (velho, novo):
            raise PatchError(
                f"contadores do hunk {m.group(0)!r} nao batem: "
                f"-{vistos_velho} +{vistos_novo}"
            )
    return out


def linhas_adicionadas(patch: str) -> list[tuple[int, str]]:
    """(numero 1-based na versao nova, texto) de cada linha `+`, em ordem."""
    return [(n, t) for tipo, n, t in parse_patch(patch) if tipo == "+" and n]
