"""
montar_prs_demo.py - Monta as branches dos PRs de teste do workflow (D-011).

Para cada PR do dataset escolhido:
  - `demo/base` recebe o estado "antes" dos arquivos modificados;
  - `demo/<pr_id>` parte de `demo/base` e recebe o estado "depois".
Não faz push nem abre o PR: quem abre é o autor (gh pr create), um a um.

Uso:
    python -m scripts.montar_prs_demo PR-003 PR-007 PR-021
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
_DATASET = _RAIZ / "evaluation" / "dataset" / "pilot_dataset.json"
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def reconstruir_antes(source_after: str, patch: str) -> str:
    """Desfaz o patch sobre o arquivo `depois`: tira as adições e devolve as remoções."""
    depois = source_after.splitlines()
    saida: list[str] = []
    cursor = 0  # índice em `depois`
    linhas = patch.splitlines()
    i = 0
    while i < len(linhas):
        casou = _HUNK.match(linhas[i])
        if not casou:
            i += 1
            continue
        inicio_novo = int(casou.group(3)) - 1
        saida.extend(depois[cursor:inicio_novo])
        cursor = inicio_novo
        i += 1
        while i < len(linhas) and not linhas[i].startswith("@@"):
            marca, texto = linhas[i][:1], linhas[i][1:]
            if marca == "+":
                cursor += 1
            elif marca == "-":
                saida.append(texto)
            elif marca == " ":
                saida.append(depois[cursor])
                cursor += 1
            i += 1
    saida.extend(depois[cursor:])
    return "\n".join(saida) + "\n"


def _git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=_RAIZ, check=True)


def _escrever(caminho: str, conteudo: str) -> None:
    destino = _RAIZ / caminho
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8", newline="\n")


def _depois(arquivo: dict) -> str:
    """Conteúdo do arquivo depois da mudança (novo: as linhas adicionadas)."""
    if arquivo.get("source_after"):
        return arquivo["source_after"]
    return "\n".join(linha["line"] for linha in arquivo["added_lines"]) + "\n"


def main() -> None:
    ids = sys.argv[1:]
    dataset = {pr["pr_id"]: pr for pr in json.loads(_DATASET.read_text(encoding="utf-8"))}
    _git("checkout", "-B", "demo/base", "main")
    for pr_id in ids:
        for arq in dataset[pr_id]["files"]:
            if arq["status"] == "modified":
                _escrever(arq["filename"], reconstruir_antes(arq["source_after"], arq["patch"]))
    _git("add", "app")
    _git("commit", "-m", "demo: estado anterior dos arquivos modificados")
    for pr_id in ids:
        _git("checkout", "-B", f"demo/{pr_id.lower()}", "demo/base")
        for arq in dataset[pr_id]["files"]:
            _escrever(arq["filename"], _depois(arq))
        _git("add", "app")
        _git("commit", "-m", f"demo: {pr_id}")
    _git("checkout", "main")


if __name__ == "__main__":
    main()
