"""Validador do dataset do piloto (23 normas da PEP 8, schema v2, D-010).

Confere o schema (SCHEMA.md), a consistencia do patch e a composicao exigida.
O ruff e uma checagem AST sao o oraculo do rotulo: toda violacao numa linha
adicionada precisa estar rotulada, e todo rotulo positivo precisa disparar a
propria norma. Nao depende de evaluation/metrics.py nem de run_evaluation.py.

Uso:
    python evaluation/dataset/validate_pilot_dataset.py
Saida: 0 se tudo passar, 1 caso contrario (com lista de falhas).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Rodado como script, a raiz do projeto nao esta no sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.dataset.conformity import (  # noqa: E402
    ALLOWED_BY_SUB,
    ast_findings,
    conformity_errors,
    ruff_findings,
)
from evaluation.dataset.norms import (  # noqa: E402
    FAMILIAS,
    NEGATIVOS,
    NORMAS,
    NORMAS_POR_ID,
)
from evaluation.dataset.patch import PatchError, parse_patch  # noqa: E402

DATASET_PATH = Path(__file__).parent / "pilot_dataset.json"

# Composicao exigida (spec 2026-10-08-dataset-realista-design.md).
N_PRS = 25
N_PRS_LIMPOS = 5
N_ARQUIVOS = 35
N_NOVOS = 21
N_MODIFICADOS = 14
PRS_POR_N_ARQUIVOS = {1: 16, 2: 8, 3: 1}
LINHAS_POR_ARQUIVO = (8, 60)
NORMAS_POR_PR_VIOLADOR = (2, 5)
MIN_POSITIVAS_POR_NORMA = 4
MIN_PRS_POR_NORMA = 2
MIN_NEGATIVOS_POR_NORMA = 2

SUB_REGRAS = {
    familia: {n.id for n in NORMAS if n.familia == familia} for familia in FAMILIAS
}

# O rotulo do `except:` depende do corpo do bloco, entao a checagem e feita
# sobre a AST do arquivo, nao por linha. A PEP 8 tolera o `except:` nu quando o
# handler registra o traceback ou relanca; `except Exception:` nunca viola.
_DEF = re.compile(r"^\s*def\s+(\w+)")
_CLASS = re.compile(r"^\s*class\s+(\w+)")
_SIGLA = re.compile(r"[A-Z]{2,}")
FAMILIA_EXCECAO = "pep8-recomendacoes"


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
    Rotulo de cada linha `except` pelo criterio da PEP 8.

    Retorna (rotulos, erros): rotulos mapeia o indice 0-based da linha
    `except` para a sub_regra violada, ou None se o bloco nao viola; erros
    lista os blocos fora do escopo ("linha N: ..."), que nao recebem rotulo.

    O `except:` nu viola quando o corpo e so `pass`/`continue`, e nao viola
    quando o handler registra o traceback ou relanca. Um `except` com tipo
    nunca viola; seu corpo so precisa ser uma das mesmas formas.
    """
    labels: dict[int, str | None] = {}
    errors: list[str] = []
    for node in ast.walk(ast.parse(code)):
        if not isinstance(node, ast.ExceptHandler):
            continue
        idx = node.lineno - 1
        body = node.body
        if any(isinstance(n, ast.Try) for stmt in body for n in ast.walk(stmt)):
            errors.append(f"linha {idx}: try aninhado no except")
            continue
        registra_ou_relanca = any(
            _is_logger_exception(stmt) or isinstance(stmt, ast.Raise)
            for stmt in body
        )
        silencioso = (
            len(body) == 1
            and isinstance(body[0], (ast.Pass, ast.Continue))
            and body[0].lineno == node.lineno + 1
        )
        if registra_ou_relanca:
            labels[idx] = None
        elif silencioso:
            labels[idx] = "except_nu" if node.type is None else None
        else:
            errors.append(f"linha {idx}: corpo do except fora do escopo")
    return labels, errors


