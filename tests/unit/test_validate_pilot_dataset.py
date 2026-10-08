"""Testes do validador do dataset (D-009, D-010)."""

from __future__ import annotations

import textwrap

import pytest

from evaluation.dataset.validate_pilot_dataset import (
    HARD_NEGATIVE_CATALOG_EXCECAO,
    SUB_REGRAS,
    block_duplicates,
    except_labels,
    matches_exc_catalog,
    validar_arquivo,
    Estatisticas,
)


def _labels(src: str) -> tuple[dict[int, str | None], list[str]]:
    return except_labels(textwrap.dedent(src).strip("\n"))


class TestExceptLabels:
    def test_except_nu_com_pass_viola(self):
        labels, errors = _labels("""
            try:
                run()
            except:
                pass
        """)
        assert labels == {2: "except_nu"}
        assert errors == []

    def test_except_nu_com_continue_viola(self):
        labels, errors = _labels("""
            for item in items:
                try:
                    run(item)
                except:
                    continue
        """)
        assert labels == {3: "except_nu"}
        assert errors == []

    def test_except_nu_com_logger_exception_e_tolerado(self):
        labels, errors = _labels("""
            try:
                run()
            except:
                logger.exception("Falha")
        """)
        assert labels == {2: None}
        assert errors == []

    def test_except_nu_com_raise_e_tolerado(self):
        labels, errors = _labels("""
            try:
                run()
            except:
                raise
        """)
        assert labels == {2: None}
        assert errors == []

    def test_exception_com_pass_nao_viola(self):
        # A PEP 8 manda usar `except Exception:` para erros de programa.
        labels, errors = _labels("""
            try:
                run()
            except Exception:
                pass
        """)
        assert labels == {2: None}
        assert errors == []

    def test_especifica_com_continue_nao_viola(self):
        labels, errors = _labels("""
            for item in items:
                try:
                    run(item)
                except ValueError:
                    continue
        """)
        assert labels == {3: None}
        assert errors == []

    @pytest.mark.parametrize(
        "cabecalho",
        [
            "except json.JSONDecodeError:",
            "except BaseException:",
            "except (ValueError, KeyError):",
        ],
    )
    def test_qualquer_tipo_nunca_viola(self, cabecalho):
        labels, errors = _labels(f"""
            try:
                run()
            {cabecalho}
                pass
        """)
        assert labels == {2: None}
        assert errors == []

    def test_exception_com_logger_exception_nao_viola(self):
        labels, errors = _labels("""
            try:
                run()
            except Exception as exc:
                logger.exception("Falha: %s", exc)
        """)
        assert labels == {2: None}
        assert errors == []

    def test_especifica_com_raise_from_nao_viola(self):
        labels, errors = _labels("""
            try:
                run()
            except ValueError as exc:
                raise AppError("Dados invalidos") from exc
        """)
        assert labels == {2: None}
        assert errors == []

    @pytest.mark.parametrize("cabecalho", ["except:", "except Exception:"])
    @pytest.mark.parametrize(
        "corpo",
        ['logger.error("falha")', 'print("falha")', "return None", "fallback = 0"],
    )
    def test_corpo_fora_do_escopo_e_rejeitado(self, cabecalho, corpo):
        labels, errors = _labels(f"""
            def run_job():
                try:
                    run()
                {cabecalho}
                    {corpo}
        """)
        assert labels == {}
        assert len(errors) == 1

    def test_raise_condicional_e_rejeitado(self):
        labels, errors = _labels("""
            try:
                run()
            except Exception as exc:
                if strict:
                    raise AppError("falha") from exc
        """)
        assert labels == {}
        assert len(errors) == 1

    def test_try_aninhado_e_rejeitado(self):
        labels, errors = _labels("""
            try:
                run()
            except Exception:
                try:
                    cleanup()
                except OSError:
                    raise
        """)
        assert 2 not in labels
        assert errors

    def test_corpo_na_mesma_linha_e_rejeitado(self):
        labels, errors = _labels("""
            try:
                run()
            except: pass
        """)
        assert labels == {}
        assert len(errors) == 1

    def test_codigo_sem_except_nao_gera_rotulo(self):
        assert _labels("if flag:\n    run()") == ({}, [])


