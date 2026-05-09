"""
config.py — Configurações centralizadas do RAG-Reviewer.

Carrega variáveis de ambiente e fornece defaults seguros para todos os módulos.
Usa Pydantic BaseSettings para validação automática de tipos.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Caminho absoluto para o .env na raiz do projeto (funciona independente do cwd)
_ENV_FILE = Path(__file__).parent.parent / ".env"

# load_dotenv como fallback explícito para desenvolvimento local.
# override=False garante que variáveis já definidas (ex: pelo GitHub Actions) não sejam sobrescritas.
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)


class Settings(BaseSettings):
    """Configurações do sistema — lidas de variáveis de ambiente."""

    # ── GitHub ──────────────────────────────────────────────────────────────
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    repo_full_name: str = Field(default="", alias="REPO_FULL_NAME")
    pr_number: int = Field(default=0, alias="PR_NUMBER")
    pr_head_sha: str = Field(default="", alias="PR_HEAD_SHA")
    pr_base_sha: str = Field(default="", alias="PR_BASE_SHA")

    # ── LLM ─────────────────────────────────────────────────────────────────
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    llm_model: str = Field(default="llama-3.3-70b-versatile", alias="LLM_MODEL")

    # ── Qdrant ───────────────────────────────────────────────────────────────
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(
        default="style_guide_chunks", alias="QDRANT_COLLECTION"
    )

    # ── Embedding ────────────────────────────────────────────────────────────
    embedding_model: str = Field(default="all-MiniLM-L6-v2", alias="EMBEDDING_MODEL")

    # ── Retrieval ────────────────────────────────────────────────────────────
    top_k_chunks: int = Field(default=5, alias="TOP_K_CHUNKS")
    score_threshold: float = Field(default=0.55, alias="SCORE_THRESHOLD")
    max_diff_tokens: int = Field(default=3000, alias="MAX_DIFF_TOKENS")

    # ── Comportamento ────────────────────────────────────────────────────────
    block_on_critical: bool = Field(default=True, alias="BLOCK_ON_CRITICAL")

    model_config = SettingsConfigDict(
        populate_by_name=True,
        env_file=str(_ENV_FILE),  # caminho absoluto — independente do cwd
        env_file_encoding="utf-8",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna instância singleton das configurações (com cache)."""
    return Settings()
