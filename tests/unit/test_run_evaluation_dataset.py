"""Carregamento do dataset v2 (PRs de varios arquivos) em run_evaluation."""

from __future__ import annotations

import json

import pytest

from evaluation.run_evaluation import (
    _build_file_diff,
    _build_gold_lines,
    _load_dataset,
)

ARQUIVO_NOVO = {
    "filename": "app/a.py",
    "status": "added",
    "patch": "@@ -0,0 +1,2 @@\n+x=1\n+y = 2",
    "added_lines": [
        {"line": "x=1", "viola": True, "regra": "pep8-espacos",
         "sub_regra": "espaco_operador", "hard_negative": False},
        {"line": "y = 2", "viola": False, "regra": None,
         "sub_regra": None, "hard_negative": False},
    ],
}
ARQUIVO_MOD = {
    "filename": "app/b.py",
    "status": "modified",
    "patch": "@@ -1,3 +1,3 @@\n a\n-old\n+new\n c",
    "source_after": "a\nnew\nc",
    "added_lines": [
        {"line": "new", "viola": False, "regra": None,
         "sub_regra": None, "hard_negative": False},
    ],
}


def _escrever(tmp_path, dataset):
    path = tmp_path / "ds.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")
    return path


def test_carrega_pr_com_varios_arquivos(tmp_path):
    ds = [{"pr_id": "PR-1", "description": "d", "files": [ARQUIVO_NOVO, ARQUIVO_MOD]}]
    assert _load_dataset(_escrever(tmp_path, ds)) == ds


@pytest.mark.parametrize(
    "mutar",
    [
        lambda pr: pr.pop("files"),
        lambda pr: pr.update(files=[]),
        lambda pr: pr["files"][0].pop("status"),
        lambda pr: pr["files"][0]["added_lines"][0].pop("viola"),
    ],
)
def test_dataset_malformado_falha_alto(tmp_path, mutar):
    pr = json.loads(json.dumps({"pr_id": "PR-1", "files": [ARQUIVO_NOVO]}))
    mutar(pr)
    with pytest.raises(ValueError):
        _load_dataset(_escrever(tmp_path, [pr]))


def test_gabarito_por_arquivo_leva_o_pr_id():
    gold = _build_gold_lines("PR-1", ARQUIVO_NOVO)
    assert [(g.pr_id, g.line, g.viola, g.sub_regra) for g in gold] == [
        ("PR-1", "x=1", True, "espaco_operador"),
        ("PR-1", "y = 2", False, None),
    ]


def test_file_diff_usa_o_status_e_conta_remocoes_do_patch():
    novo = _build_file_diff(ARQUIVO_NOVO)
    mod = _build_file_diff(ARQUIVO_MOD)
    assert (novo.status, novo.deletions, novo.added_lines) == ("added", 0, ["x=1", "y = 2"])
    assert (mod.status, mod.deletions, mod.additions) == ("modified", 1, 1)
    assert mod.filename == "app/b.py"


# ── linhas ambiguas ──────────────────────────────────────────────────────────

from evaluation.metrics import LineResult  # noqa: E402
from evaluation.run_evaluation import _resumo_ambiguas, _separar_ambiguas  # noqa: E402


def _lr(line, signaled, cell):
    return LineResult(
        pr_id="PR-1", line=line, expected_viola=False, regra="pep8-nomes",
        sub_regra=None, hard_negative=False, signaled=signaled, cell=cell,
        cites_correct_norm=None,
    )


def test_separa_as_linhas_ambiguas_da_matriz():
    arquivo = {
        "added_lines": [
            {"line": "a = 1", "viola": False},
            {"line": "retry_limit = 3", "viola": False, "ambiguo": True},
            {"line": "b = 2", "viola": False, "ambiguo": False},
        ]
    }
    resultados = [_lr("a = 1", False, "TN"), _lr("retry_limit = 3", True, "FP"), _lr("b = 2", False, "TN")]

    validas, ambiguas = _separar_ambiguas(resultados, arquivo)

    assert [r.line for r in validas] == ["a = 1", "b = 2"]
    assert ambiguas == [{"line": "retry_limit = 3", "regra": "pep8-nomes", "signaled": True}]


def test_resumo_conta_total_e_sinalizadas():
    detalhes = [
        {"pr_id": "PR-1", "ambiguous_lines": [{"line": "x", "signaled": True}, {"line": "y", "signaled": False}]},
        {"pr_id": "PR-2", "ambiguous_lines": []},
        {"pr_id": "PR-3"},
    ]
    resumo = _resumo_ambiguas(detalhes)
    assert (resumo["total"], resumo["signaled"]) == (2, 1)
    assert resumo["lines"][0]["pr_id"] == "PR-1"
