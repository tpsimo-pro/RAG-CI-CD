"""
diff_parser.py - Estrutura do diff de um arquivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FileDiff:
    """Representa o diff de um único arquivo dentro de um PR."""

    filename: str
    """Caminho relativo do arquivo no repositório."""

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
