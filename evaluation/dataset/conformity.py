"""Conformidade do codigo do dataset com a PEP 8 (D-008, D-009, D-010).

Nao faz parte do sistema avaliado: confere que o material de teste nao
comete violacoes da PEP 8 que o gabarito nao rotula. Cada achado e um par
(indice 0-based da linha, tag), onde a tag e um codigo do ruff ou uma
das checagens AST abaixo. So entra aqui o que a PEP 8 manda: layout,
nomes, imports e espacos (ruff E, W, N, I), mais o nome `l`/`O`/`I`.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys

from evaluation.dataset.norms import NORMAS

_RUFF_ARGS = [
    "check", "--isolated", "--no-cache", "--preview",
    "--output-format", "json", "--line-length", "79",
    "--select", "E,W,N,I,F403",
    "--config", "lint.pycodestyle.max-doc-length=72",
    "--stdin-filename", "pr.py", "-",
]

# O achado que e a propria violacao rotulada so vale na linha positiva da
# norma correspondente: os codigos do ruff do catalogo e, se a norma tambem
# tem checagem AST, a propria tag (D-010).
ALLOWED_BY_SUB = {
    n.id: set(n.ruff) | ({n.id} if n.ast else set()) for n in NORMAS
}

# PEP 8: `l`, `O` e `I` nunca como nome; so aparecem na linha positiva que
# os atribui, e ler o nome em outra linha seria uma violacao fora do gabarito.
_FORBIDDEN_NAMES = {"l", "O", "I"}


def ruff_findings(code: str) -> list[tuple[int, str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", *_RUFF_ARGS],
        input=code + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [
        (d["location"]["row"] - 1, d["code"]) for d in json.loads(proc.stdout)
    ]


def _is_logger_exception(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Attribute)
        and stmt.value.func.attr == "exception"
        and isinstance(stmt.value.func.value, ast.Name)
        and stmt.value.func.value.id == "logger"
    )


def tolerated_bare_excepts(code: str) -> set[int]:
    """Linhas de `except:` nu que a PEP 8 tolera.

    A PEP 8 aceita o `except:` nu em dois casos: o handler registra o
    traceback, ou faz limpeza e relanca com `raise`. O ruff (E722) acusa
    qualquer `except:` nu, entao estes sao descontados do achado.
    """
    tolerated: set[int] = set()
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            if any(
                isinstance(stmt, ast.Raise) or _is_logger_exception(stmt)
                for stmt in node.body
            ):
                tolerated.add(node.lineno - 1)
    return tolerated


_UPPER = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
_SNAKE = re.compile(r"^_{0,2}[a-z][a-z0-9_]*_{0,2}$")


def _is_literal(node: ast.expr | None) -> bool:
    if isinstance(node, ast.Constant):
        return True
    return isinstance(node, ast.Tuple) and all(_is_literal(e) for e in node.elts)


def ast_findings(code: str) -> list[tuple[int, str]]:
    tree = ast.parse(code)
    out: list[tuple[int, str]] = []
    # PEP 8: constantes de modulo em MAIUSCULAS. Vale o literal atribuido a
    # um nome que nao e MAIUSCULO nem snake_case (CapWords ou mixedCase);
    # variavel global em snake_case e legitima pela propria PEP 8.
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            alvo, valor = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            alvo, valor = node.target, node.value
        else:
            continue
        if (
            isinstance(alvo, ast.Name)
            and _is_literal(valor)
            and not _UPPER.match(alvo.id)
            and not _SNAKE.match(alvo.id)
        ):
            out.append((node.lineno - 1, "constante_maiuscula"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            if not isinstance(node.ctx, ast.Store):
                out.append((node.lineno - 1, "uso-nome-proibido"))
    return out


def conformity_errors(
    lines: list[str],
    sub_regras: list[str | None],
    alvo: set[int] | None = None,
) -> list[str]:
    """Achados que nao sao a propria violacao rotulada na linha.

    `lines` e o arquivo inteiro e `sub_regras` a norma de cada linha (None se
    nao rotulada). `alvo` limita a checagem as linhas adicionadas (indices
    0-based); achados em linhas de contexto sao codigo pre-existente.
    """
    code = "\n".join(lines)
    tolerated = tolerated_bare_excepts(code)
    errors: list[str] = []
    for idx, tag in ruff_findings(code) + ast_findings(code):
        if alvo is not None and idx not in alvo:
            continue
        if tag == "E722" and idx in tolerated:
            continue
        inside = 0 <= idx < len(lines)
        sub = sub_regras[idx] if inside else None
        if sub is not None and tag in ALLOWED_BY_SUB.get(sub, set()):
            continue
        text = lines[idx] if inside else ""
        errors.append(f"linha {idx}: {tag}: {text!r}")
    return errors
