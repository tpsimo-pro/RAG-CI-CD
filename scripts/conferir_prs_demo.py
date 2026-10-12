"""
conferir_prs_demo.py - Confere as reviews dos PRs de teste contra o gabarito (D-011).

Para cada PR do GitHub informado, lê os comentários inline da review (gh api),
usa o campo `line` que a API devolve (a linha no arquivo depois da mudança, ou
seja, independente da contagem de `position` do publisher) para achar o texto da
linha e compara com os rótulos do dataset: linhas sinalizadas contra `viola`,
ambíguas à parte.

Uso:
    python -m scripts.conferir_prs_demo PR-003=12 PR-007=13 PR-021=14
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
_DATASET = _RAIZ / "evaluation" / "dataset" / "pilot_dataset.json"


def texto_da_linha(linhas_depois: list[str], numero: int | None) -> str | None:
    """Texto da linha `numero` (1-indexada) do arquivo depois da mudança."""
    if numero is None or not 1 <= numero <= len(linhas_depois):
        return None
    return linhas_depois[numero - 1]


def _gh(caminho: str) -> list[dict]:
    saida = subprocess.run(
        ["gh", "api", "--paginate", caminho],
        cwd=_RAIZ,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    # --paginate concatena arrays JSON ("[...][...]"); decodifica um a um
    decodificador = json.JSONDecoder()
    itens: list[dict] = []
    pos = 0
    while pos < len(saida):
        while pos < len(saida) and saida[pos].isspace():
            pos += 1
        if pos >= len(saida):
            break
        bloco, pos = decodificador.raw_decode(saida, pos)
        itens.extend(bloco)
    return itens


def _depois(arquivo: dict) -> str:
    if arquivo.get("source_after"):
        return arquivo["source_after"]
    return "\n".join(linha["line"] for linha in arquivo["added_lines"]) + "\n"


def main() -> None:
    repo = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        cwd=_RAIZ,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dataset = {pr["pr_id"]: pr for pr in json.loads(_DATASET.read_text(encoding="utf-8"))}
    total = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for par in sys.argv[1:]:
        pr_id, numero = par.split("=")
        arquivos = {f["filename"]: f for f in dataset[pr_id]["files"]}
        sinalizadas: set[tuple[str, str]] = set()
        for c in _gh(f"repos/{repo}/pulls/{numero}/comments"):
            arq = arquivos.get(c["path"])
            if arq is None:
                continue
            texto = texto_da_linha(_depois(arq).splitlines(), c.get("line"))
            if texto is not None:
                sinalizadas.add((c["path"], texto.strip()))
        print(f"\n== {pr_id} (PR #{numero})")
        for arq in dataset[pr_id]["files"]:
            for linha in arq["added_lines"]:
                chave = (arq["filename"], linha["line"].strip())
                if linha.get("ambiguo"):
                    estado = "sinalizada" if chave in sinalizadas else "nao sinalizada"
                    print(f"  ambigua {estado}: {linha['line']}")
                    continue
                sinal = chave in sinalizadas
                if linha["viola"]:
                    celula = "tp" if sinal else "fn"
                else:
                    celula = "fp" if sinal else "tn"
                total[celula] += 1
                if celula in ("fp", "fn"):
                    print(f"  {celula.upper()}: {arq['filename']}: {linha['line']}")
    print("\nTotal:", total)


if __name__ == "__main__":
    main()
