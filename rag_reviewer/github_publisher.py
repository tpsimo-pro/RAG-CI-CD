"""
github_publisher.py - Publicação da revisão no PR pela API REST do GitHub.

Responsabilidades:
  1. Achar a posição de cada violação no diff unificado.
  2. Criar UMA review `COMMENT` com um comentário inline por violação.
  3. Pular comentários que já existem no PR (o Action roda a cada push).
  4. Cair para um sumário sem inline quando a API recusa as posições (422).

O revisor nunca bloqueia o PR: a PEP 8 é estilo (D-011).
"""

from __future__ import annotations

import requests
from rich.console import Console

from rag_reviewer.config import get_settings
from rag_reviewer.diff_parser import FileDiff, PullRequestDiff
from rag_reviewer.llm_client import Violation

console = Console()

ViolationList = list[tuple[FileDiff, Violation]]

_SEVERITIES = ("HIGH", "MEDIUM", "LOW")
_GITHUB_API_BASE = "https://api.github.com"
_APPROVAL_MESSAGE = "Nenhuma violação da PEP 8 detectada nas linhas adicionadas."


class GitHubPublisher:
    """Publica a revisão no PR: uma review COMMENT com comentários inline."""

    def __init__(
        self,
        token: str | None = None,
        repo: str | None = None,
        pr_number: int | None = None,
        head_sha: str | None = None,
    ) -> None:
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

    def publish(
        self,
        violations: ViolationList,
        pr_diff: PullRequestDiff,
        unreviewed: list[str] | None = None,
        model: str | None = None,
    ) -> None:
        """
        Publica a revisão.

        Sem violações e sem arquivos não revisados, publica só a aprovação.
        Com violações, publica uma review com os comentários que ainda não
        existem no PR. Se nada é novo, não publica nada.
        """
        unreviewed = unreviewed or []
        if not violations and not unreviewed:
            self.post_summary(_APPROVAL_MESSAGE)
            return

        existentes = self._existing_comments()
        inline, sem_posicao, novas = self._build_review_comments(violations, existentes)
        if violations and not novas and not unreviewed:
            console.log(
                "[dim]GitHubPublisher:[/dim] todos os comentários já existem no PR; "
                "nada a publicar."
            )
            return

        notas = [_nota(fd, v) for fd, v in sem_posicao]
        counts = _count_by_severity(novas)
        self._create_review(inline, counts, notas, unreviewed, model)
        console.log(
            f"[green]GitHubPublisher:[/green] review publicada, "
            f"{len(novas)} violação(ões) nova(s), {len(inline)} comentário(s) inline."
        )

    def post_summary(self, message: str) -> None:
        """Publica um comentário geral (não inline) no PR."""
        url = f"{_GITHUB_API_BASE}/repos/{self._repo}/issues/{self._pr_number}/comments"
        response = requests.post(
            url, headers=self._headers, json={"body": message}, timeout=30
        )
        response.raise_for_status()

    # ── Internos ──────────────────────────────────────────────────────────

    def _existing_comments(self) -> set[tuple[str, str]]:
        """(path, corpo) dos comentários de review já publicados. Falha vira conjunto vazio."""
        url = f"{_GITHUB_API_BASE}/repos/{self._repo}/pulls/{self._pr_number}/comments"
        existentes: set[tuple[str, str]] = set()
        try:
            atual: str | None = url
            while atual:
                response = requests.get(
                    atual, headers=self._headers, params={"per_page": 100}, timeout=30
                )
                response.raise_for_status()
                existentes.update(
                    (c.get("path", ""), c.get("body", "")) for c in response.json()
                )
                atual = response.links.get("next", {}).get("url")
        except requests.RequestException as exc:
            console.log(
                f"[yellow]GitHubPublisher:[/yellow] não leu os comentários existentes "
                f"({exc}); publicando sem checar repetições."
            )
            return set()
        return existentes

    def _build_review_comments(
        self, violations: ViolationList, existentes: set[tuple[str, str]]
    ) -> tuple[list[dict], ViolationList, ViolationList]:
        """
        Separa as violações em comentários inline e violações sem posição.

        Returns:
            (inline, sem_posicao, novas): `novas` é tudo que ainda não existe no
            PR (inline mais sem posição), usado na contagem do sumário.
        """
        inline: list[dict] = []
        sem_posicao: ViolationList = []
        novas: ViolationList = []
        usadas: dict[str, set[int]] = {}
        for file_diff, violation in violations:
            corpo = _format_inline_comment(violation)
            if (file_diff.filename, corpo) in existentes:
                continue
            novas.append((file_diff, violation))
            posicao = _find_diff_position(
                file_diff.patch,
                violation.line_content,
                usadas.setdefault(file_diff.filename, set()),
            )
            if posicao is None:
                sem_posicao.append((file_diff, violation))
            else:
                inline.append(
                    {"path": file_diff.filename, "position": posicao, "body": corpo}
                )
        return inline, sem_posicao, novas

    def _create_review(
        self,
        comments: list[dict],
        counts: dict[str, int],
        notas: list[str],
        unreviewed: list[str],
        model: str | None,
    ) -> None:
        """Cria a review. Se a API recusar as posições (422), refaz só com o sumário."""
        url = f"{_GITHUB_API_BASE}/repos/{self._repo}/pulls/{self._pr_number}/reviews"
        total = sum(counts.values())
        payload = {
            "commit_id": self._head_sha,
            "body": _build_summary_body(total, counts, notas, unreviewed, model),
            "event": "COMMENT",
            "comments": comments,
        }
        response = requests.post(url, headers=self._headers, json=payload, timeout=30)
        if response.status_code == 422 and comments:
            console.log(
                "[yellow]GitHubPublisher:[/yellow] a API recusou os comentários inline "
                "(422); publicando só o sumário."
            )
            extras = [f"- `{c['path']}`: {c['body'].splitlines()[0]}" for c in comments]
            payload["body"] = _build_summary_body(
                total, counts, notas + extras, unreviewed, model
            )
            payload["comments"] = []
            response = requests.post(
                url, headers=self._headers, json=payload, timeout=30
            )
        response.raise_for_status()


