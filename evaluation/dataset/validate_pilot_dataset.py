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

DATASET_PATH = Path(__file__).parent / "pilot_secao5.json"

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

    for pr in data:
        pr_id = pr.get("pr_id", "<sem pr_id>")

        for field in ("pr_id", "description", "filename", "patch", "added_lines"):
            if field not in pr:
                fail(errors, f"{pr_id}: campo obrigatorio ausente: {field}")

        if pr_id in pr_ids_seen:
            fail(errors, f"pr_id duplicado: {pr_id}")
        pr_ids_seen.add(pr_id)

        added_lines = pr.get("added_lines", [])
        if not (6 <= len(added_lines) <= 15):
            fail(
                errors,
                f"{pr_id}: {len(added_lines)} linhas adicionadas, fora do "
                f"intervalo esperado (~6-15).",
            )

        has_violation = False
        for i, entry in enumerate(added_lines):
            loc = f"{pr_id}[{i}]"
            for field in ("line", "viola", "sub_regra", "hard_negative"):
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

            # sub_regra so pode ser nao-nulo quando viola=true
            if viola:
                if sub_regra not in ("booleano", "nulo"):
                    fail(
                        errors,
                        f"{loc}: viola=true exige sub_regra em "
                        f"{{'booleano','nulo'}}, obtido {sub_regra!r}.",
                    )
                has_violation = True
            else:
                if sub_regra is not None:
                    fail(
                        errors,
                        f"{loc}: viola=false mas sub_regra={sub_regra!r} "
                        f"(deveria ser null).",
                    )

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

            # Checagem semantica contra o guia (D-002): toda linha marcada
            # como violacao booleana/nula precisa realmente conter a
            # construcao proibida, e vice-versa (nenhuma linha negativa
            # deveria conter == True/False ou != None/== None "soltos").
            if sub_regra == "booleano" and not BOOLEAN_VIOLATION.search(line):
                fail(
                    errors,
                    f"{loc}: sub_regra=booleano mas a linha nao contem "
                    f"'== True'/'== False': {line!r}",
                )
            if sub_regra == "nulo" and not NULL_VIOLATION.search(line):
                fail(
                    errors,
                    f"{loc}: sub_regra=nulo mas a linha nao contem "
                    f"'!= None'/'== None': {line!r}",
                )
            if not viola:
                if BOOLEAN_VIOLATION.search(line) or NULL_VIOLATION.search(line):
                    fail(
                        errors,
                        f"{loc}: viola=false mas a linha contem uma "
                        f"construcao proibida pela Secao 5: {line!r}",
                    )

            all_lines.append(entry)

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
    bool_pos = [l for l in positives if l["sub_regra"] == "booleano"]
    null_pos = [l for l in positives if l["sub_regra"] == "nulo"]

    check_eq(errors, "Pull Requests", n_prs, 30)
    check_eq(errors, "PRs de controle (sem violacao)", control_prs, 8)
    check_eq(errors, "PRs com >=1 violacao", violation_prs, 22)
    check_range(errors, "Total de linhas adicionadas", n_lines, 290, 310)
    check_eq(errors, "Linhas positivas (violam)", len(positives), 60)
    check_eq(errors, "Positivas - booleano", len(bool_pos), 30)
    check_eq(errors, "Positivas - nulo", len(null_pos), 30)
    check_eq(errors, "Negativos dificeis", len(hard_negatives), 60)

    # --- Cobertura do catalogo minimo de negativos dificeis ---------------
    hard_texts = [l["line"] for l in hard_negatives]
    for name, pattern in HARD_NEGATIVE_CATALOG.items():
        if not any(pattern.search(t) for t in hard_texts):
            fail(
                errors,
                f"Catalogo de negativos dificeis sem cobertura: {name!r} "
                f"nao aparece em nenhuma linha hard_negative=true.",
            )

    print_report(errors)
    print("\n--- Resumo de contagens ---")
    print(f"PRs totais:              {n_prs}")
    print(f"PRs de controle:         {control_prs}")
    print(f"PRs com violacao:        {violation_prs}")
    print(f"Linhas adicionadas (N):  {n_lines}")
    print(f"Linhas positivas:        {len(positives)} "
          f"(booleano={len(bool_pos)}, nulo={len(null_pos)})")
    print(f"Linhas negativas:        {len(negatives)}")
    print(f"  dos quais dificeis:    {len(hard_negatives)}")
    print("\nCobertura do catalogo minimo de negativos dificeis:")
    for name, pattern in HARD_NEGATIVE_CATALOG.items():
        count = sum(1 for t in hard_texts if pattern.search(t))
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
