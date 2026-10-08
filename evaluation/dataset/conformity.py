"""Conformidade do codigo do dataset com o corpus inteiro (D-008).

Nao faz parte do sistema avaliado: confere que o material de teste nao
comete violacoes que o gabarito nao rotula. Cada achado e um par
(indice 0-based da linha, tag), onde a tag e um codigo do ruff ou uma
das checagens AST abaixo.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys

_RUFF_ARGS = [
    "check", "--isolated", "--no-cache", "--preview",
    "--output-format", "json", "--line-length", "79",
    "--select", "E,W,N,D,ANN001,ANN201,ANN202,ANN204,I,F403",
    "--ignore", "D105",
    "--config", "lint.pydocstyle.convention='google'",
    "--config", "lint.pycodestyle.max-doc-length=72",
    "--stdin-filename", "pr.py", "-",
]

# O achado que e a propria violacao rotulada so vale na linha positiva
# da sub-regra correspondente.
ALLOWED_BY_SUB = {
    "booleano": {"E712"},
    "nulo": {"E711"},
    "nome_funcao": {"N802"},
    "nome_classe": {"N801"},
    # N806: `O`/`I` dentro de funcao e a mesma violacao vista como maiuscula.
    "nome_proibido": {"E741", "N806", "uma-letra", "nome-de-modulo"},
}

GENERIC_NAMES = {"data", "info", "temp", "obj", "result", "cnt", "mx", "err", "val"}
_BOOL_PREFIXES = ("is_", "has_", "can_", "should_")
# pep8 2.1: `l`, `O` e `I` so aparecem na linha positiva que os atribui;
# ler o nome em outra linha seria uma violacao fora do gabarito.
_FORBIDDEN_NAMES = {"l", "O", "I"}
_SECRET = re.compile(r"://|sk-|password", re.IGNORECASE)
_UPPER = re.compile(r"^[A-Z][A-Z0-9_]*$")


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


def _name_findings(name: str, lineno: int) -> list[tuple[int, str]]:
    if len(name) == 1 and name not in ("i", "j", "_"):
        return [(lineno - 1, "uma-letra")]
    if name in GENERIC_NAMES:
        return [(lineno - 1, "nome-generico")]
    return []


def _params(fn: ast.FunctionDef) -> list[ast.arg]:
    params = [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]
    if params and params[0].arg in ("self", "cls"):
        params = params[1:]
    return params


def _function_findings(fn: ast.FunctionDef) -> list[tuple[int, str]]:
    idx = fn.lineno - 1
    out: list[tuple[int, str]] = []
    returns_bool = isinstance(fn.returns, ast.Name) and fn.returns.id == "bool"
    if returns_bool != fn.name.lstrip("_").startswith(_BOOL_PREFIXES):
        out.append((idx, "prefixo-booleano"))
    params = _params(fn)
    if len(params) > 4:
        out.append((idx, "muitos-parametros"))
    defaults = [d for d in (*fn.args.defaults, *fn.args.kw_defaults) if d is not None]
    if any(
        isinstance(p.annotation, ast.Name) and p.annotation.id == "bool"
        for p in params
    ) or any(
        isinstance(d, ast.Constant) and isinstance(d.value, bool) for d in defaults
    ):
        out.append((idx, "parametro-booleano"))
    doc = ast.get_docstring(fn)
    code_start = fn.body[1].lineno if doc and len(fn.body) > 1 else fn.body[0].lineno
    if fn.end_lineno - code_start + 1 > 30:
        out.append((idx, "funcao-longa"))
    if doc:
        returns_none = fn.returns is None or (
            isinstance(fn.returns, ast.Constant) and fn.returns.value is None
        )
        if params and "Args:" not in doc:
            out.append((idx, "docstring-sem-args"))
        if not returns_none and "Returns:" not in doc:
            out.append((idx, "docstring-sem-returns"))
        if any(isinstance(n, ast.Raise) for n in ast.walk(fn)) and "Raises:" not in doc:
            out.append((idx, "docstring-sem-raises"))
    return out


def ast_findings(code: str) -> list[tuple[int, str]]:
    tree = ast.parse(code)
    out: list[tuple[int, str]] = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id != "logger"
                    and not _UPPER.match(target.id)
                ):
                    out.append((node.lineno - 1, "nome-de-modulo"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out += _function_findings(node)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            out += _name_findings(node.id, node.lineno)
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            out.append((node.lineno - 1, "uso-nome-proibido"))
        elif isinstance(node, ast.arg):
            out += _name_findings(node.arg, node.lineno)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            out += _name_findings(node.name, node.lineno)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _SECRET.search(node.value)
        ):
            out.append((node.lineno - 1, "segredo"))
    return out


def conformity_errors(lines: list[str], sub_regras: list[str | None]) -> list[str]:
    """Achados que nao sao a propria violacao rotulada na linha."""
    code = "\n".join(lines)
    errors: list[str] = []
    for idx, tag in ruff_findings(code) + ast_findings(code):
        inside = 0 <= idx < len(lines)
        sub = sub_regras[idx] if inside else None
        if sub is not None and tag in ALLOWED_BY_SUB.get(sub, set()):
            continue
        text = lines[idx] if inside else ""
        errors.append(f"linha {idx}: {tag}: {text!r}")
    return errors
