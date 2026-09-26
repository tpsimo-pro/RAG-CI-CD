"""Validador do dataset do piloto (Secao 5 - Comparacoes).

Confere as contagens exigidas por D-004 e as invariantes de schema
descritas na tarefa. Nao depende de nada em evaluation/metrics.py ou
evaluation/run_evaluation.py (fora do escopo deste especialista).

Uso:
    python evaluation/dataset/validate_pilot_dataset.py
Saida: 0 se tudo passar, 1 caso contrario (com lista de falhas).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

# Rodado como script, a raiz do projeto nao esta no sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.dataset.conformity import conformity_errors  # noqa: E402

DATASET_PATH = Path(__file__).parent / "pilot_dataset.json"

# Catalogo minimo de negativos dificeis (D-004). Cada padrao precisa
# aparecer pelo menos uma vez em alguma linha marcada hard_negative=true.
HARD_NEGATIVE_CATALOG = {
    "is not None (if)": re.compile(r"^\s*if\s+.+\bis not None\s*:"),
    "is None (if)": re.compile(r"^\s*if\s+.+\bis None\s*:"),
    "flag simples (if x:)": re.compile(r"^\s*if\s+[A-Za-z_][\w.]*\s*:"),
    "not flag (if not x:)": re.compile(r"^\s*if not\s+[A-Za-z_][\w.]*\s*:"),
    "!= sem None": re.compile(r"^\s*if\s+.+!=\s*(?!None\b).+:"),
    "== sem bool/None": re.compile(
        r"^\s*if\s+.+==\s*(?!True\b|False\b|None\b).+:"
    ),
    "assert ... is None": re.compile(r"^\s*assert\s+.+\bis None\b"),
    "return ... is not None": re.compile(r"^\s*return\s+.+\bis not None\b"),
}

# Padroes de violacao esperados (D-002), usados para checar que toda
# linha marcada viola=True de fato contem a construcao proibida, e que
# nenhuma linha viola=False contem uma dessas construcoes (o que seria
# um rotulo inconsistente com o guia).
BOOLEAN_VIOLATION = re.compile(r"==\s*True\b|==\s*False\b")
NULL_VIOLATION = re.compile(r"!=\s*None\b|==\s*None\b")

# Emenda de D-002: Secao 2 restrita. Uma linha viola se o NOME declarado em
# `def`/`class` foge do padrao, ou se atribui/itera `l`, `O` ou `I`.
_DEF = re.compile(r"^\s*def\s+(\w+)")
_CLASS = re.compile(r"^\s*class\s+(\w+)")
_SNAKE = re.compile(r"^_{0,2}[a-z][a-z0-9_]*$")
_PASCAL = re.compile(r"^_?[A-Z][a-z0-9]*(?:[A-Z][a-z0-9]*)*$")
_SIGLA = re.compile(r"[A-Z]{2,}")
FORBIDDEN_NAME = re.compile(r"^\s*(?:for\s+)?(?:l|O|I)\s*(?:=(?!=)|\bin\b)")

SUB_REGRAS = {
    "secao-5": {"booleano", "nulo"},
    "secao-2": {"nome_funcao", "nome_classe", "nome_proibido"},
    "coding-4.1": {"captura_generica", "captura_silenciosa"},
}


def violation_kind(line: str) -> str | None:
    """Sub-regra que a linha viola segundo os padroes do guia, ou None."""
    if BOOLEAN_VIOLATION.search(line):
        return "booleano"
    if NULL_VIOLATION.search(line):
        return "nulo"
    m = _DEF.match(line)
    if m and not _SNAKE.match(m.group(1)):
        return "nome_funcao"
    m = _CLASS.match(line)
    if m and not _PASCAL.match(m.group(1)):
        return "nome_classe"
    if FORBIDDEN_NAME.match(line):
        return "nome_proibido"
    return None


HARD_NEGATIVE_CATALOG_SECAO2 = {
    "def __init__": re.compile(r"^\s*def\s+__init__\("),
    "def _privado": re.compile(r"^\s*def\s+_[a-z]\w*\("),
    "def snake_case": re.compile(r"^\s*def\s+[a-z]+_[a-z_]+\("),
    "class PascalCase": re.compile(r"^\s*class\s+[A-Z][a-z]+[A-Z]\w*[:(]"),
    "class ...Error(Exception)": re.compile(r"^\s*class\s+\w+Error\(Exception\):"),
    "lower = ...": re.compile(r"^\s*lower\s*="),
    "for i in ...": re.compile(r"^\s*for\s+i\s+in\b"),
    "for j in ...": re.compile(r"^\s*for\s+j\s+in\b"),
    "atributo .l": re.compile(r"\.l\b"),
    "comentario com l = 1": re.compile(r"^\s*#.*\bl\s*="),
    "string com l = 1": re.compile(r"[\"'][^\"']*\b[lOI]\s*=\s*1[\"']"),
}

# Emenda 2 de D-002: coding_standards.md 4.1. O rotulo depende do corpo do
# bloco, entao a checagem e feita sobre a AST do PR inteiro, nao por linha.
REGRA_EXCECAO = "coding-4.1"


def _is_logger_exception(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Attribute)
        and stmt.value.func.attr == "exception"
        and isinstance(stmt.value.func.value, ast.Name)
        and stmt.value.func.value.id == "logger"
    )


def except_labels(code: str) -> tuple[dict[int, str | None], list[str]]:
    """
    Rotulo de cada linha `except` pelo criterio da emenda 2 de D-002.

    Retorna (rotulos, erros): rotulos mapeia o indice 0-based da linha
    `except` para a sub_regra violada, ou None se o bloco nao viola; erros
    lista os blocos fora do escopo da emenda, que nao recebem rotulo.
    """
    labels: dict[int, str | None] = {}
    errors: list[str] = []
    for node in ast.walk(ast.parse(code)):
        if not isinstance(node, ast.ExceptHandler):
            continue
        idx = node.lineno - 1
        tipo = node.type
        if isinstance(tipo, ast.Name) and tipo.id == "Exception":
            sub = "captura_generica"
        elif isinstance(tipo, ast.Attribute) or (
            isinstance(tipo, ast.Name) and tipo.id != "BaseException"
        ):
            sub = "captura_silenciosa"
        else:
            errors.append(f"linha {idx}: except sem tipo, tupla ou BaseException")
            continue
        body = node.body
        if any(isinstance(n, ast.Try) for stmt in body for n in ast.walk(stmt)):
            errors.append(f"linha {idx}: try aninhado no except")
            continue
        logs = any(_is_logger_exception(stmt) for stmt in body)
        raises = [stmt for stmt in body if isinstance(stmt, ast.Raise)]
        # O guia pede re-raise "com contexto adicional": raise sem `from`
        # deixa o rotulo discutivel, em qualquer tipo de except.
        if raises and not logs and all(r.cause is None for r in raises):
            errors.append(f"linha {idx}: raise sem from")
            continue
        if logs or raises:
            labels[idx] = None
        elif (
            len(body) == 1
            and isinstance(body[0], (ast.Pass, ast.Continue))
            and body[0].lineno == node.lineno + 1
        ):
            labels[idx] = sub
        else:
            errors.append(f"linha {idx}: corpo do except fora do escopo")
    return labels, errors


def block_duplicates(
    lines: list[str], labels: dict[int, str | None]
) -> list[str]:
    """
    Linhas de bloco `except` repetidas no PR.

    classify_lines agrupa linhas de texto igual (D-003): sinalizar uma
    sinaliza todas. Um `except` repetido, ou o corpo de um bloco violador
    repetido, tornaria o rotulo da linha indistinguivel.
    """
    norm = [" ".join(text.split()) for text in lines]
    errors: list[str] = []
    for idx, sub in labels.items():
        if norm.count(norm[idx]) > 1:
            errors.append(f"linha {idx}: except repetido no PR: {lines[idx]!r}")
        if sub is not None and norm.count(norm[idx + 1]) > 1:
            errors.append(
                f"linha {idx + 1}: corpo de except violador repetido no PR: "
                f"{lines[idx + 1]!r}"
            )
    return errors


# Catalogo minimo da emenda 2. Os padroes de bloco casam a linha `except`
# (hard_negative) e a linha logo abaixo dela, o inicio do corpo.
_EXC_GENERICA = re.compile(r"^\s*except Exception\b")
_EXC_ESPECIFICA = re.compile(r"^\s*except (?!Exception\b|BaseException\b)[\w.]+")
_LOG_EXC = re.compile(r"^\s*logger\.exception\(")
_RAISE_FROM = re.compile(r"^\s*raise\s+\S.*\sfrom\s+\w+\s*$")
_PASS_TEXTO = r"except Exception:\s*pass"

HARD_NEGATIVE_CATALOG_EXCECAO = {
    "except Exception + logger.exception": (_EXC_GENERICA, _LOG_EXC),
    "except Exception + raise ... from": (_EXC_GENERICA, _RAISE_FROM),
    "except especifica + raise ... from": (_EXC_ESPECIFICA, _RAISE_FROM),
    "except especifica + logger.exception": (_EXC_ESPECIFICA, _LOG_EXC),
    "comentario com except Exception: pass": (
        re.compile(r"^\s*#.*" + _PASS_TEXTO),
        None,
    ),
    "string com except Exception: pass": (
        re.compile(r"[\"'][^\"']*" + _PASS_TEXTO + r"[^\"']*[\"']"),
        None,
    ),
}


def matches_exc_catalog(
    pattern: tuple[re.Pattern, re.Pattern | None], line: str, nxt: str
) -> bool:
    head, body = pattern
    return bool(head.search(line)) and (body is None or bool(body.search(nxt)))


def fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


def main() -> int:
    errors: list[str] = []

    raw_bytes = DATASET_PATH.read_bytes()
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        fail(errors, "Arquivo contem BOM UTF-8; deve ser UTF-8 sem BOM.")

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"FALHA CRITICA: JSON invalido ou nao-UTF-8: {exc}")
        return 1

    # --- Estrutura basica -------------------------------------------------
    if not isinstance(data, list):
        fail(errors, "Raiz do JSON deve ser uma lista de PRs.")
        print_report(errors)
        return 1

    pr_ids_seen: set[str] = set()
    all_lines: list[dict] = []
    control_prs = 0
    violation_prs = 0
    exc_pairs: list[tuple[str, str]] = []

    for pr in data:
        pr_id = pr.get("pr_id", "<sem pr_id>")

        for field in ("pr_id", "description", "filename", "patch", "added_lines"):
            if field not in pr:
                fail(errors, f"{pr_id}: campo obrigatorio ausente: {field}")

        if pr_id in pr_ids_seen:
            fail(errors, f"pr_id duplicado: {pr_id}")
        pr_ids_seen.add(pr_id)

        added_lines = pr.get("added_lines", [])
        if not (6 <= len(added_lines) <= 40):
            fail(
                errors,
                f"{pr_id}: {len(added_lines)} linhas adicionadas, fora do "
                f"intervalo esperado (6-40, D-008).",
            )

        has_violation = False
        texts = [e.get("line", "") for e in added_lines]
        try:
            labels, scope_errors = except_labels("\n".join(texts))
        except SyntaxError:
            # A falha de sintaxe ja e reportada pela checagem de ast.parse.
            labels, scope_errors = {}, []
        else:
            subs = [e.get("sub_regra") for e in added_lines]
            for msg in conformity_errors(texts, subs):
                fail(errors, f"{pr_id}: {msg} (D-008)")
        for msg in scope_errors + block_duplicates(texts, labels):
            fail(errors, f"{pr_id}: {msg} (emenda 2 de D-002)")

        for i, entry in enumerate(added_lines):
            loc = f"{pr_id}[{i}]"
            for field in ("line", "viola", "regra", "sub_regra", "hard_negative"):
                if field not in entry:
                    fail(errors, f"{loc}: campo ausente: {field}")
                    continue

            viola = entry.get("viola")
            sub_regra = entry.get("sub_regra")
            hard_negative = entry.get("hard_negative")
            line = entry.get("line", "")

            if not isinstance(viola, bool):
                fail(errors, f"{loc}: 'viola' deve ser bool.")
            if not isinstance(hard_negative, bool):
                fail(errors, f"{loc}: 'hard_negative' deve ser bool.")

            regra = entry.get("regra")
            if viola:
                if regra not in SUB_REGRAS or sub_regra not in SUB_REGRAS[regra]:
                    fail(
                        errors,
                        f"{loc}: viola=true exige regra/sub_regra coerentes, "
                        f"obtido {regra!r}/{sub_regra!r}.",
                    )
                has_violation = True
            else:
                if sub_regra is not None:
                    fail(
                        errors,
                        f"{loc}: viola=false mas sub_regra={sub_regra!r} "
                        f"(deveria ser null).",
                    )
                if hard_negative and regra not in SUB_REGRAS:
                    fail(errors, f"{loc}: hard_negative exige 'regra' valida.")
                if not hard_negative and regra is not None:
                    fail(errors, f"{loc}: negativo comum deve ter regra=null.")

            # hard_negative so pode ser true quando viola=false
            if hard_negative and viola:
                fail(
                    errors,
                    f"{loc}: hard_negative=true em linha com viola=true "
                    f"(inconsistente por definicao).",
                )

            # 'line' nao deve carregar o prefixo '+' do diff
            if line.startswith("+"):
                fail(errors, f"{loc}: 'line' nao deve conter o prefixo '+' do diff.")

            # Checagem semantica contra o guia (D-002 e emenda): a sub_regra
            # rotulada precisa ser a que os padroes do guia detectam na
            # linha, e nenhuma linha negativa pode conter construcao proibida
            # de nenhuma das tres regras.
            kind = labels[i] if i in labels else violation_kind(line)
            if viola and kind != sub_regra:
                fail(
                    errors,
                    f"{loc}: sub_regra={sub_regra!r} mas os padroes do guia "
                    f"detectam {kind!r}: {line!r}",
                )
            if not viola and kind is not None:
                fail(
                    errors,
                    f"{loc}: viola=false mas a linha contem construcao "
                    f"proibida ({kind}): {line!r}",
                )
            for rx in (_DEF, _CLASS):
                m = rx.match(line)
                if m and _SIGLA.search(m.group(1)):
                    fail(
                        errors,
                        f"{loc}: identificador com sigla fora do escopo "
                        f"(emenda de D-002): {line!r}",
                    )

            all_lines.append(entry)
            if hard_negative and regra == REGRA_EXCECAO:
                nxt = texts[i + 1] if i + 1 < len(texts) else ""
                exc_pairs.append((line, nxt))

        if has_violation:
            violation_prs += 1
        else:
            control_prs += 1

        # --- patch consistente com added_lines ---
        patch = pr.get("patch", "")
        patch_added = [
            l[1:] for l in patch.split("\n") if l.startswith("+")
        ]
        expected = [e["line"] for e in added_lines]
        if patch_added != expected:
            fail(
                errors,
                f"{pr_id}: patch inconsistente com added_lines "
                f"(diff: {patch_added} vs {expected}).",
            )
        if not re.match(r"^@@ -0,0 \+1,\d+ @@", patch):
            fail(errors, f"{pr_id}: cabecalho do hunk do patch invalido.")

        # --- snippet e Python sintaticamente valido ---
        code = "\n".join(expected)
        try:
            ast.parse(code)
        except SyntaxError as exc:
            fail(errors, f"{pr_id}: added_lines nao formam Python valido: {exc}")

        # --- linhas nao ultrapassam 79 colunas (Secao 1.1 do guia) ---
        for i, e in enumerate(added_lines):
            if len(e["line"]) > 79:
                fail(
                    errors,
                    f"{pr_id}[{i}]: linha com {len(e['line'])} caracteres "
                    f"(> 79), ruido de outra regra do guia.",
                )

    # --- Contagens globais (D-004) ----------------------------------------
    n_prs = len(data)
    n_lines = len(all_lines)
    positives = [l for l in all_lines if l["viola"]]
    negatives = [l for l in all_lines if not l["viola"]]
    hard_negatives = [l for l in negatives if l["hard_negative"]]
    by_sub = {
        sub: [l for l in positives if l["sub_regra"] == sub]
        for subs in SUB_REGRAS.values()
        for sub in subs
    }

    check_eq(errors, "Pull Requests", n_prs, 75)
    check_eq(errors, "PRs de controle (sem violacao)", control_prs, 21)
    check_eq(errors, "PRs com >=1 violacao", violation_prs, 54)
    check_range(errors, "Total de linhas adicionadas", n_lines, 1200, 3000)
    n_chars = sum(len(x["line"]) + 1 for x in all_lines)
    if n_chars > 90_000:
        fail(errors, f"Texto do dataset com {n_chars} caracteres (> 90000, D-008).")
    check_eq(errors, "Linhas positivas (violam)", len(positives), 132)
    for sub, expected in (
        ("booleano", 26),
        ("nulo", 26),
        ("nome_funcao", 16),
        ("nome_classe", 16),
        ("nome_proibido", 16),
        ("captura_generica", 16),
        ("captura_silenciosa", 16),
    ):
        check_eq(errors, f"Positivas - {sub}", len(by_sub[sub]), expected)
    check_eq(errors, "Negativos dificeis", len(hard_negatives), 132)
    check_eq(
        errors,
        "Negativos dificeis - coding-4.1",
        sum(1 for x in hard_negatives if x["regra"] == REGRA_EXCECAO),
        32,
    )

    # --- Cobertura do catalogo minimo de negativos dificeis ---------------
    hard_texts = [l["line"] for l in hard_negatives]
    catalog = {**HARD_NEGATIVE_CATALOG, **HARD_NEGATIVE_CATALOG_SECAO2}
    for name, pattern in catalog.items():
        if not any(pattern.search(t) for t in hard_texts):
            fail(
                errors,
                f"Catalogo de negativos dificeis sem cobertura: {name!r} "
                f"nao aparece em nenhuma linha hard_negative=true.",
            )
    for name, pattern in HARD_NEGATIVE_CATALOG_EXCECAO.items():
        if not any(matches_exc_catalog(pattern, ln, nx) for ln, nx in exc_pairs):
            fail(
                errors,
                f"Catalogo de negativos dificeis sem cobertura: {name!r} "
                f"nao aparece em nenhum hard_negative da regra coding-4.1.",
            )

    print_report(errors)
    print("\n--- Resumo de contagens ---")
    print(f"PRs totais:              {n_prs}")
    print(f"PRs de controle:         {control_prs}")
    print(f"PRs com violacao:        {violation_prs}")
    print(f"Linhas adicionadas (N):  {n_lines}")
    print(f"Caracteres do dataset:   {n_chars}")
    print(f"Linhas positivas:        {len(positives)} "
          + ", ".join(f"{k}={len(v)}" for k, v in by_sub.items()))
    print(f"Linhas negativas:        {len(negatives)}")
    print(f"  dos quais dificeis:    {len(hard_negatives)}")
    print("\nCobertura do catalogo minimo de negativos dificeis:")
    for name, pattern in catalog.items():
        count = sum(1 for t in hard_texts if pattern.search(t))
        print(f"  {name:<28} {count}x")
    for name, pattern in HARD_NEGATIVE_CATALOG_EXCECAO.items():
        count = sum(1 for ln, nx in exc_pairs if matches_exc_catalog(pattern, ln, nx))
        print(f"  {name:<28} {count}x")

    return 1 if errors else 0


def check_eq(errors: list[str], label: str, actual: int, expected: int) -> None:
    if actual != expected:
        fail(errors, f"{label}: esperado {expected}, obtido {actual}.")


def check_range(errors: list[str], label: str, actual: int, lo: int, hi: int) -> None:
    if not (lo <= actual <= hi):
        fail(errors, f"{label}: esperado entre {lo} e {hi}, obtido {actual}.")


def print_report(errors: list[str]) -> None:
    if errors:
        print(f"FALHAS ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
    else:
        print("Todas as verificacoes de schema passaram.")


if __name__ == "__main__":
    sys.exit(main())
