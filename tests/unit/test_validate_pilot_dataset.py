"""Testes da checagem por AST da regra coding-4.1 (emenda 2 de D-002)."""

from __future__ import annotations

import textwrap

import pytest

from evaluation.dataset.validate_pilot_dataset import (
    HARD_NEGATIVE_CATALOG_EXCECAO,
    SUB_REGRAS,
    block_duplicates,
    except_labels,
    matches_exc_catalog,
)


def _labels(src: str) -> tuple[dict[int, str | None], list[str]]:
    return except_labels(textwrap.dedent(src).strip("\n"))


class TestExceptLabels:
    def test_exception_com_pass_e_captura_generica(self):
        labels, errors = _labels("""
            try:
                run()
            except Exception:
                pass
        """)
        assert labels == {2: "captura_generica"}
        assert errors == []

    def test_especifica_com_continue_e_captura_silenciosa(self):
        labels, errors = _labels("""
            for item in items:
                try:
                    run(item)
                except ValueError:
                    continue
        """)
        assert labels == {3: "captura_silenciosa"}
        assert errors == []

    def test_tipo_com_atributo_e_especifico(self):
        labels, _ = _labels("""
            try:
                run()
            except json.JSONDecodeError:
                pass
        """)
        assert labels == {2: "captura_silenciosa"}

    def test_exception_com_logger_exception_nao_viola(self):
        labels, errors = _labels("""
            try:
                run()
            except Exception as exc:
                logger.exception("Falha: %s", exc)
        """)
        assert labels == {2: None}
        assert errors == []

    def test_exception_com_raise_puro_nao_viola(self):
        labels, errors = _labels("""
            try:
                run()
            except Exception:
                raise
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

    def test_especifica_com_raise_sem_from_fica_fora_do_escopo(self):
        labels, errors = _labels("""
            try:
                run()
            except ValueError:
                raise
        """)
        assert labels == {}
        assert len(errors) == 1

    @pytest.mark.parametrize(
        "corpo",
        ['logger.error("falha")', 'print("falha")', "return None", "fallback = 0"],
    )
    def test_corpo_fora_do_escopo_e_rejeitado(self, corpo):
        labels, errors = _labels(f"""
            def run_job():
                try:
                    run()
                except Exception:
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

    @pytest.mark.parametrize(
        "cabecalho",
        ["except:", "except BaseException:", "except (ValueError, KeyError):"],
    )
    def test_tipos_fora_do_escopo_sao_rejeitados(self, cabecalho):
        labels, errors = _labels(f"""
            try:
                run()
            {cabecalho}
                pass
        """)
        assert labels == {}
        assert len(errors) == 1

    def test_corpo_na_mesma_linha_e_rejeitado(self):
        labels, errors = _labels("""
            try:
                run()
            except Exception: pass
        """)
        assert labels == {}
        assert len(errors) == 1

    def test_codigo_sem_except_nao_gera_rotulo(self):
        assert _labels("if flag:\n    run()") == ({}, [])


class TestBlockDuplicates:
    def test_except_repetido_no_pr_e_erro(self):
        lines = [
            "try:", "    run()", "except ValueError:", "    pass",
            "try:", "    stop()", "except ValueError:", "    raise AppError() from None",
        ]
        labels = {2: "captura_silenciosa", 6: None}
        errors = block_duplicates(lines, labels)
        assert len(errors) == 2  # cada ocorrencia do except repetido

    def test_corpo_violador_repetido_no_pr_e_erro(self):
        lines = [
            "try:", "    run()", "except ValueError:", "    pass",
            "class Empty:", "    pass",
        ]
        errors = block_duplicates(lines, {2: "captura_silenciosa"})
        assert len(errors) == 1

    def test_pr_sem_repeticao_passa(self):
        lines = [
            "try:", "    run()", "except ValueError:", "    pass",
            "except KeyError:", "    continue",
        ]
        labels = {2: "captura_silenciosa", 4: "captura_silenciosa"}
        assert block_duplicates(lines, labels) == []


def test_sub_regras_da_regra_nova():
    assert SUB_REGRAS["coding-4.1"] == {"captura_generica", "captura_silenciosa"}


class TestCatalogoExcecao:
    @pytest.mark.parametrize(
        ("nome", "linha", "proxima"),
        [
            ("except Exception + logger.exception",
             "    except Exception as exc:", '        logger.exception("x %s", exc)'),
            ("except Exception + raise", "    except Exception:", "        raise"),
            ("except especifica + raise ... from",
             "    except KeyError as exc:", '        raise AppError("x") from exc'),
            ("except especifica + logger.exception",
             "    except OSError as exc:", '        logger.exception("x %s", exc)'),
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
