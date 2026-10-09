"""Scripts dos PRs de teste do workflow (D-011)."""

from scripts.conferir_prs_demo import texto_da_linha
from scripts.montar_prs_demo import reconstruir_antes

DEPOIS = "a = 1\nb = 2\nc = 3\nd = 4\n"
PATCH = "@@ -1,3 +1,4 @@\n a = 1\n-x = 0\n+b = 2\n c = 3\n+d = 4"


def test_reconstruir_antes_desfaz_adicoes_e_restaura_remocoes():
    assert reconstruir_antes(DEPOIS, PATCH) == "a = 1\nx = 0\nc = 3\n"


def test_reconstruir_antes_com_dois_hunks():
    depois = "a\nb\nc\nd\ne\nf\n"
    patch = "@@ -1,2 +1,2 @@\n a\n-x\n+b\n@@ -5,2 +5,2 @@\n e\n-y\n+f"
    assert reconstruir_antes(depois, patch) == "a\nx\nc\nd\ne\ny\n"


def test_texto_da_linha():
    linhas = DEPOIS.splitlines()
    assert texto_da_linha(linhas, 2) == "b = 2"
    assert texto_da_linha(linhas, 4) == "d = 4"
    assert texto_da_linha(linhas, None) is None  # comentario desatualizado
    assert texto_da_linha(linhas, 99) is None
