"""Catalogo das normas da PEP 8 avaliadas (D-010).

Fonte unica: o validador do dataset, a conformidade (oraculo do ruff), o
gabarito de recuperacao e a citacao da norma derivam daqui. Este modulo e
instrumentacao de avaliacao; o sistema em producao nao o usa.

`regra` (familia) e `sub_regra` (norma) sao os nomes dos campos do dataset.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Padrao de citacao da familia: casa a `norm_reference` do LLM, que vem do
# contexto `[Fonte: ... | Secao: ...]` montado a partir de `pep-0008.md`.
FAMILIAS: dict[str, re.Pattern[str]] = {
    "pep8-recomendacoes": re.compile(
        r"programming\s+recommendations|bare\s+except", re.IGNORECASE
    ),
    "pep8-nomes": re.compile(r"naming|\bnames?\b", re.IGNORECASE),
    "pep8-layout": re.compile(
        r"code\s+lay-?out|blank\s+lines|maximum\s+line\s+length|indentation",
        re.IGNORECASE,
    ),
    "pep8-imports": re.compile(r"\bimports?\b", re.IGNORECASE),
    "pep8-espacos": re.compile(
        r"whitespace|pet\s+peeves|other\s+recommendations", re.IGNORECASE
    ),
    "pep8-comentarios": re.compile(r"\bcomments?\b", re.IGNORECASE),
}


@dataclass(frozen=True)
class Norma:
    """Uma norma da PEP 8 que o piloto avalia."""

    id: str
    familia: str
    ancora: re.Pattern[str]
    """Enunciado da norma no texto da PEP 8 (quebras de linha valem espaco)."""

    ruff: frozenset[str]
    """Codigos do ruff que podem acusar uma linha rotulada com esta norma."""

    exemplo: str
    """Modulo minimo que viola so esta norma (teste contra o ruff instalado)."""

    so_arquivo_novo: bool = False
    """Depende da vizinhanca: so aparece em arquivo novo (D-010)."""

    ast: bool = False
    """Tambem detectada por checagem AST em `conformity.py`."""


def _a(texto: str) -> re.Pattern[str]:
    return re.compile(texto, re.IGNORECASE)


NORMAS: tuple[Norma, ...] = (
    Norma(
        "booleano",
        "pep8-recomendacoes",
        _a(r"compare\s+boolean\s+values\s+to\s+True\s+or\s+False"),
        frozenset({"E712"}),
        "x = 1\nif x == True:\n    pass\n",
    ),
    Norma(
        "nulo",
        "pep8-recomendacoes",
        _a(r"comparisons\s+to\s+singletons\s+like\s+None"),
        frozenset({"E711"}),
        "x = 1\nif x == None:\n    pass\n",
    ),
    Norma(
        "except_nu",
        "pep8-recomendacoes",
        _a(
            r"mention\s+specific\s+exceptions\s+whenever\s+possible\s+instead"
            r"\s+of\s+using\s+a\s+bare"
        ),
        frozenset({"E722"}),
        "try:\n    run()\nexcept:\n    pass\n",
    ),
    Norma(
        "not_is",
        "pep8-recomendacoes",
        _a(r"use\s+`?is\s+not`?\s+operator\s+rather\s+than"),
        frozenset({"E714"}),
        "x = 1\nif not x is None:\n    pass\n",
    ),
    Norma(
        "tipo_isinstance",
        "pep8-recomendacoes",
        _a(r"object\s+type\s+comparisons\s+should\s+always\s+use\s+isinstance"),
        frozenset({"E721"}),
        "a = 1\nb = 2\nif type(a) == type(b):\n    pass\n",
    ),
    Norma(
        "lambda_atribuido",
        "pep8-recomendacoes",
        _a(r"always\s+use\s+a\s+def\s+statement\s+instead\s+of\s+an\s+assignment"),
        frozenset({"E731"}),
        "double = lambda v: v * 2\n",
    ),
    Norma(
        "instrucoes_compostas",
        "pep8-recomendacoes",
        _a(r"compound\s+statements\s+\(multiple\s+statements\s+on\s+the\s+same"),
        frozenset({"E701", "E702"}),
        "x = 1; y = 2\n",
    ),
    Norma(
        "nome_funcao",
        "pep8-nomes",
        _a(r"function\s+names\s+should\s+be\s+lowercase"),
        frozenset({"N802"}),
        "def CalculateTax(order):\n    return order\n",
    ),
    Norma(
        "nome_classe",
        "pep8-nomes",
        _a(r"class\s+names\s+should\s+normally\s+use\s+the\s+CapWords"),
        frozenset({"N801"}),
        "class order_item:\n    pass\n",
    ),
    Norma(
        "nome_proibido",
        "pep8-nomes",
        _a(r"never\s+use\s+the\s+characters\s+'l'"),
        frozenset({"E741", "N806"}),
        "l = 1\n",
    ),
    Norma(
        "erro_sufixo",
        "pep8-nomes",
        _a(r"you\s+should\s+use\s+the\s+suffix\s+\"Error\"\s+on\s+your"),
        frozenset({"N818"}),
        "class PaymentFailure(Exception):\n    pass\n",
    ),
    Norma(
        "self_cls",
        "pep8-nomes",
        _a(r"always\s+use\s+`?self`?\s+for\s+the\s+first\s+argument\s+to\s+instance"),
        frozenset({"N804", "N805"}),
        "class Cart:\n    def total(this):\n        return 0\n",
    ),
    Norma(
        "constante_maiuscula",
        "pep8-nomes",
        _a(
            r"constants\s+are\s+usually\s+defined\s+on\s+a\s+module\s+level\s+and"
            r"\s+written\s+in\s+all\s+capital\s+letters"
        ),
        frozenset({"N816"}),
        "maxRetries = 3\n",
        ast=True,
    ),
    Norma(
        "linha_longa",
        "pep8-layout",
        _a(r"limit\s+all\s+lines\s+to\s+a\s+maximum\s+of\s+79\s+characters"),
        frozenset({"E501"}),
        "TEXT = '" + "a" * 80 + "'\n",
    ),
    Norma(
        "linhas_em_branco",
        "pep8-layout",
        _a(r"surround\s+top-level\s+function\s+and\s+class\s+definitions\s+with"),
        frozenset({"E301", "E302", "E303", "E305"}),
        "def first():\n    pass\ndef second():\n    pass\n",
        so_arquivo_novo=True,
    ),
    Norma(
        "import_unico",
        "pep8-imports",
        _a(r"imports\s+should\s+usually\s+be\s+on\s+separate\s+lines"),
        frozenset({"E401", "I001"}),
        "import os, sys\n",
    ),
    Norma(
        "import_topo",
        "pep8-imports",
        _a(r"imports\s+are\s+always\s+put\s+at\s+the\s+top\s+of\s+the\s+file"),
        frozenset({"E402"}),
        "VALUE = 1\nimport os\n",
        so_arquivo_novo=True,
    ),
    Norma(
        "import_estrela",
        "pep8-imports",
        _a(r"wildcard\s+imports\s+\(`from\s+<module>\s+import\s+\*`\)\s+should"),
        frozenset({"F403"}),
        "from os import *\n",
    ),
    Norma(
        "import_ordem",
        "pep8-imports",
        _a(r"imports\s+should\s+be\s+grouped\s+in\s+the\s+following\s+order"),
        frozenset({"I001"}),
        "import sys\nimport os\n",
        so_arquivo_novo=True,
    ),
    Norma(
        "espaco_operador",
        "pep8-espacos",
        _a(r"always\s+surround\s+these\s+binary\s+operators\s+with\s+a\s+single"),
        frozenset({"E225"}),
        "x=1\n",
    ),
    Norma(
        "espaco_parenteses",
        "pep8-espacos",
        _a(r"immediately\s+inside\s+parentheses,\s+brackets\s+or\s+braces"),
        frozenset({"E201", "E202"}),
        "print( 1 )\n",
    ),
    Norma(
        "espaco_antes_virgula",
        "pep8-espacos",
        _a(r"immediately\s+before\s+a\s+comma,\s+semicolon,\s+or\s+colon"),
        frozenset({"E203"}),
        "print(1 , 2)\n",
    ),
    Norma(
        "comentario_inline",
        "pep8-comentarios",
        _a(r"inline\s+comments\s+should\s+be\s+separated\s+by\s+at\s+least\s+two"),
        frozenset({"E261", "E262", "E265"}),
        "x = 1 # nota\n",
    ),
)

NORMAS_POR_ID: dict[str, Norma] = {n.id: n for n in NORMAS}


def ids_da_familia(familia: str) -> set[str]:
    """Normas (sub_regras) de uma familia (regra)."""
    return {n.id for n in NORMAS if n.familia == familia}


def normas_do_chunk(texto: str) -> set[str]:
    """Normas cujo enunciado esta no texto de um chunk recuperado."""
    return {n.id for n in NORMAS if n.ancora.search(texto)}


# Formas validas que parecem violar a norma (negativos dificeis). O validador
# exige pelo menos 2 linhas `hard_negative` da familia da norma que casem algum
# destes padroes.
def _p(*padroes: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p) for p in padroes)


NEGATIVOS: dict[str, tuple[re.Pattern[str], ...]] = {
    "booleano": _p(r"\bis (?:True|False)\b", r"^\s*if\s+(?:not\s+)?[\w.]+\s*:"),
    "nulo": _p(r"\bis None\b", r"\bis not None\b"),
    "except_nu": _p(r"^\s*except\s+[\w(]", r"^\s*except\s*:"),
    "not_is": _p(r"\bis not\b", r"^\s*(?:if|while)\s+not\s+[\w.]+\s*:"),
    "tipo_isinstance": _p(r"\bisinstance\(", r"\btype\([^)]*\)\s+is\b"),
    "lambda_atribuido": _p(r"key=lambda\b", r"[(,]\s*lambda\b"),
    "instrucoes_compostas": _p(
        r"[\"'][^\"']*;[^\"']*[\"']", r"\[[^\]]*:[^\]]*\]", r"\{[^}]*:[^}]*\}"
    ),
    "nome_funcao": _p(r"^\s*def\s+__init__\(", r"^\s*def\s+_?[a-z]+_[a-z_]+\("),
    "nome_classe": _p(r"^\s*class\s+[A-Z][a-z]+[A-Z]\w*", r"^\s*class\s+_[A-Z]\w*"),
    "nome_proibido": _p(r"^\s*lower\s*=", r"^\s*for\s+[ij]\s+in\b", r"\.l\b"),
    "erro_sufixo": _p(r"class\s+\w+Error\(", r"class\s+\w+\((?!.*Exception)"),
    "self_cls": _p(r"\(self\b", r"\(cls\b"),
    "constante_maiuscula": _p(r"^[A-Z][A-Z0-9_]*\s*=", r"^[a-z_]+\s*="),
    "linha_longa": _p(r"^.{74,79}$"),
    "linhas_em_branco": _p(r"^(?:async\s+)?def\s", r"^class\s"),
    "import_unico": _p(r"^import\s+\w+\s*$", r"^from\s+\S+\s+import\s+\w+,\s*\w+"),
    "import_topo": _p(r"^(?:import|from)\s"),
    "import_estrela": _p(r"^from\s+\S+\s+import\s+\(", r"\*args|\*\*kwargs"),
    "import_ordem": _p(r"^(?:import|from)\s"),
    "espaco_operador": _p(r"[(,]\s*\w+=[^=\s]", r"\w\s==\s\w"),
    "espaco_parenteses": _p(r"\(\)|\[\]|\{\}", r"[\"'][^\"']*\(\s[^\"']*[\"']"),
    "espaco_antes_virgula": _p(r"[\"'][^\"']*\s,[^\"']*[\"']", r"\[[^\]]*:[^\]]*\]"),
    "comentario_inline": _p(r"\S  # \S", r"[\"'][^\"']*#[^\"']*[\"']"),
}