def block_duplicates(
    lines: list[str], labels: dict[int, str | None]
) -> list[str]:
    """
    Linhas de bloco `except` repetidas no arquivo.

    classify_lines agrupa linhas de texto igual (D-003): sinalizar uma
    sinaliza todas. Um `except` repetido, ou o corpo de um bloco violador
    repetido, tornaria o rotulo da linha indistinguivel.
    """
    norm = [" ".join(text.split()) for text in lines]
    errors: list[str] = []
    for idx, sub in labels.items():
        if norm.count(norm[idx]) > 1:
            errors.append(f"linha {idx}: except repetido no arquivo: {lines[idx]!r}")
        if sub is not None and norm.count(norm[idx + 1]) > 1:
            errors.append(
                f"linha {idx + 1}: corpo de except violador repetido no arquivo: "
                f"{lines[idx + 1]!r}"
            )
    return errors


# Catalogo do `except` (pares cabecalho + inicio do corpo), que as formas
# de uma linha em NEGATIVOS nao descrevem. Cada padrao precisa aparecer.
_EXC_NU = re.compile(r"^\s*except\s*:")
_EXC_GENERICA = re.compile(r"^\s*except Exception\b")
_EXC_ESPECIFICA = re.compile(r"^\s*except (?!Exception\b|BaseException\b)[\w.]+")
_LOG_EXC = re.compile(r"^\s*logger\.exception\(")
_RAISE_FROM = re.compile(r"^\s*raise\s+\S.*\sfrom\s+\w+\s*$")
_RAISE_PURO = re.compile(r"^\s*raise\s*$")
_PASS_OU_CONTINUE = re.compile(r"^\s*(?:pass|continue)\s*$")
_PASS_TEXTO = r"except Exception:\s*pass"

