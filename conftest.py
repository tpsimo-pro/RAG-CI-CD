# conftest.py — Configurações globais do pytest
import sys
from pathlib import Path

# Adiciona o diretório raiz do projeto ao sys.path para que os imports funcionem
# tanto ao rodar `pytest` da raiz quanto de subdiretórios
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
