"""
github_publisher.py — Publicação de comentários de revisão via GitHub REST API.

Responsabilidades:
  1. Encontrar a posição correta de cada violação no diff unificado.
  2. Criar uma review com comentários inline para cada violação identificável.
  3. Publicar um comentário geral de resumo com tabela de severidades.
  4. Emitir REQUEST_CHANGES quando há violações críticas.

Uso típico:
    publisher = GitHubPublisher()
    publisher.publish(all_violations, pr_diff)
    # Se houver CRITICAL: publisher.request_changes("mensagem") é chamado
    # pelo reviewer.py automaticamente.
"""

from __future__ import annotations

import requests
from rich.console import Console

from rag_reviewer.config import get_settings
from rag_reviewer.diff_parser import FileDiff, PullRequestDiff
from rag_reviewer.llm_client import Violation

console = Console()

# Tipo alias
ViolationList = list[tuple[FileDiff, Violation]]

_SEVERITY_EMOJI: dict[str, str] = {
    "CRITICAL": "⛔",
    "HIGH": "🔴",
    "MEDIUM": "🟡",
    "LOW": "🔵",
}

_GITHUB_API_BASE = "https://api.github.com"


class GitHubPublisher:
    """
    Publica comentários de revisão no PR via GitHub REST API.

    Estratégia:
    - Para cada violação com ``line_content`` localizável no patch → comentário inline.
    - Ao final → uma única review consolidada (evita spam de requests).
    - Violações cujo ``line_content`` não é localizável no diff → incluídas
      apenas no corpo do sumário da review.
    """

    def __init__(
        self,
        token: str | None = None,
        repo: str | None = None,
        pr_number: int | None = None,
        head_sha: str | None = None,
    ) -> None:
        """
        Inicializa o publisher.

        Os parâmetros são opcionais para facilitar testes unitários.
        Em produção, os valores vêm de ``get_settings()``.
        """
        settings = get_settings()
        self._token = token if token is not None else settings.github_token
        self._repo = repo if repo is not None else settings.repo_full_name
        self._pr_number = pr_number if pr_number is not None else settings.pr_number
        self._head_sha = head_sha if head_sha is not None else settings.pr_head_sha
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ── Interface pública ─────────────────────────────────────────────────

    def publish(self, violations: ViolationList, pr_diff: PullRequestDiff) -> None:
        """
        Publica os comentários de revisão no PR.

        Se não houver violações, publica uma mensagem de aprovação.
        Caso contrário, cria uma review consolidada com comentários inline
        para cada violação localizável e um sumário geral.

        Args:
            violations: Lista de (FileDiff, Violation) gerada pelo LLMClient.
            pr_diff: Diff completo do PR (usado para contexto no sumário).
        """
        if not violations:
            self.post_summary(
                "✅ Nenhuma violação detectada nas normas organizacionais."
            )
            return

        review_comments = self._build_review_comments(violations)
        severity_counts = _count_by_severity(violations)
        self._create_review(review_comments, severity_counts)

        console.log(
            f"[green]✅ GitHubPublisher:[/green] review publicada — "
            f"{len(violations)} violação(ões), "
            f"{len(review_comments)} comentário(s) inline."
        )

    def post_summary(self, message: str) -> None:
        """
        Publica um comentário geral (não inline) no PR.

        Usado para mensagem de aprovação ou avisos sem localização específica.
        """
        url = (
            f"{_GITHUB_API_BASE}/repos/{self._repo}"
            f"/issues/{self._pr_number}/comments"
        )
        response = requests.post(
            url,
            headers=self._headers,
            json={"body": message},
            timeout=30,
        )
        response.raise_for_status()

    def request_changes(self, message: str) -> None:
        """
        Cria uma review de REQUEST_CHANGES sem comentários inline.

        Chamado pelo reviewer.py quando há violações CRITICAL e
        BLOCK_ON_CRITICAL=true.

        Args:
            message: Mensagem explicativa exibida no topo da review.
        """
        url = (
            f"{_GITHUB_API_BASE}/repos/{self._repo}" f"/pulls/{self._pr_number}/reviews"
        )
        payload = {
            "commit_id": self._head_sha,
            "body": message,
            "event": "REQUEST_CHANGES",
            "comments": [],
        }
        response = requests.post(url, headers=self._headers, json=payload, timeout=30)
        response.raise_for_status()
        console.log("[red]⛔ GitHubPublisher:[/red] REQUEST_CHANGES enviado ao PR.")

    # ── Internos ──────────────────────────────────────────────────────────

    def _build_review_comments(self, violations: ViolationList) -> list:
        """
        Constrói a lista de comentários inline para a API do GitHub.

        Para cada violação, tenta localizar a linha no patch do arquivo.
        Violações não localizáveis são ignoradas nos comentários inline
        (mas aparecem no sumário da review).
        """
        comments = []
        for file_diff, violation in violations:
            position = _find_diff_position(file_diff.patch, violation.line_content)
            if position is not None:
                comments.append(
                    {
                        "path": file_diff.filename,
                        "position": position,
                        "body": _format_inline_comment(violation),
                    }
                )
        return comments

    def _create_review(self, comments: list, severity_counts: dict[str, int]) -> None:
        """
        Cria uma review consolidada com comentários inline e sumário.

        A API do GitHub recebe todos os comentários de uma só vez, evitando
        múltiplas requests e reduzindo o risco de rate limiting.

        O evento é COMMENT por padrão; REQUEST_CHANGES é tratado
        separadamente pelo reviewer.py via ``request_changes()``.
        """
        total = sum(severity_counts.values())
        body = _build_summary_body(total, severity_counts)

        payload = {
            "commit_id": self._head_sha,
            "body": body,
            "event": "COMMENT",
            "comments": comments,
        }
        url = (
            f"{_GITHUB_API_BASE}/repos/{self._repo}" f"/pulls/{self._pr_number}/reviews"
        )
        response = requests.post(url, headers=self._headers, json=payload, timeout=30)
        response.raise_for_status()


