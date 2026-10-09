"""O YAML do Action tem o que o spec exige (D-011)."""

from pathlib import Path

TEXTO = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "rag_reviewer.yml"
).read_text(encoding="utf-8")


def test_gatilho_e_permissoes():
    assert "types: [opened, synchronize, reopened]" in TEXTO
    assert '"**/*.py"' in TEXTO
    assert "pull-requests: write" in TEXTO
    assert "contents: read" in TEXTO
    assert "timeout-minutes: 10" in TEXTO


def test_executa_o_modulo_e_usa_os_secrets():
    assert "python -m rag_reviewer.main" in TEXTO
    for nome in ("GITHUB_TOKEN", "GROQ_API_KEY", "QDRANT_URL", "QDRANT_API_KEY"):
        assert nome in TEXTO
    assert "QDRANT_COLLECTION:  pep8_chunks" in TEXTO


def test_sem_bloqueio_e_sem_variaveis_sem_uso():
    assert "BLOCK_ON_CRITICAL" not in TEXTO
    assert "PR_BASE_SHA" not in TEXTO