HARD_NEGATIVE_CATALOG_EXCECAO = {
    "except Exception + logger.exception": (_EXC_GENERICA, _LOG_EXC),
    "except Exception + raise ... from": (_EXC_GENERICA, _RAISE_FROM),
    "except especifica + raise ... from": (_EXC_ESPECIFICA, _RAISE_FROM),
    "except especifica + logger.exception": (_EXC_ESPECIFICA, _LOG_EXC),
    "except Exception + pass (PEP 8 recomenda)": (
        _EXC_GENERICA,
        _PASS_OU_CONTINUE,
    ),
    "except especifica + pass/continue": (_EXC_ESPECIFICA, _PASS_OU_CONTINUE),
    "except nu + logger.exception (tolerado)": (_EXC_NU, _LOG_EXC),
    "except nu + raise (tolerado)": (_EXC_NU, _RAISE_PURO),
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


class Estatisticas:
    """Contagens acumuladas do dataset, para a composicao exigida."""

    def __init__(self) -> None:
        self.positivas: Counter[str] = Counter()
        self.prs_da_norma: dict[str, set[str]] = defaultdict(set)
        self.negativos: Counter[str] = Counter()
        self.exc_pairs: list[tuple[str, str]] = []
        self.linhas_positivas = 0
        self.linhas_negativas = 0
        self.linhas_dificeis = 0
        self.n_linhas = 0


def _source_lines(arquivo: dict) -> list[str]:
    if arquivo.get("status") == "modified":
        return arquivo.get("source_after", "").split("\n")
    return [e.get("line", "") for e in arquivo.get("added_lines", [])]


def _mapa_linhas(
    pr_id: str, arquivo: dict, errors: list[str]
) -> list[int] | None:
    """Indice 0-based, na fonte, de cada entrada de added_lines (ou None)."""
    added = arquivo.get("added_lines", [])
    patch = arquivo.get("patch", "")
    loc = f"{pr_id}:{arquivo.get('filename')}"
    try:
        partes = parse_patch(patch)
    except PatchError as exc:
        fail(errors, f"{loc}: patch invalido: {exc}")
        return None
    mais = [(n, t) for tipo, n, t in partes if tipo == "+" and n]
    if [t for _, t in mais] != [e.get("line") for e in added]:
        fail(errors, f"{loc}: patch inconsistente com added_lines.")
        return None
    status = arquivo.get("status")
    if status == "added":
        if not re.match(r"^@@ -0,0 \+1,\d+ @@", patch):
            fail(errors, f"{loc}: cabecalho do hunk de arquivo novo invalido.")
        if len(partes) != len(mais):
            fail(errors, f"{loc}: arquivo novo so pode ter linhas '+'.")
        return [n - 1 for n, _ in mais]
    fonte = _source_lines(arquivo)
    for tipo, n, texto in partes:
        if tipo in (" ", "+") and (n is None or n > len(fonte) or fonte[n - 1] != texto):
            fail(errors, f"{loc}: patch nao bate com source_after na linha {n}.")
            return None
    return [n - 1 for n, _ in mais]


def _validar_entradas(
    pr_id: str, arquivo: dict, errors: list[str]
) -> bool:
    """Campos, tipos e coerencia viola/regra/sub_regra/hard_negative."""
    ok = True
    loc0 = f"{pr_id}:{arquivo.get('filename')}"
    for campo in ("filename", "status", "patch", "added_lines"):
        if campo not in arquivo:
            fail(errors, f"{loc0}: campo obrigatorio ausente: {campo}")
            ok = False
    if not ok:
        return False
    if arquivo["status"] not in ("added", "modified"):
        fail(errors, f"{loc0}: status invalido: {arquivo['status']!r}")
        ok = False
    if arquivo["status"] == "modified" and "source_after" not in arquivo:
        fail(errors, f"{loc0}: arquivo modified exige source_after.")
        ok = False
    if arquivo["status"] == "added" and "source_after" in arquivo:
        fail(errors, f"{loc0}: arquivo added nao tem source_after.")
        ok = False
    if not str(arquivo["filename"]).endswith(".py"):
        fail(errors, f"{loc0}: filename deve terminar em .py.")
        ok = False
    n = len(arquivo["added_lines"])
    if not (LINHAS_POR_ARQUIVO[0] <= n <= LINHAS_POR_ARQUIVO[1]):
        fail(errors, f"{loc0}: {n} linhas adicionadas, fora de {LINHAS_POR_ARQUIVO}.")
    for i, e in enumerate(arquivo["added_lines"]):
        loc = f"{loc0}[{i}]"
        for campo in ("line", "viola", "regra", "sub_regra", "hard_negative"):
            if campo not in e:
                fail(errors, f"{loc}: campo ausente: {campo}")
                ok = False
        if not ok:
            continue
        if not isinstance(e["viola"], bool) or not isinstance(e["hard_negative"], bool):
            fail(errors, f"{loc}: 'viola' e 'hard_negative' devem ser bool.")
            ok = False
            continue
        if e["line"].startswith("+"):
            fail(errors, f"{loc}: 'line' nao deve conter o prefixo '+' do diff.")
        if e["viola"]:
            norma = NORMAS_POR_ID.get(e["sub_regra"])
            if norma is None or e["regra"] != norma.familia:
                fail(
                    errors,
                    f"{loc}: viola=true exige regra/sub_regra do catalogo, "
                    f"obtido {e['regra']!r}/{e['sub_regra']!r}.",
                )
                ok = False
            elif norma.so_arquivo_novo and arquivo["status"] == "modified":
                fail(
                    errors,
                    f"{loc}: {norma.id} depende da vizinhanca e so vale em "
                    "arquivo novo.",
                )
            if e["hard_negative"]:
                fail(errors, f"{loc}: hard_negative=true com viola=true.")
        else:
            if e["sub_regra"] is not None:
                fail(errors, f"{loc}: viola=false mas sub_regra={e['sub_regra']!r}.")
            if e["hard_negative"] and e["regra"] not in FAMILIAS:
                fail(errors, f"{loc}: hard_negative exige 'regra' valida.")
            if not e["hard_negative"] and e["regra"] is not None:
                fail(errors, f"{loc}: negativo comum deve ter regra=null.")
    return ok


def validar_arquivo(
    pr_id: str, arquivo: dict, errors: list[str], stats: Estatisticas
) -> set[str]:
    """Valida um arquivo do PR e devolve as normas positivas que ele traz."""
    loc0 = f"{pr_id}:{arquivo.get('filename')}"
    if not _validar_entradas(pr_id, arquivo, errors):
        return set()
    mapa = _mapa_linhas(pr_id, arquivo, errors)
    if mapa is None:
        return set()
    fonte = _source_lines(arquivo)
    codigo = "\n".join(fonte)
    try:
        ast.parse(codigo)
    except SyntaxError as exc:
        fail(errors, f"{loc0}: o arquivo nao e Python valido: {exc}")
        return set()

    added = arquivo["added_lines"]
    subs: list[str | None] = [None] * len(fonte)
    for src_idx, e in zip(mapa, added):
        subs[src_idx] = e["sub_regra"] if e["viola"] else None
    alvo = set(mapa)

    # Oraculo 1: nenhum achado sem rotulo nas linhas adicionadas.
    for msg in conformity_errors(fonte, subs, alvo):
        fail(errors, f"{loc0}: {msg} (oraculo)")

    # Oraculo 2: todo rotulo positivo dispara a propria norma.
    tags: dict[int, set[str]] = defaultdict(set)
    for idx, tag in ruff_findings(codigo) + ast_findings(codigo):
        tags[idx].add(tag)
    rotulos_exc, erros_exc = except_labels(codigo)
    for msg in erros_exc:
        idx = int(re.match(r"linha (\d+):", msg).group(1))
        if idx in alvo:
            fail(errors, f"{loc0}: {msg}")
    for msg in block_duplicates(fonte, {i: rotulos_exc[i] for i in rotulos_exc if i in alvo}):
        fail(errors, f"{loc0}: {msg}")

    # D-003: classify_lines agrupa linhas de texto igual no arquivo; um texto
    # positivo e negativo ao mesmo tempo tornaria o rotulo indecidivel.
    rotulos_por_texto: dict[str, set[bool]] = defaultdict(set)
    for e in added:
        texto = " ".join(e["line"].split())
        if texto:
            rotulos_por_texto[texto].add(e["viola"])
    for texto, rotulos in rotulos_por_texto.items():
        if len(rotulos) > 1:
            fail(errors, f"{loc0}: texto positivo e negativo ao mesmo tempo: {texto!r}")

    positivas: set[str] = set()
    for i, (src_idx, e) in enumerate(zip(mapa, added)):
        loc = f"{loc0}[{i}]"
        stats.n_linhas += 1
        if e["viola"]:
            stats.linhas_positivas += 1
            sub = e["sub_regra"]
            positivas.add(sub)
            stats.positivas[sub] += 1
            stats.prs_da_norma[sub].add(pr_id)
            if not tags[src_idx] & ALLOWED_BY_SUB.get(sub, set()):
                fail(errors, f"{loc}: {sub} rotulada, mas nenhum oraculo a detecta: {e['line']!r}")
            if sub == "except_nu" and rotulos_exc.get(src_idx) != "except_nu":
                fail(errors, f"{loc}: except_nu exige `except:` nu com corpo so pass/continue.")
        else:
            stats.linhas_negativas += 1
            if src_idx in rotulos_exc and rotulos_exc[src_idx] is not None:
                fail(errors, f"{loc}: viola=false mas o except viola: {e['line']!r}")
            if e["hard_negative"]:
                stats.linhas_dificeis += 1
                for sub in SUB_REGRAS.get(e["regra"], ()):
                    if any(p.search(e["line"]) for p in NEGATIVOS[sub]):
                        stats.negativos[sub] += 1
                nxt = added[i + 1]["line"] if i + 1 < len(added) else ""
                stats.exc_pairs.append((e["line"], nxt))
        for rx in (_DEF, _CLASS):
            m = rx.match(e["line"])
            if m and _SIGLA.search(m.group(1)):
                fail(errors, f"{loc}: identificador com sigla fora do escopo: {e['line']!r}")
    return positivas


def validar_dataset(data: list) -> tuple[list[str], Estatisticas, dict]:
    errors: list[str] = []
    stats = Estatisticas()
    resumo = {"limpos": 0, "violadores": 0, "novos": 0, "modificados": 0,
              "arquivos": 0, "prs_por_n_arquivos": Counter()}
    vistos: set[str] = set()
    for pr in data:
        pr_id = pr.get("pr_id", "<sem pr_id>")
        for campo in ("pr_id", "description", "files"):
            if campo not in pr:
                fail(errors, f"{pr_id}: campo obrigatorio ausente: {campo}")
        if pr_id in vistos:
            fail(errors, f"pr_id duplicado: {pr_id}")
        vistos.add(pr_id)
        arquivos = pr.get("files", [])
        resumo["prs_por_n_arquivos"][len(arquivos)] += 1
        nomes = [a.get("filename") for a in arquivos]
        if len(set(nomes)) != len(nomes):
            fail(errors, f"{pr_id}: filename repetido no PR.")
        normas_pr: set[str] = set()
        for a in arquivos:
            resumo["arquivos"] += 1
            if a.get("status") == "added":
                resumo["novos"] += 1
            elif a.get("status") == "modified":
                resumo["modificados"] += 1
            normas_pr |= validar_arquivo(pr_id, a, errors, stats)
        if normas_pr:
            resumo["violadores"] += 1
            lo, hi = NORMAS_POR_PR_VIOLADOR
            if not (lo <= len(normas_pr) <= hi):
                fail(errors, f"{pr_id}: {len(normas_pr)} normas distintas, fora de {lo}-{hi}.")
        else:
            resumo["limpos"] += 1
    return errors, stats, resumo


def checar_composicao(
    errors: list[str], stats: Estatisticas, resumo: dict, n_prs: int
) -> None:
    check_eq(errors, "Pull Requests", n_prs, N_PRS)
    check_eq(errors, "PRs limpos", resumo["limpos"], N_PRS_LIMPOS)
    check_eq(errors, "PRs violadores", resumo["violadores"], N_PRS - N_PRS_LIMPOS)
    check_eq(errors, "Arquivos", resumo["arquivos"], N_ARQUIVOS)
    check_eq(errors, "Arquivos novos", resumo["novos"], N_NOVOS)
    check_eq(errors, "Arquivos modificados", resumo["modificados"], N_MODIFICADOS)
    for n, esperado in PRS_POR_N_ARQUIVOS.items():
        check_eq(errors, f"PRs com {n} arquivo(s)", resumo["prs_por_n_arquivos"][n], esperado)
    for norma in NORMAS:
        n = stats.positivas[norma.id]
        if n < MIN_POSITIVAS_POR_NORMA:
            fail(errors, f"{norma.id}: {n} linhas positivas, minimo {MIN_POSITIVAS_POR_NORMA}.")
        prs = len(stats.prs_da_norma[norma.id])
        if prs < MIN_PRS_POR_NORMA:
            fail(errors, f"{norma.id}: presente em {prs} PR(s), minimo {MIN_PRS_POR_NORMA}.")
        if stats.negativos[norma.id] < MIN_NEGATIVOS_POR_NORMA:
            fail(
                errors,
                f"{norma.id}: {stats.negativos[norma.id]} negativos dificeis, "
                f"minimo {MIN_NEGATIVOS_POR_NORMA}.",
            )
    for nome, padrao in HARD_NEGATIVE_CATALOG_EXCECAO.items():
        if not any(matches_exc_catalog(padrao, ln, nx) for ln, nx in stats.exc_pairs):
            fail(errors, f"Catalogo de excecao sem cobertura: {nome!r}.")


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
    if not isinstance(data, list):
        print("FALHA CRITICA: raiz do JSON deve ser uma lista de PRs.")
        return 1

    erros_ds, stats, resumo = validar_dataset(data)
    errors += erros_ds
    checar_composicao(errors, stats, resumo, len(data))

    print_report(errors)
    print("\n--- Resumo de contagens ---")
    print(f"PRs: {len(data)} (limpos {resumo['limpos']}, violadores {resumo['violadores']})")
    print(f"Arquivos: {resumo['arquivos']} (novos {resumo['novos']}, modificados {resumo['modificados']})")
    print(f"Linhas adicionadas: {stats.n_linhas}")
    print(f"Positivas: {stats.linhas_positivas}; negativas: {stats.linhas_negativas}; dificeis: {stats.linhas_dificeis}")
    print("\nNorma                    positivas  PRs  negativos dificeis")
    for n in NORMAS:
        print(f"  {n.id:<22} {stats.positivas[n.id]:>5} {len(stats.prs_da_norma[n.id]):>5} {stats.negativos[n.id]:>8}")
    return 1 if errors else 0


def check_eq(errors: list[str], label: str, actual: int, expected: int) -> None:
    if actual != expected:
        fail(errors, f"{label}: esperado {expected}, obtido {actual}.")


def print_report(errors: list[str]) -> None:
    if errors:
        print(f"FALHAS ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
    else:
        print("Todas as verificacoes de schema passaram.")


if __name__ == "__main__":
    sys.exit(main())
