"""
diff_parser.py — Coleta e pré-processamento do diff de Pull Requests.

Responsabilidades:
  1. Coletar o diff de um PR via GitHub REST API (com paginação).
  2. Estruturar os dados em dataclasses tipadas (FileDiff, PullRequestDiff).
  3. Construir o texto de consulta (query text) otimizado para o RAG.

Uso típico (executado pelo runner do GitHub Actions):
    collector = DiffCollector()
    pr_diff   = collector.collect()
    for file_diff in pr_diff.files:
        query = build_query_text(file_diff)
        # → passa ao embedder e ao retriever
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import requests
from rich.console import Console

from rag_reviewer.config import get_settings

console = Console()

# Limite de caracteres do texto de consulta enviado ao modelo de embedding.
# Modelos como all-MiniLM-L6-v2 suportam até ~512 tokens (≈ 2 000 chars).
_MAX_QUERY_CHARS: int = 2_000

# Extensões de arquivo ignoradas na revisão (binários, locks, assets, etc.)
_IGNORED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".ico",
        ".webp",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".whl",
        ".exe",
        ".dll",
        ".lock",
        ".sum",
    }
)


# ── Modelos de dados ───────────────────────────────────────────────────────────


@dataclass
class FileDiff:
    """Representa o diff de um único arquivo dentro de um PR."""

    filename: str
    """Caminho relativo do arquivo no repositório. Ex: 'src/services/user_service.py'"""

    patch: str
    """Texto bruto do diff no formato unified diff (linhas +/-)."""

    status: str
    """Status da alteração: 'added' | 'modified' | 'deleted' | 'renamed' | 'copied'."""

    additions: int = 0
    """Número de linhas adicionadas."""

    deletions: int = 0
    """Número de linhas removidas."""

    added_lines: list[str] = field(default_factory=list)
    """Apenas as linhas efetivamente adicionadas (prefixo '+' removido)."""


@dataclass
class PullRequestDiff:
    """Representa o diff completo de um Pull Request."""

    pr_number: int
    """Número do PR no repositório."""

    repo: str
    """Nome completo do repositório. Ex: 'org/repo'."""

    files: list[FileDiff]
    """Lista de diffs por arquivo."""

    total_additions: int
    """Total de linhas adicionadas no PR."""

    total_deletions: int
    """Total de linhas removidas no PR."""


# ── Coletor de Diff ────────────────────────────────────────────────────────────


class DiffCollector:
    """
    Coleta e estrutura o diff de um PR via GitHub REST API.

    Lê as variáveis de ambiente GITHUB_TOKEN, REPO_FULL_NAME e PR_NUMBER
    por meio de ``get_settings()``.  Suporta paginação automática da API
    e filtra extensões de arquivos irrelevantes (binários, imagens, etc.).
    """

    _GITHUB_API_BASE = "https://api.github.com"

    # Sentinela para distinguir "não fornecido" de "fornecido como vazio".
    _UNSET = object()

    def __init__(
        self,
        token: str | None = None,
        repo: str | None = None,
        pr_number: int | None = None,
    ) -> None:
        """
        Inicializa o coletor.

        Os parâmetros são opcionais para facilitar testes unitários sem
        variáveis de ambiente.  Em produção, os valores vêm de ``get_settings()``.

        Quando um parâmetro é fornecido explicitamente (mesmo que vazio), ele
        tem prioridade sobre o valor de ``get_settings()``.  Isso permite que
        testes unitários passem valores inválidos e verifiquem a validação.
        """
        settings = get_settings()
        self._token: str = token if token is not None else settings.github_token
        self._repo: str = repo if repo is not None else settings.repo_full_name
        self._pr_number: int = (
            pr_number if pr_number is not None else settings.pr_number
        )
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ── Interface pública ──────────────────────────────────────────────────

    def collect(self) -> PullRequestDiff:
        """
        Coleta o diff do PR definido nas variáveis de ambiente.

        Returns:
            PullRequestDiff com todos os arquivos modificados, exceto:
            - arquivos deletados (sem código a revisar)
            - arquivos binários / com extensão ignorada

        Raises:
            requests.HTTPError: quando a API do GitHub retorna erro HTTP.
            ValueError: quando variáveis de ambiente obrigatórias estão ausentes.
        """
        self._validate_config()

        url = (
            f"{self._GITHUB_API_BASE}/repos/{self._repo}"
            f"/pulls/{self._pr_number}/files"
        )
        console.log(
            f"[cyan]DiffCollector:[/cyan] coletando diff do PR "
            f"[bold]#{self._pr_number}[/bold] em [bold]{self._repo}[/bold]..."
        )

        raw_files = self._paginate(url)
        files = self._parse_files(raw_files)

        pr_diff = PullRequestDiff(
            pr_number=self._pr_number,
            repo=self._repo,
            files=files,
            total_additions=sum(f.additions for f in files),
            total_deletions=sum(f.deletions for f in files),
        )

        console.log(
            f"[green]✅ Diff coletado:[/green] {len(files)} arquivo(s) relevante(s), "
            f"{pr_diff.total_additions} adição(ões), "
            f"{pr_diff.total_deletions} remoção(ões)."
        )
        return pr_diff

    # ── Internos ───────────────────────────────────────────────────────────

    def _validate_config(self) -> None:
        """Valida que as variáveis obrigatórias estão presentes."""
        missing = []
        if not self._token:
            missing.append("GITHUB_TOKEN")
        if not self._repo:
            missing.append("REPO_FULL_NAME")
        if not self._pr_number:
            missing.append("PR_NUMBER")
        if missing:
            raise ValueError(
                f"Variáveis de ambiente obrigatórias ausentes: {', '.join(missing)}"
            )

    def _paginate(self, url: str) -> list:
        """
        Coleta todas as páginas de uma URL paginada da API do GitHub.

        A API retorna até 100 itens por página; o link para a próxima página
        vem no header ``Link`` da resposta.
        """
        results: list = []
        current_url: str | None = url
        while current_url:
            response = requests.get(
                current_url,
                headers=self._headers,
                params={"per_page": 100},
                timeout=30,
            )
            response.raise_for_status()
            results.extend(response.json())
            current_url = response.links.get("next", {}).get("url")
        return results

    def _parse_files(self, raw_files: list) -> list[FileDiff]:
        """
        Converte a lista bruta da API em objetos FileDiff.

        Filtra:
        - Arquivos deletados (status == 'deleted')
        - Extensões ignoradas (binários, imagens, etc.)
        - Arquivos sem patch (binários detectados em tempo de execução)
        """
        files: list[FileDiff] = []
        skipped = 0

        for raw in raw_files:
            filename: str = raw.get("filename", "")
            status: str = raw.get("status", "")
            patch: str = raw.get("patch", "")

            # Arquivos deletados não precisam de revisão
            if status == "deleted":
                skipped += 1
                continue

            # Extensões de arquivo ignoradas (binários, assets)
            if _is_ignored_file(filename):
                skipped += 1
                continue

            # Arquivos sem patch (ex: binários renomeados)
            if not patch:
                skipped += 1
                continue

            added_lines = _extract_added_lines(patch)

            files.append(
                FileDiff(
                    filename=filename,
                    patch=patch,
                    status=status,
                    additions=raw.get("additions", 0),
                    deletions=raw.get("deletions", 0),
                    added_lines=added_lines,
                )
            )

        if skipped:
            console.log(
                f"[dim]DiffCollector:[/dim] {skipped} arquivo(s) ignorado(s) "
                "(deletados, binários ou sem patch)."
            )

        return files


# ── Funções auxiliares puras ───────────────────────────────────────────────────


def _extract_added_lines(patch: str) -> list[str]:
    """
    Extrai apenas as linhas adicionadas de um patch no formato unified diff.

    Remove o prefixo '+' de cada linha adicionada e ignora as linhas de
    cabeçalho do hunk (``+++ b/...``) e as linhas de contexto (sem prefixo).

    Args:
        patch: Texto bruto do diff no formato unified diff.

    Returns:
        Lista de strings com o conteúdo das linhas adicionadas (sem o '+').
    """
    added: list[str] = []
    for line in patch.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])  # remove o prefixo '+'
    return added


def _is_ignored_file(filename: str) -> bool:
    """
    Verifica se um arquivo deve ser ignorado com base na extensão.

    Args:
        filename: Caminho relativo do arquivo no repositório.

    Returns:
        True se o arquivo deve ser ignorado, False caso contrário.
    """
    suffix = os.path.splitext(filename)[1].lower()
    return suffix in _IGNORED_EXTENSIONS


def build_query_text(file_diff: FileDiff, max_chars: int = _MAX_QUERY_CHARS) -> str:
    """
    Constrói o texto de consulta para o RAG a partir de um FileDiff.

    O texto inclui:
    - O nome do arquivo como contexto (importante para o modelo de embedding
      inferir a linguagem e o domínio do código).
    - As linhas adicionadas no PR, que são o alvo da revisão.

    Se o texto resultante exceder ``max_chars``, ele é truncado com sufixo
    ``[TRUNCADO]`` para indicar ao LLM que o diff foi cortado.

    Args:
        file_diff: O diff de um arquivo.
        max_chars: Número máximo de caracteres no texto de consulta.

    Returns:
        String pronta para ser embedada e enviada ao retriever.
    """
    header = f"Arquivo: {file_diff.filename}\n"
    body = "\n".join(file_diff.added_lines)
    full_text = header + body

    if len(full_text) > max_chars:
        truncation_marker = "\n[TRUNCADO]"
        full_text = full_text[: max_chars - len(truncation_marker)] + truncation_marker

    return full_text
