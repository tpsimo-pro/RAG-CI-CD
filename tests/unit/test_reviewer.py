"""Testes do RAGReviewer com todas as dependências simuladas."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rag_reviewer.diff_parser import FileDiff, PullRequestDiff
from rag_reviewer.llm_client import Violation
from rag_reviewer.reviewer import RAGReviewer


def fd(name="a.py") -> FileDiff:
    return FileDiff(
        filename=name,
        patch="@@ -0,0 +1 @@\n+x = 1",
        status="added",
        added_lines=["x = 1"],
    )


def ctx(name="a.py"):
    c = MagicMock()
    c.file_diff = fd(name)
    return c


def viol(severity="HIGH") -> Violation:
    return Violation("x = 1", "desc", "PEP 8", severity, "fix")


def make(files=None, contextos=None, llm_side_effect=None, violacoes=None):
    collector = MagicMock()
    collector.collect.return_value = PullRequestDiff(
        pr_number=1,
        repo="o/r",
        files=files if files is not None else [fd()],
        total_additions=1,
        total_deletions=0,
    )
    retriever = MagicMock()
    retriever.retrieve_for_diff.return_value = (
        contextos if contextos is not None else [ctx()]
    )
    llm = MagicMock()
    llm.model = "modelo-x"
    if llm_side_effect is not None:
        llm.review.side_effect = llm_side_effect
    else:
        llm.review.return_value = violacoes if violacoes is not None else [viol()]
    publisher = MagicMock(spec=["publish", "post_summary"])
    reviewer = RAGReviewer(
        collector=collector, retriever=retriever, llm=llm, publisher=publisher
    )
    return reviewer, publisher, llm


def test_publica_as_violacoes_com_o_modelo():
    rev, pub, _ = make()
    resultado = rev.run()
    assert len(resultado) == 1
    kwargs = pub.publish.call_args.kwargs
    assert kwargs["model"] == "modelo-x"
    assert kwargs["unreviewed"] == []


def test_severidade_alta_nao_bloqueia_o_pr():
    # O publisher simulado só aceita publish e post_summary: qualquer chamada
    # a request_changes levantaria AttributeError.
    rev, pub, _ = make(violacoes=[viol("HIGH")])
    rev.run()
    pub.publish.assert_called_once()


def test_pr_sem_arquivos_publica_aviso_curto():
    rev, pub, llm = make(files=[])
    assert rev.run() == []
    pub.post_summary.assert_called_once()
    llm.review.assert_not_called()


def test_sem_contexto_recuperado_publica_aviso_curto():
    rev, pub, llm = make(contextos=[])
    assert rev.run() == []
    pub.post_summary.assert_called_once()
    llm.review.assert_not_called()


def test_falha_em_um_arquivo_nao_derruba_os_outros():
    def efeito(context):
        if context.file_diff.filename == "a.py":
            raise ValueError("JSON invalido")
        return [viol()]

    rev, pub, _ = make(contextos=[ctx("a.py"), ctx("b.py")], llm_side_effect=efeito)
    resultado = rev.run()
    assert [f.filename for f, _ in resultado] == ["b.py"]
    assert pub.publish.call_args.kwargs["unreviewed"] == ["a.py"]


def test_falha_em_todos_os_arquivos_falha_o_job_depois_de_publicar():
    rev, pub, _ = make(contextos=[ctx("a.py")], llm_side_effect=ValueError("x"))
    with pytest.raises(RuntimeError):
        rev.run()
    pub.publish.assert_called_once()


def test_rate_limit_tem_uma_nova_tentativa(monkeypatch):
    class RateLimitError(Exception):
        pass

    monkeypatch.setattr("rag_reviewer.reviewer.time.sleep", lambda s: None)
    respostas = [RateLimitError("429"), [viol()]]

    def efeito(context):
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    rev, pub, llm = make(llm_side_effect=efeito)
    assert len(rev.run()) == 1
    assert llm.review.call_count == 2


def test_rate_limit_persistente_marca_o_arquivo_como_nao_revisado(monkeypatch):
    class RateLimitError(Exception):
        pass

    monkeypatch.setattr("rag_reviewer.reviewer.time.sleep", lambda s: None)
    rev, pub, llm = make(
        contextos=[ctx("a.py"), ctx("b.py")],
        llm_side_effect=lambda c: (_ for _ in ()).throw(RateLimitError("429"))
        if c.file_diff.filename == "a.py"
        else [viol()],
    )
    rev.run()
    assert llm.review.call_count == 3  # a.py duas vezes, b.py uma
    assert pub.publish.call_args.kwargs["unreviewed"] == ["a.py"]