class TestBlockDuplicates:
    def test_except_repetido_no_pr_e_erro(self):
        lines = [
            "try:", "    run()", "except:", "    pass",
            "try:", "    stop()", "except:", "    raise",
        ]
        labels = {2: "except_nu", 6: None}
        errors = block_duplicates(lines, labels)
        assert len(errors) == 2  # cada ocorrencia do except repetido

    def test_corpo_violador_repetido_no_pr_e_erro(self):
        lines = [
            "try:", "    run()", "except:", "    pass",
            "class Empty:", "    pass",
        ]
        errors = block_duplicates(lines, {2: "except_nu"})
        assert len(errors) == 1

    def test_pr_sem_repeticao_passa(self):
        lines = [
            "try:", "    run()", "except KeyError:", "    pass",
            "except:", "    continue",
        ]
        labels = {2: None, 4: "except_nu"}
        assert block_duplicates(lines, labels) == []


def test_except_nu_pertence_a_familia_das_recomendacoes():
    assert "except_nu" in SUB_REGRAS["pep8-recomendacoes"]


class TestCatalogoExcecao:
    @pytest.mark.parametrize(
        ("nome", "linha", "proxima"),
        [
            ("except Exception + logger.exception",
             "    except Exception as exc:", '        logger.exception("x %s", exc)'),
            ("except Exception + raise ... from",
             "    except Exception as exc:", '        raise AppError("x") from exc'),
            ("except especifica + raise ... from",
             "    except KeyError as exc:", '        raise AppError("x") from exc'),
            ("except especifica + logger.exception",
             "    except OSError as exc:", '        logger.exception("x %s", exc)'),
            ("except Exception + pass (PEP 8 recomenda)",
             "    except Exception:", "        pass"),
            ("except especifica + pass/continue",
             "    except KeyError:", "        continue"),
            ("except nu + logger.exception (tolerado)",
             "    except:", '        logger.exception("x")'),
            ("except nu + raise (tolerado)", "    except:", "        raise"),
            ("comentario com except Exception: pass",
             "    # nunca usar except Exception: pass aqui", ""),
            ("string com except Exception: pass",
             'HINT = "evite except Exception: pass"', ""),
        ],
    )
    def test_cada_padrao_reconhece_seu_exemplo(self, nome, linha, proxima):
        assert matches_exc_catalog(HARD_NEGATIVE_CATALOG_EXCECAO[nome], linha, proxima)

    def test_exception_nao_conta_como_especifica(self):
        padrao = HARD_NEGATIVE_CATALOG_EXCECAO["except especifica + logger.exception"]
        assert not matches_exc_catalog(
            padrao, "    except Exception as exc:", '        logger.exception("x")'
        )

    def test_except_nu_violador_nao_conta_como_tolerado(self):
        padrao = HARD_NEGATIVE_CATALOG_EXCECAO["except nu + raise (tolerado)"]
        assert not matches_exc_catalog(padrao, "    except:", "        pass")


# ── validar_arquivo: o oraculo e o schema v2 ─────────────────────────────────


def _linha(texto, sub=None, regra=None, dificil=False):
    return {
        "line": texto,
        "viola": sub is not None,
        "regra": regra,
        "sub_regra": sub,
        "hard_negative": dificil,
    }


def _arquivo_novo(entradas, nome="app/mod.py"):
    patch = "@@ -0,0 +1,%d @@\n" % len(entradas) + "\n".join(
        "+" + e["line"] for e in entradas
    )
    return {"filename": nome, "status": "added", "patch": patch,
            "added_lines": entradas}


def _validar(arquivo):
    erros: list[str] = []
    positivas = validar_arquivo("PR-900", arquivo, erros, Estatisticas())
    return positivas, erros


def _corpo_limpo():
    return [_linha(t) for t in [
        '"""Modulo de exemplo."""', "", "", "def total(items):",
        "    value = 0", "    for item in items:", "        value += item",
        "    return value",
    ]]


