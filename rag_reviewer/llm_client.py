"""
llm_client.py — Interface com o LLM para geração de revisões de código.

Responsabilidades:
  1. Montar o prompt de revisão com o diff e os chunks normativos recuperados.
  2. Chamar a API da Groq e obter a resposta em JSON.
  3. Parsear o JSON e retornar uma lista de objetos Violation.

Uso típico:
    client = LLMClient()
    violations = client.review(retrieved_context)
    # violations: List[Violation]
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from rag_reviewer.config import get_settings
from rag_reviewer.retriever import RetrievedContext

console = Console()

# Diretório dos prompts — relativo a este arquivo, independe do cwd
_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Severidades válidas conforme o planejamento
_VALID_SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW"})


# ── Modelos de dados ───────────────────────────────────────────────────────────


@dataclass
class Violation:
    """Representa uma única violação de norma identificada pelo LLM."""

    line_content: str
    """Trecho exato da linha do PR que viola a norma."""

    violation_description: str
    """Descrição clara e objetiva do que foi violado."""

    norm_reference: str
    """Referência à norma: nome do documento + seção/página."""

    severity: str
    """Severidade da violação: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'."""

    suggestion: str
    """Sugestão concreta de como corrigir a violação."""


# ── Cliente LLM ────────────────────────────────────────────────────────────────


class LLMClient:
    """
    Interface com a API da Groq para revisão de código.

    Constrói o prompt de revisão, chama a API e converte a resposta JSON
    em uma lista de objetos Violation.

    A inicialização é lazy: a biblioteca ``groq`` é importada apenas
    na primeira chamada a ``review()``, permitindo testes unitários sem a
    dependência instalada.
    """

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int = 2048,
    ) -> None:
        """
        Inicializa o cliente.

        Args:
            model: Nome do modelo Groq. Usa LLM_MODEL do .env se None.
            max_tokens: Limite de tokens na resposta do LLM.
        """
        settings = get_settings()
        self._api_key = settings.groq_api_key
        self._model = model or settings.llm_model
        self._max_tokens = max_tokens
        self._client = None  # lazy — importado em _get_client()

        self._system_prompt = self._load_prompt("system_prompt.txt")
        self._review_template = self._load_prompt("review_template.txt")

    # ── Propriedades ──────────────────────────────────────────────────────

    @property
    def model(self) -> str:
        return self._model

    # ── Interface pública ─────────────────────────────────────────────────

    def review(self, context: RetrievedContext) -> list[Violation]:
        """
        Analisa um arquivo do PR e retorna as violações encontradas.

        Args:
            context: RetrievedContext com o diff do arquivo e os chunks normativos.

        Returns:
            Lista de Violation. Vazia se não houver violações ou se o LLM
            retornar JSON com "violations": [].

        Raises:
            ValueError: Quando GROQ_API_KEY não está configurada.
            json.JSONDecodeError: Quando o LLM não retorna JSON válido.
        """
        self._validate_api_key()

        user_message = self._build_user_message(context)

        console.log(
            f"[cyan]LLMClient:[/cyan] revisando "
            f"[bold]{context.file_diff.filename}[/bold] "
            f"com modelo [bold]{self._model}[/bold]..."
        )

        raw_response = self._call_api(user_message)
        violations = self._parse_response(raw_response)

        console.log(
            f"[green]✅ LLMClient:[/green] "
            f"{len(violations)} violação(ões) encontrada(s) em "
            f"[bold]{context.file_diff.filename}[/bold]."
        )
        return violations

    # ── Internos ──────────────────────────────────────────────────────────

    def _validate_api_key(self) -> None:
        """Verifica se a API key está configurada antes de chamar a API."""
        if not self._api_key:
            raise ValueError(
                "GROQ_API_KEY não está configurada. "
                "Adicione ao .env ou às variáveis de ambiente."
            )

    def _build_user_message(self, context: RetrievedContext) -> str:
        """Monta o prompt de revisão com os dados do contexto."""
        chunks_text = "\n\n---\n\n".join(
            f"[Fonte: {c['source']} | Seção: {c['section']}]\n{c['text']}"
            for c in context.chunks
        )
        return self._review_template.format(
            filename=context.file_diff.filename,
            added_lines="\n".join(context.file_diff.added_lines),
            retrieved_chunks=chunks_text,
        )

    def _call_api(self, user_message: str) -> str:
        """Chama a API da Groq e retorna o texto bruto da resposta."""
        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            console.log(f"[bold red]Erro na API da Groq:[/bold red] {exc}")
            raise

    def _parse_response(self, raw: str) -> list[Violation]:
        """
        Converte o JSON bruto do LLM em uma lista de Violation.

        Estratégia de parsing defensivo:
        1. Tenta parsear o texto diretamente como JSON.
        2. Se falhar, tenta extrair um bloco JSON via regex (caso o LLM
           adicione texto fora do JSON apesar das instruções).
        3. Valida que cada violation tem os campos obrigatórios.
        4. Normaliza a severity para uppercase; ignora valores inválidos.
        """
        data = self._extract_json(raw)
        raw_violations = data.get("violations", [])

        violations: list[Violation] = []
        for i, v in enumerate(raw_violations):
            try:
                violation = self._parse_single_violation(v)
                violations.append(violation)
            except (KeyError, TypeError) as exc:
                console.log(
                    f"[yellow]⚠️  LLMClient:[/yellow] violação #{i} ignorada "
                    f"(campo inválido: {exc})."
                )
        return violations

    def _extract_json(self, raw: str) -> dict:
        """
        Extrai um dicionário JSON do texto bruto.

        Tenta parsing direto; se falhar, procura por bloco ```json ... ```.
        """
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Tenta extrair bloco de código JSON
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        raise json.JSONDecodeError(
            f"LLM não retornou JSON válido. Resposta recebida:\n{raw[:500]}",
            doc=raw,
            pos=0,
        )

    def _parse_single_violation(self, v: dict) -> Violation:
        """Converte um dict em Violation, validando campos obrigatórios."""
        severity = str(v.get("severity", "LOW")).upper()
        if severity not in _VALID_SEVERITIES:
            severity = "LOW"

        return Violation(
            line_content=str(v["line_content"]),
            violation_description=str(v["violation_description"]),
            norm_reference=str(v["norm_reference"]),
            severity=severity,
            suggestion=str(v["suggestion"]),
        )

    def _get_client(self):
        """Retorna cliente Groq com lazy initialization."""
        if self._client is None:
            try:
                from groq import Groq
            except ImportError as exc:
                raise ImportError(
                    "groq não está instalado. Execute: pip install groq"
                ) from exc
            self._client = Groq(api_key=self._api_key)
            console.log(
                f"[cyan]LLMClient:[/cyan] cliente Groq inicializado "
                f"(modelo: [bold]{self._model}[/bold])."
            )
        return self._client

    @staticmethod
    def _load_prompt(filename: str) -> str:
        """Lê um arquivo de prompt do diretório prompts/."""
        path = _PROMPTS_DIR / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Arquivo de prompt não encontrado: {path}. "
                "Verifique se rag_reviewer/prompts/ existe."
            )
        return path.read_text(encoding="utf-8")
