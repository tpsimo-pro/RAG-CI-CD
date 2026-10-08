"""Leitura do unified diff do dataset (D-010)."""

from __future__ import annotations

import pytest

from evaluation.dataset.patch import PatchError, linhas_adicionadas, parse_patch

PATCH = "\n".join(
    [
        "@@ -1,4 +1,5 @@",
        " import os",
        "-OLD = 1",
        "+NEW = 1",
        "+OTHER = 2",
        " ",
        " def f():",
        "@@ -20,2 +21,3 @@",
        "     return 1",
        "+    # nota",
        " ",
    ]
)


def test_numera_as_linhas_da_versao_nova():
    tipos = [(t, n) for t, n, _ in parse_patch(PATCH)]
    assert tipos == [
        (" ", 1), ("-", None), ("+", 2), ("+", 3), (" ", 4), (" ", 5),
        (" ", 21), ("+", 22), (" ", 23),
    ]


def test_linhas_adicionadas_em_ordem_com_numero():
    assert linhas_adicionadas(PATCH) == [
        (2, "NEW = 1"), (3, "OTHER = 2"), (22, "    # nota"),
    ]


def test_arquivo_novo():
    patch = "@@ -0,0 +1,2 @@\n+a = 1\n+b = 2"
    assert linhas_adicionadas(patch) == [(1, "a = 1"), (2, "b = 2")]


def test_contador_errado_e_rejeitado():
    with pytest.raises(PatchError):
        parse_patch("@@ -1,2 +1,2 @@\n a\n+b")


def test_texto_fora_de_hunk_e_rejeitado():
    with pytest.raises(PatchError):
        parse_patch("a = 1")