# ── Funções puras auxiliares ───────────────────────────────────────────────────


def _find_diff_position(patch: str, line_content: str) -> int | None:
    """
    Encontra a posição (1-indexed) de uma linha adicionada dentro do patch.

    A "posição" no diff unificado do GitHub conta a partir de 1, incluindo
    as linhas de cabeçalho de hunk (``@@ ... @@``). Ela é usada pela API
    de review comments como identificador de localização.

    Estratégia:
    1. Itera linha a linha do patch incrementando o contador de posição.
    2. Conta linhas de hunk, adicionadas (+) e de contexto.
    3. **Não** conta linhas removidas (-), pois elas não existem na versão nova.
    4. Retorna a posição da primeira linha adicionada que contenha
       ``line_content`` (busca substring, após remover o prefixo '+').

    Args:
        patch: Texto bruto do diff unificado (campo ``patch`` da GitHub API).
        line_content: Trecho de código que a violação aponta.

    Returns:
        Inteiro 1-indexed se encontrado, None caso contrário.
    """
    if not patch or not line_content:
        return None

    # Normaliza para comparação: remove espaços extras das extremidades
    needle = line_content.strip()

    position = 0
    for line in patch.splitlines():
        if line.startswith("@@"):
            position += 1  # cabeçalho de hunk também conta como posição
        elif line.startswith("-"):
            pass  # linhas removidas não incrementam posição
        else:
            position += 1  # linha de contexto ou adicionada

        # Verifica correspondência nas linhas adicionadas
        if line.startswith("+") and not line.startswith("+++"):
            added_content = line[1:].strip()
            if needle in added_content:
                return position

    return None


def _format_inline_comment(violation: Violation) -> str:
    """
    Formata uma Violation como corpo de comentário inline no GitHub.

    Usa Markdown compatível com a interface do GitHub.

    Args:
        violation: Objeto Violation com os dados da infração.

    Returns:
        String formatada em Markdown.
    """
    emoji = _SEVERITY_EMOJI.get(violation.severity, "ℹ️")
    return (
        f"{emoji} **[{violation.severity}]** {violation.violation_description}\n\n"
        f"📖 **Norma violada:** `{violation.norm_reference}`\n\n"
        f"💡 **Sugestão:** {violation.suggestion}"
    )


def _count_by_severity(violations: ViolationList) -> dict[str, int]:
    """
    Conta as violações agrupadas por severidade.

    Args:
        violations: Lista de (FileDiff, Violation).

    Returns:
        Dict com chaves 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW' e suas contagens.
    """
    counts: dict[str, int] = {}
    for _, v in violations:
        counts[v.severity] = counts.get(v.severity, 0) + 1
    return counts


def _build_summary_body(total: int, counts: dict[str, int]) -> str:
    """
    Constrói o corpo Markdown do sumário da review.

    Inclui uma tabela com a contagem por severidade e um rodapé rastreável.

    Args:
        total: Total de violações encontradas.
        counts: Dict com contagens por severidade.

    Returns:
        String Markdown pronta para o corpo da review.
    """
    lines = [
        f"## 🤖 RAG-Reviewer: {total} violação(ões) detectada(s)\n",
        "| Severidade | Quantidade |",
        "|---|---|",
    ]
    for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = counts.get(severity, 0)
        if count > 0:
            emoji = _SEVERITY_EMOJI.get(severity, "")
            lines.append(f"| {emoji} {severity} | {count} |")

    lines.append(
        "\n> *Revisão automática gerada pelo RAG-Reviewer com base nas "
        "normas organizacionais indexadas.*"
    )
    return "\n".join(lines)
