"""Settings tolera variaveis antigas do .env (ex.: BLOCK_ON_CRITICAL, removida em D-011)."""

from __future__ import annotations

from rag_reviewer.config import Settings


def test_variavel_removida_no_env_nao_derruba_a_configuracao(tmp_path, monkeypatch):
    # O módulo carrega o .env real em os.environ; isola as variáveis do teste.
    monkeypatch.delenv("TOP_K_CHUNKS", raising=False)
    monkeypatch.delenv("BLOCK_ON_CRITICAL", raising=False)
    env = tmp_path / ".env"
    env.write_text("BLOCK_ON_CRITICAL=true\nTOP_K_CHUNKS=7\n", encoding="utf-8")
    settings = Settings(_env_file=str(env))
    top_k = settings.top_k_chunks  # variável local: a falha não imprime o repr do Settings
    tem_campo_antigo = hasattr(settings, "block_on_critical")
    assert top_k == 7
    assert not tem_campo_antigo
