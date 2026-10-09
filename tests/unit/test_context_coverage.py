"""Cobertura de contexto: a norma da linha positiva chegou ao LLM?"""

from __future__ import annotations

from types import SimpleNamespace

from evaluation.retrieval.context_coverage import cobertura_de_contexto

BOOLEANO = "Don't compare boolean values to True or False using `==`."


class _RetrieverFalso:
    def __init__(self, por_arquivo):
        self._por_arquivo = por_arquivo

    def retrieve_for_file(self, file_diff):
        chunks = self._por_arquivo.get(file_diff.filename)
        return SimpleNamespace(chunks=[{"text": t} for t in chunks]) if chunks is not None else None


def _arquivo(nome, linhas):
    return {
        "filename": nome,
        "status": "added",
        "patch": "",
        "added_lines": [
            {"line": ln, "viola": sub is not None, "sub_regra": sub} for ln, sub in linhas
        ],
    }


def test_marca_se_a_norma_esta_no_contexto_do_arquivo():
    dataset = [
        {
            "pr_id": "PR-1",
            "files": [
                _arquivo("a.py", [("if x == True:", "booleano"), ("y = 1", None)]),
                _arquivo("b.py", [("x=1", "espaco_operador")]),
            ],
        }
    ]
    retriever = _RetrieverFalso({"a.py": [BOOLEANO, "outro texto"], "b.py": ["sem norma"]})

    linhas = cobertura_de_contexto(dataset, retriever)

    assert [(r["filename"], r["sub_regra"], r["no_contexto"]) for r in linhas] == [
        ("a.py", "booleano", True),
        ("b.py", "espaco_operador", False),
    ]
    assert linhas[0]["palavras_contexto"] == len(BOOLEANO.split()) + 2


def test_arquivo_sem_contexto_nao_cobre_nada():
    dataset = [{"pr_id": "PR-1", "files": [_arquivo("a.py", [("x=1", "espaco_operador")])]}]
    linhas = cobertura_de_contexto(dataset, _RetrieverFalso({}))
    assert linhas == [
        {"pr_id": "PR-1", "filename": "a.py", "line": "x=1",
         "sub_regra": "espaco_operador", "no_contexto": False, "palavras_contexto": 0}
    ]