# ── Funções puras ─────────────────────────────────────────────────────────────


def _find_diff_position(
    patch: str, line_content: str, usadas: set[int] | None = None
) -> int | None:
    """
    Posição (1-indexada) de uma linha adicionada dentro do patch.

    A posição conta a partir do primeiro cabeçalho de hunk, incluindo
    cabeçalhos, linhas de contexto e adicionadas, e não conta as removidas.
    Prefere a igualdade exata (após `strip`) à substring e ignora as posições
    em `usadas`, para que violações de texto igual caiam em linhas diferentes.
    A posição escolhida é registrada em `usadas`.
    """
    if not patch or not line_content or not line_content.strip():
        return None
    usadas = usadas if usadas is not None else set()
    alvo = line_content.strip()
    exata: int | None = None
    parcial: int | None = None
    posicao = 0
    for linha in patch.splitlines():
        if linha.startswith("-"):
            continue
        posicao += 1
        if (
            linha.startswith("+")
            and not linha.startswith("+++")
            and posicao not in usadas
        ):
            conteudo = linha[1:].strip()
            if conteudo == alvo and exata is None:
                exata = posicao
            elif alvo in conteudo and parcial is None:
                parcial = posicao
    escolhida = exata if exata is not None else parcial
    if escolhida is not None:
        usadas.add(escolhida)
    return escolhida


def _format_inline_comment(violation: Violation) -> str:
    """Corpo Markdown do comentário inline: severidade, descrição, norma e correção."""
    if violation.ambiguous:
        abertura = (
            "**[LOW] Possível ambiguidade.** O texto da PEP 8 não decide este caso."
            f"\n\n{violation.violation_description}"
        )
    else:
        abertura = f"**[{violation.severity}]** {violation.violation_description}"
    return (
        f"{abertura}\n\n"
        f"**Norma:** `{violation.norm_reference}`\n\n"
        f"**Como corrigir:** {violation.suggestion}"
    )


def _nota(file_diff: FileDiff, violation: Violation) -> str:
    """Linha do sumário para uma violação sem posição localizável no diff."""
    return (
        f"- `{file_diff.filename}`: [{violation.severity}] "
        f"{violation.violation_description} (`{violation.norm_reference}`). "
        f"Linha: `{violation.line_content}`"
    )


def _count_by_severity(violations: ViolationList) -> dict[str, int]:
    """Conta as violações por severidade."""
    counts: dict[str, int] = {}
    for _, v in violations:
        counts[v.severity] = counts.get(v.severity, 0) + 1
    return counts


def _build_summary_body(
    total: int,
    counts: dict[str, int],
    notas: list[str] | None = None,
    unreviewed: list[str] | None = None,
    model: str | None = None,
) -> str:
    """Corpo Markdown da review: tabela por severidade, notas e arquivos não revisados."""
    if total:
        linhas = [
            f"## RAG-Reviewer: {total} violação(ões) detectada(s)\n",
            "| Severidade | Quantidade |",
            "|---|---|",
        ]
        for severidade in _SEVERITIES:
            if counts.get(severidade, 0) > 0:
                linhas.append(f"| {severidade} | {counts[severidade]} |")
    else:
        linhas = ["## RAG-Reviewer: nenhuma violação nova detectada\n"]
    if notas:
        linhas += ["", "Violações sem linha localizável no diff:", *notas]
    if unreviewed:
        linhas += [
            "",
            "Arquivos não revisados (falha na chamada ao LLM):",
            *[f"- `{nome}`" for nome in unreviewed],
        ]
    rodape = "Revisão automática do RAG-Reviewer com base na PEP 8"
    if model:
        rodape += f" (modelo `{model}`)"
    linhas += ["", f"> *{rodape}.*"]
    return "\n".join(linhas)
