"""Testes da conformidade do dataset com a PEP 8 (D-008, D-009)."""

from __future__ import annotations

import textwrap

from evaluation.dataset.conformity import ast_findings, conformity_errors

LIMPO = textwrap.dedent('''\
    """Calculo de descontos de pedidos."""

    import logging

    logger = logging.getLogger(__name__)
    MAX_RATE = 0.5


    def calculate_discount(price, rate):
        if rate > MAX_RATE:
            raise ValueError("Taxa acima do limite")
        return price * rate


    def is_free(price):
        return price == 0
''').splitlines()


def _erros(lines, subs=None):
    return conformity_errors(lines, subs or [None] * len(lines))


def _tags(src: str) -> set[str]:
    return {tag for _, tag in ast_findings(textwrap.dedent(src))}


def test_modulo_limpo_passa():
    assert _erros(LIMPO) == []


def test_linha_acima_de_79_colunas_reprova():
    lines = LIMPO[:-1] + ["    return price == 0  # " + "x" * 60]
    assert any("E501" in e for e in _erros(lines))


def test_comentario_acima_de_72_colunas_reprova():
    lines = LIMPO[:-1] + ["    # " + "palavra " * 9, "    return price == 0"]
    assert any("W505" in e for e in _erros(lines))


def test_espaco_ausente_apos_dois_pontos_reprova():
    lines = LIMPO.copy()
    lines[LIMPO.index("def is_free(price):")] = "def is_free(price:int):"
    assert any("E231" in e for e in _erros(lines))


def test_imports_fora_de_ordem_reprovam():
    lines = ["import sys", "import logging", ""] + LIMPO[3:]
    assert any("I001" in e for e in _erros(lines))


def test_e712_so_vale_na_positiva_booleana():
    lines = LIMPO[:-1] + ["    return price == True"]
    assert _erros(lines)
    subs = [None] * (len(lines) - 1) + ["booleano"]
    assert _erros(lines, subs) == []


def test_positiva_com_outra_violacao_reprova():
    lines = LIMPO.copy()
    idx = lines.index("def is_free(price):")
    lines[idx] = "def isFree(price:int):"
    subs = [None] * len(lines)
    subs[idx] = "nome_funcao"
    erros = _erros(lines, subs)
    assert any("E231" in e for e in erros)
    assert not any("N802" in e for e in erros)


def test_achado_fora_do_intervalo_de_linhas_nao_quebra():
    lines = LIMPO + ["", ""]
    assert isinstance(_erros(lines), list)


def test_o_que_a_pep8_nao_manda_nao_reprova():
    # Docstring, anotacoes, prefixo booleano, quantidade de parametros,
    # nomes genericos e de uma letra eram exigencias dos guias antigos.
    codigo = textwrap.dedent('''\
        def check_stock(a1, a2, a3, a4, a5, strict=False):
            result = a1
            x = a2
            return result and x and strict


        total = 1
        DB_URL = "postgresql://u:p@host/db"
    ''').splitlines()
    assert _erros(codigo) == []


def test_nome_proibido_maiusculo_em_funcao_vale_so_na_positiva():
    lines = LIMPO[:-1] + ["    O = price", "    return price == 0"]
    assert any("N806" in e for e in _erros(lines))
    subs = [None] * len(lines)
    subs[-2] = "nome_proibido"
    assert _erros(lines, subs) == []


def test_uso_de_nome_proibido_fora_da_atribuicao_reprova():
    assert "uso-nome-proibido" in _tags(
        "def f_(count):\n    l = count\n    return l\n"
    )
    assert "uso-nome-proibido" not in _tags(
        "def f_(count):\n    l = count\n    return count\n"
    )


EXCETO = textwrap.dedent('''\
    import logging

    logger = logging.getLogger(__name__)


    def load(path):
        try:
            return open(path)
        except:
            {corpo}
''')


def _exceto(corpo):
    return EXCETO.format(corpo=corpo).splitlines()


def test_except_nu_com_logger_exception_e_tolerado_pela_pep8():
    assert _erros(_exceto('logger.exception("falha")')) == []


def test_except_nu_com_raise_e_tolerado_pela_pep8():
    assert _erros(_exceto("raise")) == []


def test_except_nu_silencioso_reprova_fora_da_positiva():
    lines = _exceto("pass")
    assert any("E722" in e for e in _erros(lines))


def test_except_nu_silencioso_vale_na_positiva_except_nu():
    lines = _exceto("pass")
    subs = [None] * len(lines)
    subs[lines.index("    except:")] = "except_nu"
    assert _erros(lines, subs) == []


def test_achado_em_linha_de_contexto_e_ignorado_com_alvo():
    lines = ["x=1", "", "", "y = 2", "z=3"]
    subs = [None] * len(lines)
    assert any("E225" in e for e in _erros(lines))
    assert conformity_errors(lines, subs, alvo={3}) == []
    erros = conformity_errors(lines, subs, alvo={3, 4})
    assert len(erros) == 1 and "linha 4" in erros[0]


# ── docstring em definicoes publicas (PEP 8, Documentation Strings) ──────────

from evaluation.dataset.conformity import docstring_findings  # noqa: E402


def _linhas_sem_doc(src):
    return [i for i, _ in docstring_findings(textwrap.dedent(src))]


def test_modulo_sem_docstring_e_acusado_na_linha_zero():
    assert _linhas_sem_doc("x = 1\n") == [0]


def test_funcao_e_classe_publicas_sem_docstring_sao_acusadas():
    src = '''\
        """Modulo."""


        class Cart:
            def total(self):
                return 0


        def build():
            return Cart()
    '''
    assert _linhas_sem_doc(src) == [3, 4, 8]


def test_init_e_publico_e_exige_docstring():
    src = '''\
        """Modulo."""


        class Cart:
            """Carrinho."""

            def __init__(self):
                self.items = []
    '''
    assert _linhas_sem_doc(src) == [6]


def test_nomes_privados_e_funcoes_aninhadas_ficam_de_fora():
    src = '''\
        """Modulo."""


        def _interna():
            return 1


        class _Auxiliar:
            def metodo(self):
                return 2


        def publica():
            """Faz algo."""

            def aninhada():
                return 3

            return aninhada
    '''
    assert _linhas_sem_doc(src) == []


def test_conformity_errors_so_cobra_docstring_quando_pedido():
    lines = ['"""Modulo."""', "", "", "def build():", "    return 1"]
    subs = [None] * len(lines)
    assert conformity_errors(lines, subs) == []
    erros = conformity_errors(lines, subs, docstrings=True)
    assert len(erros) == 1 and "docstring_publico" in erros[0]


def test_docstring_em_linha_de_contexto_e_ignorada_com_alvo():
    lines = ['"""Modulo."""', "", "", "def build():", "    return 1"]
    subs = [None] * len(lines)
    assert conformity_errors(lines, subs, alvo={4}, docstrings=True) == []