class TestValidarArquivo:
    def test_arquivo_limpo_nao_tem_erro(self):
        positivas, erros = _validar(_arquivo_novo(_corpo_limpo()))
        assert erros == [] and positivas == set()

    def test_violacao_rotulada_passa(self):
        e = _corpo_limpo()
        e[4] = _linha("    value = 0 if value == None else 1", "nulo", "pep8-recomendacoes")
        e[4]["line"] = "    if value == None:"
        e[5:5] = [_linha("        pass")]
        positivas, erros = _validar(_arquivo_novo(e))
        assert positivas == {"nulo"}, erros
        assert [x for x in erros if "oraculo" in x] == []

    def test_violacao_sem_rotulo_e_erro_do_oraculo(self):
        e = _corpo_limpo()
        e[4] = _linha("    value=0")
        _, erros = _validar(_arquivo_novo(e))
        assert any("E225" in x and "oraculo" in x for x in erros)

    def test_rotulo_positivo_que_nao_dispara_e_erro(self):
        e = _corpo_limpo()
        e[4] = _linha("    value = 0", "nulo", "pep8-recomendacoes")
        _, erros = _validar(_arquivo_novo(e))
        assert any("nenhum oraculo a detecta" in x for x in erros)

    def test_regra_incoerente_com_a_norma_e_erro(self):
        e = _corpo_limpo()
        e[4] = _linha("    if value == None:", "nulo", "pep8-nomes")
        _, erros = _validar(_arquivo_novo(e))
        assert any("regra/sub_regra do catalogo" in x for x in erros)

    def test_patch_inconsistente_e_erro(self):
        arq = _arquivo_novo(_corpo_limpo())
        arq["patch"] = arq["patch"].replace("+    value = 0", "+    value = 1")
        _, erros = _validar(arq)
        assert any("patch inconsistente" in x for x in erros)

    def test_arquivo_pequeno_demais_e_erro(self):
        _, erros = _validar(_arquivo_novo([_linha("x = 1")]))
        assert any("fora de (8, 60)" in x for x in erros)


def _modificado(antes, depois, rotulos=None, nome="app/mod.py"):
    """Arquivo modificado com o patch gerado por difflib (contexto de 2 linhas)."""
    import difflib

    rotulos = rotulos or {}
    diff = list(difflib.unified_diff(antes, depois, lineterm="", n=2))
    patch = "\n".join(diff[2:])
    entradas = [
        rotulos.get(t[1:], _linha(t[1:]))
        for t in diff[2:]
        if t.startswith("+") and not t.startswith("@@")
    ]
    return {"filename": nome, "status": "modified", "patch": patch,
            "source_after": "\n".join(depois), "added_lines": entradas}


ANTES = [
    '"""Modulo."""', "", "", "def total(items):", "    return sum(items)",
    "", "", "def other(a):", "    return a  #nota",
]


class TestArquivoModificado:
    def _depois(self, novas):
        depois = list(ANTES)
        depois[4:5] = novas
        return depois

    NOVAS = [
        "    value = 0", "    for item in items:", "        value += item",
        "    if value == None:", "        return 0", "    return value",
        "    # fim", "    # fim2",
    ]

    def test_achado_em_contexto_pre_existente_e_ignorado(self):
        # O `#nota` sem espaco (E262) ja existia na linha de contexto.
        arq = _modificado(
            ANTES, self._depois(self.NOVAS),
            {"    if value == None:": _linha("    if value == None:", "nulo", "pep8-recomendacoes")},
        )
        positivas, erros = _validar(arq)
        assert positivas == {"nulo"}, erros

    def test_norma_de_contexto_em_arquivo_modificado_e_erro(self):
        arq = _modificado(
            ANTES, self._depois(self.NOVAS),
            {"    # fim": _linha("    # fim", "linhas_em_branco", "pep8-layout")},
        )
        _, erros = _validar(arq)
        assert any("so vale em arquivo novo" in x for x in erros)

    def test_modified_exige_source_after(self):
        arq = _modificado(ANTES, self._depois(self.NOVAS))
        del arq["source_after"]
        _, erros = _validar(arq)
        assert any("exige source_after" in x for x in erros)

    def test_patch_que_nao_bate_com_source_after_e_erro(self):
        arq = _modificado(ANTES, self._depois(self.NOVAS))
        arq["source_after"] = arq["source_after"].replace("value = 0", "value = 9")
        _, erros = _validar(arq)
        assert any("nao bate com source_after" in x for x in erros)
