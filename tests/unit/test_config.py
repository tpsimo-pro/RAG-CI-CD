"""Settings tolera variaveis antigas do .env (ex.: BLOCK_ON_CRITICAL, removida em D-011)."""

from __future__ import annotations

from rag_reviewer.config import Settings


def test_variavel_removida_no_env_nao_derruba_a_configuracao(tmp_path):
    env = tmp_path / ".env"
    env.write_text("BLOCK_ON_CRITICAL=true\nTOP_K_CHUNKS=7\n", encoding="utf-8")
    settings = Settings(_env_file=str(env))
    assert settings.top_k_chunks == 7
    assert not hasattr(settings, "block_on_critical")
