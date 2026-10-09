"""Testes do GitHubPublisher (HTTP simulado, sem rede)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from rag_reviewer.diff_parser import FileDiff, PullRequestDiff
from rag_reviewer.github_publisher import (
    GitHubPublisher,
    _build_summary_body,
    _count_by_severity,
    _find_diff_position,
    _format_inline_comment,
)
from rag_reviewer.llm_client import Violation

PATCH = "@@ -0,0 +1,4 @@\n+import os\n+x = 1\n+y = 2\n+x = 1"


def make_violation(line="x = 1", severity="HIGH", ambiguous=False) -> Violation:
    return Violation(
        line_content=line,
        violation_description="Descrição",
        norm_reference="PEP 8 - Naming Conventions",
        severity=severity,
        suggestion="Corrija",
        ambiguous=ambiguous,
    )


def make_file(patch=PATCH, name="app/a.py") -> FileDiff:
    return FileDiff(filename=name, patch=patch, status="added", added_lines=[])


def make_pr(files=None) -> PullRequestDiff:
    return PullRequestDiff(
        pr_number=7,
        repo="o/r",
        files=files or [make_file()],
        total_additions=4,
        total_deletions=0,
    )


def make_publisher() -> GitHubPublisher:
    return GitHubPublisher(token="t", repo="o/r", pr_number=7, head_sha="abc")


def resp(status=200, json=None, links=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json if json is not None else []
    r.links = links or {}
    r.raise_for_status.side_effect = (
        None if status < 400 else RuntimeError(f"HTTP {status}")
    )
    return r


class TestFindDiffPosition:
    def test_acha_linha_adicionada(self):
        # A linha logo abaixo do primeiro @@ e a posicao 1 (doc da API de reviews)
        assert _find_diff_position(PATCH, "import os") == 1

    def test_nao_acha_trecho_ausente(self):
        assert _find_diff_position(PATCH, "z = 9") is None

    def test_patch_ou_trecho_vazio(self):
        assert _find_diff_position("", "x") is None
        assert _find_diff_position(PATCH, "") is None
        assert _find_diff_position(PATCH, "   ") is None

    def test_nao_casa_linha_removida_nem_contexto(self):
        patch_removida = "@@ -1,2 +1,1 @@\n-velha = 1\n contexto = 2"
        assert _find_diff_position(patch_removida, "velha = 1") is None
        assert _find_diff_position(patch_removida, "contexto = 2") is None

    def test_primeiro_cabecalho_nao_conta_posicao(self):
        assert _find_diff_position("@@ -0,0 +1 @@\n+a = 1", "a = 1") == 1

    def test_cabecalhos_seguintes_e_linhas_removidas_contam(self):
        patch = "@@ -1,2 +1,2 @@\n-velha = 1\n+nova = 1\n@@ -9 +9 @@\n+outra = 2"
        assert _find_diff_position(patch, "nova = 1") == 2
        assert _find_diff_position(patch, "outra = 2") == 4

    def test_ultima_linha_do_patch_tem_posicao_valida(self):
        patch = "@@ -0,0 +1,2 @@\n+a = 1\n+b = 2"
        assert _find_diff_position(patch, "b = 2") == 2  # nunca len(linhas) + 1

    def test_linhas_repetidas_vao_a_posicoes_diferentes(self):
        usadas: set[int] = set()
        primeira = _find_diff_position(PATCH, "x = 1", usadas)
        segunda = _find_diff_position(PATCH, "x = 1", usadas)
        assert (primeira, segunda) == (2, 4)

    def test_terceira_violacao_na_mesma_linha_reusa_a_exata(self):
        usadas: set[int] = set()
        _find_diff_position(PATCH, "x = 1", usadas)
        _find_diff_position(PATCH, "x = 1", usadas)
        assert _find_diff_position(PATCH, "x = 1", usadas) == 2

    def test_segunda_violacao_na_mesma_linha_nao_vai_para_substring(self):
        patch = "@@ -0,0 +1,2 @@\n+x = 1\n+    x = 1  # nota"
        usadas: set[int] = set()
        assert _find_diff_position(patch, "x = 1", usadas) == 1
        assert _find_diff_position(patch, "x = 1", usadas) == 1

    def test_igualdade_exata_vence_substring(self):
        patch = "@@ -0,0 +1,2 @@\n+total_x = 1\n+x = 1"
        assert _find_diff_position(patch, "x = 1") == 2

    def test_substring_quando_nao_ha_igualdade(self):
        assert _find_diff_position(PATCH, "import") == 1


class TestFormat:
    def test_comentario_normal(self):
        texto = _format_inline_comment(make_violation(severity="MEDIUM"))
        assert texto.startswith("**[MEDIUM]** Descrição")
        assert "**Norma:** `PEP 8 - Naming Conventions`" in texto
        assert "**Como corrigir:** Corrija" in texto

    def test_comentario_ambiguo_nao_afirma_violacao(self):
        texto = _format_inline_comment(make_violation(severity="LOW", ambiguous=True))
        assert texto.startswith("**[LOW] Possível ambiguidade.**")
        assert "Descrição" in texto

    def test_sem_emojis(self):
        texto = _format_inline_comment(make_violation())
        assert all(ord(c) < 0x2000 for c in texto)

    def test_contagem_por_severidade(self):
        fd = make_file()
        violacoes = [
            (fd, make_violation(severity="HIGH")),
            (fd, make_violation(severity="LOW")),
            (fd, make_violation(severity="HIGH")),
        ]
        assert _count_by_severity(violacoes) == {"HIGH": 2, "LOW": 1}

    def test_sumario_com_violacoes(self):
        corpo = _build_summary_body(3, {"LOW": 1, "HIGH": 2}, model="m")
        assert "3 violação(ões) detectada(s)" in corpo
        assert corpo.index("HIGH") < corpo.index("LOW")
        assert "CRITICAL" not in corpo
        assert "`m`" in corpo

    def test_sumario_lista_notas_e_nao_revisados(self):
        corpo = _build_summary_body(
            1, {"HIGH": 1}, notas=["- `a.py`: algo"], unreviewed=["b.py"]
        )
        assert "- `a.py`: algo" in corpo
        assert "- `b.py`" in corpo

    def test_sumario_sem_violacoes_novas(self):
        assert "nenhuma violação nova" in _build_summary_body(0, {})


class TestPublish:
    def test_sem_violacoes_publica_aprovacao(self):
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [])
            req.post.return_value = resp(201)
            make_publisher().publish([], make_pr())
        url = req.post.call_args.args[0]
        assert url.endswith("/issues/7/comments")

    def test_comentario_inline_vai_com_a_posicao(self):
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [])
            req.post.return_value = resp(200)
            make_publisher().publish(
                [(make_file(), make_violation("import os"))], make_pr()
            )
        payload = req.post.call_args.kwargs["json"]
        assert payload["event"] == "COMMENT"
        assert payload["commit_id"] == "abc"
        assert payload["comments"][0]["position"] == 1
        assert payload["comments"][0]["path"] == "app/a.py"

    def test_linha_inexistente_no_diff_vai_ao_sumario(self):
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [])
            req.post.return_value = resp(200)
            make_publisher().publish(
                [(make_file(), make_violation("nao existe"))], make_pr()
            )
        payload = req.post.call_args.kwargs["json"]
        assert payload["comments"] == []
        assert "sem linha localizável" in payload["body"]
        assert "nao existe" in payload["body"]

    def test_violacoes_de_mesmo_texto_vao_a_linhas_diferentes(self):
        fd = make_file()
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [])
            req.post.return_value = resp(200)
            make_publisher().publish(
                [(fd, make_violation("x = 1")), (fd, make_violation("x = 1"))],
                make_pr(),
            )
        comentarios = req.post.call_args.kwargs["json"]["comments"]
        assert [c["position"] for c in comentarios] == [2, 4]

    def test_nao_repete_comentario_ja_publicado(self):
        fd = make_file()
        corpo = _format_inline_comment(make_violation("import os"))
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [{"path": "app/a.py", "body": corpo}])
            make_publisher().publish([(fd, make_violation("import os"))], make_pr())
        req.post.assert_not_called()

    def test_422_tenta_de_novo_so_com_o_sumario(self):
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [])
            req.post.side_effect = [resp(422), resp(200)]
            make_publisher().publish(
                [(make_file(), make_violation("import os"))], make_pr()
            )
        assert req.post.call_count == 2
        segunda = req.post.call_args.kwargs["json"]
        assert segunda["comments"] == []
        assert "app/a.py" in segunda["body"]

    def test_falha_ao_ler_comentarios_existentes_nao_impede_publicar(self):
        import requests as real

        with patch("rag_reviewer.github_publisher.requests") as req:
            req.RequestException = real.RequestException
            req.get.side_effect = real.RequestException("falhou")
            req.post.return_value = resp(200)
            make_publisher().publish(
                [(make_file(), make_violation("import os"))], make_pr()
            )
        assert req.post.call_count == 1

    def test_aprovacao_nao_e_repetida_a_cada_push(self):
        aprovacao = "Nenhuma violação da PEP 8 detectada nas linhas adicionadas."
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [{"body": aprovacao}])
            make_publisher().publish([], make_pr())
        req.post.assert_not_called()

    def test_aviso_novo_e_publicado_quando_ainda_nao_existe(self):
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [{"body": "outro comentario"}])
            req.post.return_value = resp(201)
            make_publisher().post_summary("aviso")
        req.post.assert_called_once()

    def test_so_arquivos_nao_revisados_publica_sumario(self):
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [])
            req.post.return_value = resp(200)
            make_publisher().publish([], make_pr(), unreviewed=["b.py"])
        assert "- `b.py`" in req.post.call_args.kwargs["json"]["body"]

    def test_publisher_nao_tem_request_changes(self):
        assert not hasattr(GitHubPublisher, "request_changes")
