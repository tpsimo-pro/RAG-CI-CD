"""Testes da conformidade do dataset com o corpus (D-008)."""

from __future__ import annotations

import textwrap

from evaluation.dataset.conformity import ast_findings, conformity_errors

LIMPO = textwrap.dedent('''\
    """Calculo de descontos de pedidos."""

    import logging

    logger = logging.getLogger(__name__)
    MAX_RATE = 0.5


    def calculate_discount(price: float, rate: float) -> float:
        """Calcula o desconto aplicado a um preco.

        Args:
            price: Preco original.
            rate: Taxa de desconto entre 0 e 1.

        Returns:
            Valor do desconto.

        Raises:
            ValueError: Se a taxa passar do limite.
        """
        if rate > MAX_RATE:
            raise ValueError("Taxa acima do limite")
        return price * rate


    def is_free(price: float) -> bool:
        """Indica se o preco e zero.

        Args:
            price: Preco a verificar.

        Returns:
            True se o preco for zero.
        """
        return price == 0
''').splitlines()


def _erros(lines, subs=None):
    return conformity_errors(lines, subs or [None] * len(lines))


def _tags(src: str) -> set[str]:
    return {tag for _, tag in ast_findings(textwrap.dedent(src))}


def test_modulo_limpo_passa():
    assert _erros(LIMPO) == []


def test_funcao_sem_docstring_reprova():
    inicio = LIMPO.index("def is_free(price: float) -> bool:")
    lines = LIMPO[: inicio + 1] + ["    return price == 0"]
    assert any("D103" in e for e in _erros(lines))


def test_e712_so_vale_na_positiva_booleana():
    lines = LIMPO[:-1] + ["    return price == True"]
    assert _erros(lines)
    subs = [None] * (len(lines) - 1) + ["booleano"]
    assert _erros(lines, subs) == []


def test_positiva_com_outra_violacao_reprova():
    lines = LIMPO.copy()
    idx = lines.index("def is_free(price: float) -> bool:")
    lines[idx] = "def isFree(price: float):"
    subs = [None] * len(lines)
    subs[idx] = "nome_funcao"
    assert any("ANN201" in e for e in _erros(lines, subs))


def test_achado_fora_do_intervalo_de_linhas_nao_quebra():
    lines = LIMPO + ["", ""]
    assert isinstance(_erros(lines), list)


def test_prefixo_booleano_nos_dois_sentidos():
    assert "prefixo-booleano" in _tags(
        "def check_stock(n: int) -> bool:\n    return n > 0\n"
    )
    assert "prefixo-booleano" in _tags(
        "def is_ready(n: int) -> int:\n    return n\n"
    )
    assert "prefixo-booleano" not in _tags(
        "def has_items(n: int) -> bool:\n    return n > 0\n"
    )


def test_nomes_genericos_e_de_uma_letra():
    assert "nome-generico" in _tags("def f_(n: int) -> None:\n    result = n\n")
    assert "uma-letra" in _tags("def f_(n: int) -> None:\n    x = n\n")
    assert "uma-letra" not in _tags(
        "def f_(count: int) -> None:\n    for i in range(count):\n        pass\n"
    )
    assert "nome-generico" in _tags(
        "try:\n    run()\nexcept Exception as err:\n    raise AppError() from err\n"
    )


def test_nome_de_modulo():
    assert "nome-de-modulo" in _tags("total = 1\n")
    assert "nome-de-modulo" not in _tags("MAX_ROWS = 1\nlogger = make()\n")


def test_parametros():
    assert "muitos-parametros" in _tags(
        "def g(a1: int, a2: int, a3: int, a4: int, a5: int) -> None:\n    pass\n"
    )
    assert "muitos-parametros" not in _tags(
        "def g(self, a1: int, a2: int, a3: int, a4: int) -> None:\n    pass\n"
    )
    assert "parametro-booleano" in _tags("def g(strict: bool) -> None:\n    pass\n")
    assert "parametro-booleano" in _tags("def g(strict=False) -> None:\n    pass\n")


def test_secoes_da_docstring():
    sem_args = 'def g(a1: int) -> None:\n    """Faz algo."""\n'
    assert "docstring-sem-args" in _tags(sem_args)
    sem_returns = 'def g() -> int:\n    """Faz algo."""\n    return 1\n'
    assert "docstring-sem-returns" in _tags(sem_returns)
    sem_raises = 'def g() -> None:\n    """Faz algo."""\n    raise ValueError()\n'
    assert "docstring-sem-raises" in _tags(sem_raises)


def test_segredo_em_literal():
    assert "segredo" in _tags('DB_URL = "postgresql://u:p@host/db"\n')


def test_nome_proibido_maiusculo_em_funcao_vale_so_na_positiva():
    lines = LIMPO[:-1] + ["    O = price", "    return price == 0"]
    assert any("N806" in e for e in _erros(lines))
    subs = [None] * len(lines)
    subs[-2] = "nome_proibido"
    assert _erros(lines, subs) == []


def test_uso_de_nome_proibido_fora_da_atribuicao_reprova():
    assert "uso-nome-proibido" in _tags(
        "def f_(count: int) -> int:\n    l = count\n    return l\n"
    )
    assert "uso-nome-proibido" not in _tags(
        "def f_(count: int) -> int:\n    l = count\n    return count\n"
    )


def test_positiva_nome_funcao_com_retorno_bool_viola_tambem_a_2_3():
    lines = LIMPO.copy()
    idx = lines.index("def is_free(price: float) -> bool:")
    lines[idx] = "def isFree(price: float) -> bool:"
    subs = [None] * len(lines)
    subs[idx] = "nome_funcao"
    assert any("prefixo-booleano" in e for e in _erros(lines, subs))


def test_init_sem_docstring_reprova():
    lines = LIMPO + [
        "",
        "",
        "class Wallet:",
        '    """Carteira do cliente."""',
        "",
        "    def __init__(self, owner: str) -> None:",
        "        self.owner = owner",
    ]
    assert any("D107" in e for e in _erros(lines))
