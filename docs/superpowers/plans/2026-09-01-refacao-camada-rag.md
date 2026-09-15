# Refação da Camada de RAG — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconstruir a camada de recuperação do RAG-Reviewer até atingir `recall@5 >= 0.95` nas 60 linhas positivas, medindo o ganho isolado de cada mudança.

**Architecture:** Cinco configurações medidas cumulativamente sobre o mesmo gabarito. Corrige-se primeiro a origem dos chunks-lixo (o `document_loader`, não o chunker), depois a granularidade da consulta, depois o modelo de embedding, e por fim adiciona-se busca híbrida densa+esparsa com fusão RRF.

**Tech Stack:** Python 3.11 · sentence-transformers · Qdrant (`qdrant-client`) · `rich` · pytest

**Spec:** [`docs/superpowers/specs/2026-09-01-refacao-camada-rag-design.md`](../specs/2026-09-01-refacao-camada-rag-design.md)

## Global Constraints

- **Nenhuma degradação silenciosa.** Todo fallback altera o que está sendo medido sem avisar. Falhas de modelo, de Qdrant ou de encoder esparso derrubam a execução.
- **Os resultados nunca são fixos** (D-007). Quais linhas violam é sempre decisão de retrieval + LLM.
- **Corpus completo** (D-007): os três guias de `docs/style_guides/` permanecem indexados. Nunca reduzir o corpus para melhorar métrica.
- **Retrieval não chama o LLM.** Toda a avaliação desta spec é offline, determinística e de custo zero de API.
- Docstrings em português, `from __future__ import annotations`, type hints, saída via `rich` — seguir o estilo existente.
- Intocados: `llm_client.py`, os prompts, `github_publisher.py`, `diff_parser.py`.
- Python do projeto: `.venv/Scripts/python.exe` (Windows). Testes: `pytest`.

## Refinação da spec descoberta no planejamento

A spec §7 define 4 configurações e **omite a mudança para consulta por linha**, que também afeta o recall. Deixá-la fora atribuiria a outras camadas um ganho que é dela. O plano usa **5 configurações**:

| | Configuração |
|---|---|
| **L0** | Sistema atual: loader atual, chunker atual, consulta por arquivo, MiniLM inglês, denso puro, threshold 0.35 |
| **L1** | + loader ciente de cercas e chunker estrutural |
| **L2** | + consulta por linha |
| **L3** | + modelo multilíngue |
| **L4** | + busca híbrida (denso + esparso, fusão RRF) |

**L0 precisa ser medido ANTES de qualquer correção de código.** Depois de corrigir o loader, a linha de base é irrecuperável. Por isso as Tarefas 1–3 constroem a instrumentação e congelam o L0 antes que a Tarefa 4 toque em qualquer coisa.

---

## Task 1: Mapa de chaves normativas

Instrumentação de avaliação. Decide quais chaves normativas cada chunk carrega, de forma **independente de chunking** — é isso que torna L0..L4 comparáveis (spec §6.1).

**Files:**
- Create: `evaluation/retrieval/__init__.py`
- Create: `evaluation/retrieval/norm_map.py`
- Test: `tests/unit/test_norm_map.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `NORM_BOOLEANO: str = "pep8:secao-5:comparacao-booleana"`
  - `NORM_NULO: str = "pep8:secao-5:comparacao-nulo"`
  - `norm_keys_of_chunk(text: str) -> set[str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_norm_map.py
from evaluation.retrieval.norm_map import (
    NORM_BOOLEANO,
    NORM_NULO,
    norm_keys_of_chunk,
)


def test_chunk_com_norma_booleana_e_reconhecido():
    texto = (
        "5. Práticas de Código\n"
        "Comparações booleanas: Não compare valores booleanos com == True ou == False.\n"
        "Correto: if is_valid:\n"
        "Incorreto: if is_valid == True:"
    )
    assert NORM_BOOLEANO in norm_keys_of_chunk(texto)


def test_chunk_com_norma_de_nulos_e_reconhecido():
    texto = (
        "Comparações de nulos: Sempre use is ou is not ao comparar com None.\n"
        "Correto: if value is not None:\n"
        "Incorreto: if value != None:"
    )
    assert NORM_NULO in norm_keys_of_chunk(texto)


def test_chunk_irrelevante_nao_carrega_chave():
    texto = "1.1 Tamanho Máximo de Linha: o limite é de 79 caracteres."
    assert norm_keys_of_chunk(texto) == set()


def test_chunk_unico_pode_carregar_as_duas_chaves():
    texto = (
        "Não compare valores booleanos com == True ou == False.\n"
        "Sempre use is ou is not ao comparar com None."
    )
    assert norm_keys_of_chunk(texto) == {NORM_BOOLEANO, NORM_NULO}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_norm_map.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evaluation.retrieval'`

- [ ] **Step 3: Write minimal implementation**

```python
# evaluation/retrieval/norm_map.py
"""
norm_map.py — Chaves normativas estáveis para a avaliação de retrieval.

O gabarito de retrieval NÃO pode ser ancorado em `chunk_id`: os ids mudam
quando o chunker muda, e a ablação compara justamente configurações de
chunking diferentes. As chaves aqui definidas são estáveis entre
configurações, tornando `recall@k` comparável entre L0 e L4.

Este módulo é INSTRUMENTAÇÃO DE AVALIAÇÃO. O sistema em produção não o usa
e não deve passar a usá-lo: as chaves descrevem o gabarito, não o
comportamento do revisor.
"""

from __future__ import annotations

import re

NORM_BOOLEANO = "pep8:secao-5:comparacao-booleana"
NORM_NULO = "pep8:secao-5:comparacao-nulo"

# Um chunk carrega a chave quando contém o ENUNCIADO da norma. Casar o
# enunciado (e não apenas o exemplo) evita que um trecho que só mencione
# `== True` de passagem seja contado como portador da norma.
_PADRAO_BOOLEANO = re.compile(
    r"compare?\s+valores\s+booleanos|compara[çc][õo]es\s+booleanas",
    re.IGNORECASE,
)
_PADRAO_NULO = re.compile(
    r"compara[çc][õo]es\s+de\s+nulos|ao\s+comparar\s+com\s+none",
    re.IGNORECASE,
)


def norm_keys_of_chunk(text: str) -> set[str]:
    """
    Retorna as chaves normativas que este chunk carrega.

    Args:
        text: Texto integral do chunk recuperado.

    Returns:
        Conjunto de chaves; vazio se o chunk não contém nenhuma norma do piloto.
    """
    chaves: set[str] = set()
    if _PADRAO_BOOLEANO.search(text):
        chaves.add(NORM_BOOLEANO)
    if _PADRAO_NULO.search(text):
        chaves.add(NORM_NULO)
    return chaves
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_norm_map.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Auditoria manual obrigatória**

A spec §6.1 exige que o mapeamento seja auditável: um mapeamento frouxo inflaria o recall de **todas** as configurações ao mesmo tempo, escondendo o problema.

Run:
```bash
.venv/Scripts/python.exe -c "
import sys; sys.stdout.reconfigure(encoding='utf-8')
from indexer.document_loader import DocumentLoader
from evaluation.retrieval.norm_map import norm_keys_of_chunk
docs = DocumentLoader().load_directory('docs/style_guides')
for d in docs:
    k = norm_keys_of_chunk(d.text)
    if k:
        print(d.source, '|', d.section, '->', sorted(k))
"
```

Expected: apenas seções do `guia_python_pep8.md` referentes à Seção 5 aparecem. Se qualquer seção de `coding_standards.md` ou `architecture_patterns.md` aparecer, os padrões estão frouxos — aperte-os e repita.

- [ ] **Step 6: Commit**

```bash
git add evaluation/retrieval/__init__.py evaluation/retrieval/norm_map.py tests/unit/test_norm_map.py
git commit -m "feat(eval): chaves normativas estaveis para avaliacao de retrieval"
```

---

## Task 2: Gabarito de retrieval e métricas

O gabarito é **derivado** do dataset, não escrito à mão: `pilot_secao5.json` já rotula cada linha positiva com `sub_regra`.

**Files:**
- Create: `evaluation/retrieval/gold.py`
- Create: `evaluation/retrieval/metrics.py`
- Test: `tests/unit/test_retrieval_metrics.py`

**Interfaces:**
- Consumes: `NORM_BOOLEANO`, `NORM_NULO` da Task 1.
- Produces:
  - `GoldLine` dataclass com campos `pr_id: str`, `line: str`, `norm_key: str`
  - `build_gold(dataset_path: Path) -> list[GoldLine]`
  - `RetrievalOutcome` dataclass com `gold: GoldLine`, `ranked_norm_keys: list[set[str]]`
  - `recall_at_k(outcomes: list[RetrievalOutcome], k: int) -> float`
  - `context_precision_at_k(outcomes: list[RetrievalOutcome], k: int) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_retrieval_metrics.py
from evaluation.retrieval.gold import GoldLine
from evaluation.retrieval.metrics import (
    RetrievalOutcome,
    context_precision_at_k,
    recall_at_k,
)

NORM = "pep8:secao-5:comparacao-booleana"
OUTRA = "outra:norma"


def _outcome(*ranks: set[str]) -> RetrievalOutcome:
    return RetrievalOutcome(
        gold=GoldLine(pr_id="PR-001", line="if x == True:", norm_key=NORM),
        ranked_norm_keys=list(ranks),
    )


def test_recall_at_k_conta_acerto_em_qualquer_posicao_ate_k():
    # norma certa na 3a posicao
    o = _outcome(set(), {OUTRA}, {NORM})
    assert recall_at_k([o], k=5) == 1.0
    assert recall_at_k([o], k=3) == 1.0
    assert recall_at_k([o], k=2) == 0.0


def test_recall_at_k_e_media_entre_linhas():
    acerta = _outcome({NORM})
    erra = _outcome({OUTRA})
    assert recall_at_k([acerta, erra], k=5) == 0.5


def test_context_precision_mede_fracao_util_do_que_foi_entregue():
    # 1 chunk util entre 4 entregues
    o = _outcome({NORM}, {OUTRA}, set(), set())
    assert context_precision_at_k([o], k=4) == 0.25


def test_metricas_com_lista_vazia_nao_quebram():
    assert recall_at_k([], k=5) == 0.0
    assert context_precision_at_k([], k=5) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_retrieval_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evaluation.retrieval.gold'`

- [ ] **Step 3: Write `gold.py`**

```python
# evaluation/retrieval/gold.py
"""
gold.py — Gabarito de retrieval, derivado do dataset do piloto.

Para cada uma das 60 linhas POSITIVAS de `pilot_secao5.json`, qual chave
normativa precisa ter chegado ao LLM.

Apenas as positivas entram (spec §6.1): para uma linha negativa como
`if x is not None:`, a Seção 5 é justamente a norma que a declara correta —
seria relevante e ao mesmo tempo não deveria gerar violação. O gabarito
ficaria ambíguo, e métrica sobre ambiguidade não serve.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from evaluation.retrieval.norm_map import NORM_BOOLEANO, NORM_NULO

_SUB_REGRA_PARA_CHAVE = {
    "booleano": NORM_BOOLEANO,
    "nulo": NORM_NULO,
}


@dataclass(frozen=True)
class GoldLine:
    """Uma linha positiva e a norma que deveria ser recuperada para ela."""

    pr_id: str
    line: str
    norm_key: str


def build_gold(dataset_path: Path) -> list[GoldLine]:
    """
    Deriva o gabarito de retrieval do dataset de detecção.

    Raises:
        ValueError: Se alguma linha positiva tiver `sub_regra` desconhecida —
            falha ruidosa, nunca rótulo silenciosamente descartado.
    """
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    gold: list[GoldLine] = []

    for pr in dataset:
        for al in pr["added_lines"]:
            if not al["viola"]:
                continue
            sub = al["sub_regra"]
            if sub not in _SUB_REGRA_PARA_CHAVE:
                raise ValueError(
                    f"{pr['pr_id']}: sub_regra desconhecida {sub!r} "
                    f"na linha {al['line']!r}"
                )
            gold.append(
                GoldLine(
                    pr_id=pr["pr_id"],
                    line=al["line"],
                    norm_key=_SUB_REGRA_PARA_CHAVE[sub],
                )
            )

    return gold
```

- [ ] **Step 4: Write `metrics.py`**

```python
# evaluation/retrieval/metrics.py
"""
metrics.py — Métricas de recuperação: recall@k e precisão de contexto.

Todas operam sobre `RetrievalOutcome`, que guarda, para uma linha do
gabarito, as chaves normativas de cada chunk recuperado NA ORDEM do ranking.
Nenhuma métrica aqui depende de `chunk_id`, o que as torna comparáveis entre
configurações de chunking diferentes (spec §6.1).
"""

from __future__ import annotations

from dataclasses import dataclass

from evaluation.retrieval.gold import GoldLine


@dataclass
class RetrievalOutcome:
    """Resultado da recuperação para uma linha do gabarito."""

    gold: GoldLine
    ranked_norm_keys: list[set[str]]
    """Chaves normativas de cada chunk recuperado, na ordem do ranking."""

    def first_hit_rank(self) -> int | None:
        """Posição 1-indexada do primeiro chunk que carrega a norma exigida."""
        for i, keys in enumerate(self.ranked_norm_keys, start=1):
            if self.gold.norm_key in keys:
                return i
        return None


def recall_at_k(outcomes: list[RetrievalOutcome], k: int) -> float:
    """Fração das linhas cuja norma exigida apareceu entre os k primeiros."""
    if not outcomes:
        return 0.0
    acertos = sum(
        1
        for o in outcomes
        if (r := o.first_hit_rank()) is not None and r <= k
    )
    return acertos / len(outcomes)


def context_precision_at_k(outcomes: list[RetrievalOutcome], k: int) -> float:
    """
    Fração dos chunks entregues que carregavam a norma exigida.

    Não é decorativa: chunks-lixo comprovadamente induzem alucinação — o LLM
    passou a acusar linhas inocentes citando "Seção: Correto" (spec §1.1).
    """
    if not outcomes:
        return 0.0
    total = 0.0
    for o in outcomes:
        entregues = o.ranked_norm_keys[:k]
        if not entregues:
            continue
        uteis = sum(1 for keys in entregues if o.gold.norm_key in keys)
        total += uteis / len(entregues)
    return total / len(outcomes)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_retrieval_metrics.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Verify the gabarito has exactly 60 lines**

Run:
```bash
.venv/Scripts/python.exe -c "
from pathlib import Path
from evaluation.retrieval.gold import build_gold
from evaluation.retrieval.norm_map import NORM_BOOLEANO, NORM_NULO
g = build_gold(Path('evaluation/dataset/pilot_secao5.json'))
print('total:', len(g))
print('booleano:', sum(1 for x in g if x.norm_key == NORM_BOOLEANO))
print('nulo:', sum(1 for x in g if x.norm_key == NORM_NULO))
"
```
Expected: `total: 60`, `booleano: 30`, `nulo: 30` (D-004). Divergência = dataset ou derivação com defeito; pare e investigue.

- [ ] **Step 7: Commit**

```bash
git add evaluation/retrieval/gold.py evaluation/retrieval/metrics.py tests/unit/test_retrieval_metrics.py
git commit -m "feat(eval): gabarito de retrieval e metricas recall@k/MRR"
```

---

## Task 3: Harness de retrieval e congelamento da linha de base L0

**Esta tarefa precisa rodar ANTES de qualquer correção de código.** Depois que o loader for corrigido, o L0 é irrecuperável.

**Files:**
- Create: `evaluation/retrieval/run_retrieval_eval.py`
- Create: `evaluation/retrieval/results_L0.json` (gerado)
- Modify: `Makefile` (alvo `eval-retrieval`)

**Interfaces:**
- Consumes: `build_gold`, `RetrievalOutcome`, `recall_at_k`, `context_precision_at_k`, `norm_keys_of_chunk`.
- Produces: `run_retrieval_eval(dataset_path: Path, label: str, per_line: bool) -> dict`

- [ ] **Step 1: Write the harness**

```python
# evaluation/retrieval/run_retrieval_eval.py
"""
run_retrieval_eval.py — Avaliação da camada de recuperação.

NÃO chama o LLM. É offline, determinística e de custo zero de API, então
pode rodar quantas vezes for necessário durante a calibração (spec §6.3).

Uso:
    python -m evaluation.retrieval.run_retrieval_eval --label L0
    python -m evaluation.retrieval.run_retrieval_eval --label L2 --per-line
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from evaluation.retrieval.gold import GoldLine, build_gold
from evaluation.retrieval.metrics import (
    RetrievalOutcome,
    context_precision_at_k,
    recall_at_k,
)
from evaluation.retrieval.norm_map import norm_keys_of_chunk
from rag_reviewer.config import get_settings
from rag_reviewer.embedder import Embedder
from rag_reviewer.vector_store import VectorStore

console = Console(highlight=False)

_ROOT = Path(__file__).parent.parent.parent
_DATASET = _ROOT / "evaluation" / "dataset" / "pilot_secao5.json"


def _retrieve_for_line(
    embedder: Embedder,
    store: VectorStore,
    line: str,
    top_k: int,
    score_threshold: float,
) -> list[dict]:
    """Recupera chunks para UMA linha (configurações L2 em diante)."""
    vector = embedder.embed_single(line).tolist()
    return store.search(
        query_vector=vector,
        top_k=top_k,
        score_threshold=score_threshold,
    )


def _retrieve_for_file(
    embedder: Embedder,
    store: VectorStore,
    lines: list[str],
    filename: str,
    top_k: int,
    score_threshold: float,
) -> list[dict]:
    """
    Recupera chunks para o ARQUIVO inteiro (comportamento L0/L1).

    Replica `build_query_text`: nome do arquivo + linhas adicionadas
    concatenadas. É a média semântica que a spec §3 identifica como causa
    dos scores comprimidos — preservada aqui para que L0 seja fiel.
    """
    query = f"Arquivo: {filename}\n" + "\n".join(lines)
    vector = embedder.embed_single(query).tolist()
    return store.search(
        query_vector=vector,
        top_k=top_k,
        score_threshold=score_threshold,
    )


def run_retrieval_eval(dataset_path: Path, label: str, per_line: bool) -> dict:
    """Executa a avaliação de retrieval e devolve o dicionário de resultados."""
    settings = get_settings()
    gold = build_gold(dataset_path)
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    embedder = Embedder()
    store = VectorStore()

    # Índice auxiliar: pr_id -> (filename, todas as linhas adicionadas)
    por_pr = {
        pr["pr_id"]: (pr["filename"], [al["line"] for al in pr["added_lines"]])
        for pr in dataset
    }

    # Cache por PR quando a consulta é por arquivo — a mesma consulta serve
    # todas as linhas positivas daquele PR.
    cache_arquivo: dict[str, list[dict]] = {}
    outcomes: list[RetrievalOutcome] = []

    for g in gold:
        filename, linhas = por_pr[g.pr_id]
        if per_line:
            chunks = _retrieve_for_line(
                embedder, store, g.line, settings.top_k_chunks, settings.score_threshold
            )
        else:
            if g.pr_id not in cache_arquivo:
                cache_arquivo[g.pr_id] = _retrieve_for_file(
                    embedder,
                    store,
                    linhas,
                    filename,
                    settings.top_k_chunks,
                    settings.score_threshold,
                )
            chunks = cache_arquivo[g.pr_id]

        outcomes.append(
            RetrievalOutcome(
                gold=g,
                ranked_norm_keys=[norm_keys_of_chunk(c["text"]) for c in chunks],
            )
        )

    resultado = {
        "label": label,
        "config": {
            "per_line": per_line,
            "embedding_model": settings.embedding_model,
            "top_k": settings.top_k_chunks,
            "score_threshold": settings.score_threshold,
            "collection": settings.qdrant_collection,
        },
        "n_gold_lines": len(gold),
        "recall_at_1": round(recall_at_k(outcomes, 1), 4),
        "recall_at_3": round(recall_at_k(outcomes, 3), 4),
        "recall_at_5": round(recall_at_k(outcomes, 5), 4),
        "context_precision_at_5": round(context_precision_at_k(outcomes, 5), 4),
    }
    return resultado


def _print_result(r: dict) -> None:
    table = Table(title=f"Retrieval — {r['label']}", header_style="bold cyan")
    table.add_column("Métrica")
    table.add_column("Valor", justify="right")
    for chave in (
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "context_precision_at_5",
    ):
        table.add_row(chave, f"{r[chave]:.4f}")
    console.print(table)

    meta = r["recall_at_5"] >= 0.95
    icone = "[OK]" if meta else "[FAIL]"
    cor = "green" if meta else "red"
    console.print(f"  {icone} [{cor}]Critério: recall@5 >= 0.95[/{cor}]\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Avalia a camada de recuperação.")
    parser.add_argument("--label", required=True, help="Rótulo da configuração (L0..L4).")
    parser.add_argument("--per-line", action="store_true", help="Consulta por linha.")
    parser.add_argument("--dataset", type=Path, default=_DATASET)
    args = parser.parse_args()

    r = run_retrieval_eval(args.dataset, args.label, args.per_line)
    _print_result(r)

    saida = Path(__file__).parent / f"results_{args.label}.json"
    saida.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[+] Resultado salvo em [bold]{saida}[/bold]\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add the Makefile target**

Adicione ao `Makefile`, na seção de Avaliação, e inclua `eval-retrieval` na linha `.PHONY`:

```makefile
eval-retrieval:
	$(PYTHON) -m evaluation.retrieval.run_retrieval_eval --label $(LABEL)
```

- [ ] **Step 3: Confirm the index reflects the CURRENT code**

O L0 só é fiel se a collection tiver sido construída pelo loader/chunker atuais.

Run: `.venv/Scripts/python.exe -m indexer.index_pipeline --docs-dir docs/style_guides --recreate`
Expected: conclui sem erro; anote o número de chunks inseridos.

- [ ] **Step 4: Measure and freeze L0**

Run: `.venv/Scripts/python.exe -m evaluation.retrieval.run_retrieval_eval --label L0`
Expected: `results_L0.json` criado. `recall@5` deve vir **baixo** — a evidência da spec §1.1 prevê que a Seção 5 não é recuperada para violações booleanas. Um `recall@5` alto aqui contradiz a evidência: pare e investigue o `norm_map` antes de prosseguir.

- [ ] **Step 5: Commit**

```bash
git add evaluation/retrieval/run_retrieval_eval.py evaluation/retrieval/results_L0.json Makefile
git commit -m "feat(eval): harness de retrieval e linha de base L0 congelada"
```

---

## Task 4: Loader ciente de blocos cercados

A correção da causa raiz (spec §4.1.1).

**Files:**
- Modify: `indexer/document_loader.py` — método `_load_markdown`
- Test: `tests/unit/test_document_loader.py`

**Interfaces:**
- Consumes: nada novo.
- Produces: `DocumentLoader.load()` deixa de emitir seções fantasma. Assinatura inalterada.

- [ ] **Step 1: Write the failing test**

```python
# acrescente a tests/unit/test_document_loader.py
def test_comentario_dentro_de_bloco_cercado_nao_vira_secao(tmp_path):
    """
    Regressão nomeada: `# Correto` dentro de ```python é comentário Python,
    não cabeçalho Markdown. Tratá-lo como cabeçalho arrancava os exemplos da
    norma a que pertencem — a causa raiz dos chunks-lixo.
    """
    md = tmp_path / "guia.md"
    md.write_text(
        "## 2.3 Nomenclatura de Funções Booleanas\n"
        "\n"
        "Funções booleanas devem começar com `is_`.\n"
        "\n"
        "```python\n"
        "# Correto\n"
        "def is_active(user) -> bool: ...\n"
        "\n"
        "# Incorreto\n"
        "def active(user): ...\n"
        "```\n",
        encoding="utf-8",
    )

    docs = DocumentLoader().load(md)
    secoes = [d.section for d in docs]

    assert "Correto" not in secoes
    assert "Incorreto" not in secoes
    assert secoes == ["2.3 Nomenclatura de Funções Booleanas"]


def test_exemplos_permanecem_na_secao_da_norma(tmp_path):
    """A norma e seus dois exemplos precisam sair no MESMO Document."""
    md = tmp_path / "guia.md"
    md.write_text(
        "## 5. Comparações\n"
        "\n"
        "Não compare booleanos com == True.\n"
        "\n"
        "```python\n"
        "# Correto\n"
        "if is_valid:\n"
        "# Incorreto\n"
        "if is_valid == True:\n"
        "```\n",
        encoding="utf-8",
    )

    docs = DocumentLoader().load(md)

    assert len(docs) == 1
    texto = docs[0].text
    assert "if is_valid:" in texto
    assert "if is_valid == True:" in texto
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_document_loader.py -k "cercado or exemplos_permanecem" -v`
Expected: FAIL — `assert 'Correto' not in ['5. Comparações', 'Correto', 'Incorreto']`

- [ ] **Step 3: Implement fence awareness**

Em `indexer/document_loader.py`, adicione o utilitário e troque a construção de `matches` dentro de `_load_markdown`:

```python
def _fenced_spans(raw: str) -> list[tuple[int, int]]:
    """
    Devolve os intervalos [início, fim) ocupados por blocos de código cercados.

    Cercas são linhas que começam com ``` ou ~~~ (com indentação opcional).
    Uma cerca de abertura sem fechamento estende-se até o fim do arquivo —
    tratar assim é conservador: prefere-se ignorar cabeçalhos reais a
    fabricar seções fantasma a partir de comentários de código.
    """
    spans: list[tuple[int, int]] = []
    abertura: int | None = None

    for m in re.finditer(r"^[ \t]*(```|~~~)", raw, re.MULTILINE):
        if abertura is None:
            abertura = m.start()
        else:
            fim = raw.find("\n", m.end())
            spans.append((abertura, len(raw) if fim == -1 else fim + 1))
            abertura = None

    if abertura is not None:
        spans.append((abertura, len(raw)))

    return spans
```

Depois, em `_load_markdown`, substitua:

```python
matches = list(pattern.finditer(raw))
```

por:

```python
spans = _fenced_spans(raw)
matches = [
    m
    for m in pattern.finditer(raw)
    if not any(inicio <= m.start() < fim for inicio, fim in spans)
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_document_loader.py -v`
Expected: PASS — todos, inclusive os testes pré-existentes.

- [ ] **Step 5: Verify the junk sections are gone from the real corpus**

Run:
```bash
.venv/Scripts/python.exe -c "
import sys; sys.stdout.reconfigure(encoding='utf-8')
from indexer.document_loader import DocumentLoader
docs = DocumentLoader().load_directory('docs/style_guides')
lixo = [d.section for d in docs
        if d.section.lower().startswith(('correto','incorreto'))
        or d.section in ('1. Stdlib','2. Terceiros','3. Internos')]
print('total de secoes:', len(docs))
print('secoes fantasma:', lixo)
assert not lixo, 'ainda ha secoes fantasma'
print('OK')
"
```
Expected: `secoes fantasma: []` e `OK`. Antes da correção havia 9 no `coding_standards.md`.

- [ ] **Step 6: Commit**

```bash
git add indexer/document_loader.py tests/unit/test_document_loader.py
git commit -m "fix(indexer): loader ignora cabecalhos falsos dentro de blocos cercados"
```

---

## Task 5: Chunker preserva a unidade normativa

Com o loader corrigido, cada `Document` já é uma unidade normativa coerente. O chunker atual pode voltar a quebrá-la por tamanho — inclusive no meio de um bloco de código.

**Files:**
- Modify: `indexer/chunker.py`
- Test: `tests/unit/test_chunker.py`

**Interfaces:**
- Consumes: `Document` do loader.
- Produces: `RecursiveChunker.split(documents) -> list[Chunk]` — assinatura inalterada; ganha a garantia de não partir blocos cercados.

- [ ] **Step 1: Write the failing test**

```python
# acrescente a tests/unit/test_chunker.py
from indexer.document_loader import Document
from indexer.chunker import RecursiveChunker


def _conta_cercas(texto: str) -> int:
    return sum(1 for linha in texto.splitlines() if linha.strip().startswith("```"))


def test_bloco_cercado_nunca_e_partido_entre_chunks():
    """
    Um bloco de código partido ao meio perde o par Correto/Incorreto, que é
    justamente o que dá +42% de margem de discriminação (spec §1.3).
    """
    corpo = "Texto normativo. " * 400  # força a divisão por tamanho
    doc = Document(
        text=(
            "5. Comparações\n\n"
            + corpo
            + "\n\n```python\n# Correto\nif is_valid:\n# Incorreto\nif is_valid == True:\n```\n"
        ),
        source="guia.md",
        section="5. Comparações",
    )

    chunks = RecursiveChunker(chunk_size=100, chunk_overlap=10).split([doc])

    assert len(chunks) > 1, "o teste precisa de um documento que realmente divida"
    for c in chunks:
        assert _conta_cercas(c.text) % 2 == 0, (
            f"chunk com cerca desemparelhada:\n{c.text}"
        )


def test_documento_pequeno_vira_um_unico_chunk():
    doc = Document(
        text="5. Comparações\n\nNão compare booleanos com == True.\n\n"
        "```python\nif is_valid:\n```",
        source="guia.md",
        section="5. Comparações",
    )
    chunks = RecursiveChunker(chunk_size=512, chunk_overlap=64).split([doc])
    assert len(chunks) == 1
    assert "if is_valid:" in chunks[0].text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_chunker.py -k "cercado or pequeno" -v`
Expected: FAIL em `test_bloco_cercado_nunca_e_partido_entre_chunks` — cerca desemparelhada.

- [ ] **Step 3: Implement fence-atomic splitting**

Em `indexer/chunker.py`, adicione o método e chame-o no início de `_split_text`:

```python
    _FENCE = re.compile(r"^[ \t]*(```|~~~)", re.MULTILINE)

    def _protect_fences(self, text: str) -> list[str]:
        """
        Fatia o texto em segmentos alternando prosa e blocos cercados inteiros.

        Blocos cercados são ATÔMICOS: nunca são divididos. Um bloco partido
        ao meio separa o exemplo Correto do Incorreto, destruindo o par que
        dá ao chunk sua capacidade de casar com código (spec §1.3).
        """
        marcas = [m.start() for m in self._FENCE.finditer(text)]
        if len(marcas) < 2:
            return [text]

        segmentos: list[str] = []
        cursor = 0
        # Consome as marcas aos pares: abertura e fechamento.
        for i in range(0, len(marcas) - 1, 2):
            inicio, fim_marca = marcas[i], marcas[i + 1]
            fim_linha = text.find("\n", fim_marca)
            fim = len(text) if fim_linha == -1 else fim_linha + 1

            if inicio > cursor:
                segmentos.append(text[cursor:inicio])
            segmentos.append(text[inicio:fim])
            cursor = fim

        if cursor < len(text):
            segmentos.append(text[cursor:])

        return [s for s in segmentos if s.strip()]
```

E no início de `_split_text`, antes de qualquer outra coisa:

```python
    def _split_text(self, text: str) -> list[str]:
        if self._len(text) <= self.chunk_size:
            stripped = text.strip()
            return [stripped] if stripped else []

        segmentos = self._protect_fences(text)
        if len(segmentos) > 1:
            # Trata cada bloco cercado como unidade indivisível e só divide a prosa.
            resultado: list[str] = []
            for seg in segmentos:
                if self._FENCE.search(seg):
                    resultado.append(seg.strip())
                else:
                    resultado.extend(self._split_text(seg))
            return [r for r in resultado if r]

        for separator in self._SEPARATORS:
            if separator in text:
                parts = text.split(separator)
                return self._merge_splits(parts, separator)

        return self._hard_split(text)
```

Adicione `import re` no topo do arquivo se ainda não existir.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_chunker.py -v`
Expected: PASS — todos, inclusive os pré-existentes.

- [ ] **Step 5: Re-index and measure L1**

```bash
.venv/Scripts/python.exe -m indexer.index_pipeline --docs-dir docs/style_guides --recreate
.venv/Scripts/python.exe -m evaluation.retrieval.run_retrieval_eval --label L1
```
Expected: `results_L1.json` criado. Compare com o L0 — a expectativa é melhora, mas **registre o número real, seja ele qual for**. Um ganho nulo aqui é informação legítima e deve ir para a tabela de ablação.

- [ ] **Step 6: Commit**

```bash
git add indexer/chunker.py tests/unit/test_chunker.py evaluation/retrieval/results_L1.json
git commit -m "fix(indexer): blocos cercados sao atomicos no chunking (L1)"
```

---

## Task 6: Guarda de divergência de modelo

Antes de trocar o modelo, é preciso impedir o modo de falha silencioso da spec §8.1: os candidatos multilíngues também têm **384 dimensões**, então o Qdrant aceitaria buscar vetores novos contra chunks antigos sem reclamar.

**Files:**
- Modify: `rag_reviewer/vector_store.py`
- Test: `tests/unit/test_vector_store_guard.py` (criar)

**Interfaces:**
- Consumes: nada novo.
- Produces:
  - `VectorStore.recreate_collection(vector_size: int, embedding_model: str) -> None`
  - `VectorStore.assert_model_matches(embedding_model: str) -> None` — levanta `RuntimeError` em divergência.
  - Payload de cada ponto ganha a chave `embedding_model`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_vector_store_guard.py
import pytest

from rag_reviewer.vector_store import VectorStore


class _FakeClient:
    def __init__(self, modelo_no_indice: str | None):
        self._modelo = modelo_no_indice

    def scroll(self, collection_name, limit, with_payload):
        if self._modelo is None:
            return [], None
        ponto = type("P", (), {"payload": {"embedding_model": self._modelo}})()
        return [ponto], None


def _store_com(modelo_no_indice):
    store = VectorStore(collection_name="teste")
    store._client = _FakeClient(modelo_no_indice)
    return store


def test_modelo_igual_nao_levanta():
    _store_com("all-MiniLM-L6-v2").assert_model_matches("all-MiniLM-L6-v2")


def test_modelo_divergente_levanta_com_instrucao():
    store = _store_com("all-MiniLM-L6-v2")
    with pytest.raises(RuntimeError) as exc:
        store.assert_model_matches("paraphrase-multilingual-MiniLM-L12-v2")
    assert "index-recreate" in str(exc.value)


def test_indice_vazio_levanta():
    store = _store_com(None)
    with pytest.raises(RuntimeError):
        store.assert_model_matches("qualquer-modelo")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_vector_store_guard.py -v`
Expected: FAIL — `AttributeError: 'VectorStore' object has no attribute 'assert_model_matches'`

- [ ] **Step 3: Implement the guard**

Em `rag_reviewer/vector_store.py`:

```python
    def assert_model_matches(self, embedding_model: str) -> None:
        """
        Falha alto se a collection foi indexada com outro modelo de embedding.

        Os modelos multilíngues candidatos também têm 384 dimensões, então o
        Qdrant ACEITARIA a busca sem reclamar: vetores de consulta do modelo
        novo contra vetores de chunk do modelo antigo. O resultado seria lixo
        silencioso, indistinguível de retrieval ruim (spec §8.1).
        """
        client = self._get_client()
        pontos, _ = client.scroll(
            collection_name=self._collection, limit=1, with_payload=True
        )

        if not pontos:
            raise RuntimeError(
                f"Coleção '{self._collection}' está vazia. "
                f"Execute: make index-recreate"
            )

        indexado = (pontos[0].payload or {}).get("embedding_model")
        if indexado != embedding_model:
            raise RuntimeError(
                f"Divergência de modelo de embedding.\n"
                f"  Indexado na coleção : {indexado!r}\n"
                f"  Configurado agora   : {embedding_model!r}\n"
                f"Buscar com modelos diferentes produz lixo silencioso.\n"
                f"Execute: make index-recreate"
            )
```

A guarda só funciona se o modelo for **gravado** na indexação. Três mudanças pequenas:

```python
# rag_reviewer/vector_store.py — assinatura de recreate_collection
    def recreate_collection(self, vector_size: int, embedding_model: str) -> None:
        ...  # corpo atual inalterado; apenas registre o modelo no log final
        console.log(
            f"[green]✅ Coleção '{self._collection}' criada "
            f"(dim={vector_size}, modelo={embedding_model}).[/green]"
        )

# rag_reviewer/vector_store.py — dentro de upsert, no dict de payload
    def upsert(self, chunks: list, embeddings, embedding_model: str) -> None:
        ...
            payload = {
                "text": chunk.text,
                "source": chunk.source,
                "section": chunk.section,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "char_count": len(chunk.text),
                "indexed_at": chunk.indexed_at,
                "embedding_model": embedding_model,   # <- a chave que a guarda lê
            }
```

```python
# indexer/index_pipeline.py — nas duas chamadas, dentro de run_indexing
store.recreate_collection(
    vector_size=embedder.vector_size,
    embedding_model=embedder.model_name,
)
store.upsert(chunks, embeddings, embedding_model=embedder.model_name)
```

> A Task 9 volta a alterar estas duas assinaturas para acomodar os vetores esparsos. Isso é esperado: cada tarefa entrega uma mudança testável, e a evolução incremental da assinatura é preferível a antecipar aqui uma estrutura que ainda não tem consumidor.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_vector_store_guard.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Wire the guard into the retrieval path**

Chame `assert_model_matches(settings.embedding_model)` na inicialização do `Retriever` e no início de `run_retrieval_eval`. Reindexe e confirme que tudo continua passando.

Run: `.venv/Scripts/python.exe -m indexer.index_pipeline --docs-dir docs/style_guides --recreate`
Then: `.venv/Scripts/python.exe -m evaluation.retrieval.run_retrieval_eval --label L1`
Expected: mesmas métricas do L1 anterior; a guarda não muda resultado, só protege.

- [ ] **Step 6: Commit**

```bash
git add rag_reviewer/vector_store.py indexer/index_pipeline.py rag_reviewer/retriever.py tests/unit/test_vector_store_guard.py
git commit -m "feat(rag): guarda contra divergencia de modelo de embedding"
```

---

## Task 7: Consulta por linha (L2)

Alinha a unidade de recuperação à unidade de avaliação de D-001.

**Files:**
- Modify: `rag_reviewer/retriever.py`
- Test: `tests/unit/test_retriever.py`

**Interfaces:**
- Consumes: `Embedder.embed`, `VectorStore.search`.
- Produces: `Retriever._retrieve_for_file` passa a consultar por linha e unir; `RetrievedContext.query_text` passa a conter as linhas consultadas, uma por linha. Novo parâmetro `max_chunks: int | None` no construtor (o `N` da spec §4.3).

- [ ] **Step 1: Write the failing test**

```python
# acrescente a tests/unit/test_retriever.py
def test_consulta_uma_vez_por_linha_adicionada():
    """
    D-001 define a linha como unidade de avaliação. Consultar por arquivo
    produz uma média semântica que não representa nenhuma das linhas.
    """
    file_diff = FileDiff(
        filename="a.py",
        patch="",
        status="modified",
        additions=3,
        deletions=0,
        added_lines=["if x == True:", "y = 1", "if z != None:"],
    )
    embedder = FakeEmbedder()   # registra cada texto recebido
    store = FakeStore(chunks=[_chunk("norma")])

    Retriever(embedder=embedder, store=store).retrieve_for_file(file_diff)

    assert embedder.textos_recebidos == [
        "if x == True:",
        "y = 1",
        "if z != None:",
    ]


def test_chunks_repetidos_entre_linhas_sao_deduplicados():
    file_diff = FileDiff(
        filename="a.py", patch="", status="modified",
        additions=2, deletions=0,
        added_lines=["if x == True:", "if y == False:"],
    )
    mesmo = _chunk("mesma norma")
    store = FakeStore(chunks=[mesmo])   # devolve o mesmo chunk para toda linha

    ctx = Retriever(embedder=FakeEmbedder(), store=store).retrieve_for_file(file_diff)

    assert len(ctx.chunks) == 1


def test_uniao_e_limitada_por_max_chunks():
    file_diff = FileDiff(
        filename="a.py", patch="", status="modified",
        additions=2, deletions=0,
        added_lines=["linha um", "linha dois"],
    )
    store = FakeStore(chunks=[_chunk(f"norma {i}") for i in range(5)])

    ctx = Retriever(
        embedder=FakeEmbedder(), store=store, max_chunks=3
    ).retrieve_for_file(file_diff)

    assert len(ctx.chunks) == 3


def test_arquivo_sem_nenhum_chunk_retorna_none():
    """Resultado legítimo, não erro (spec §8.3)."""
    file_diff = FileDiff(
        filename="a.py", patch="", status="modified",
        additions=1, deletions=0, added_lines=["y = 1"],
    )
    ctx = Retriever(
        embedder=FakeEmbedder(), store=FakeStore(chunks=[])
    ).retrieve_for_file(file_diff)

    assert ctx is None
```

Reaproveite os fakes já existentes em `tests/unit/test_retriever.py`; se não houver `FakeEmbedder` que registre os textos, acrescente o atributo `textos_recebidos: list[str]`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_retriever.py -k "por_linha or deduplicados or max_chunks" -v`
Expected: FAIL — o embedder recebe um único texto concatenado, não três.

- [ ] **Step 3: Implement per-line retrieval**

Substitua `_retrieve_for_file` em `rag_reviewer/retriever.py`:

```python
    def _retrieve_for_file(self, file_diff: FileDiff) -> RetrievedContext | None:
        """
        Consulta o Qdrant uma vez POR LINHA ADICIONADA e une os resultados.

        A unidade de recuperação é a linha, igual à unidade de avaliação de
        D-001. Consultar por arquivo concatenava linhas heterogêneas numa
        média semântica que não representava nenhuma delas — a causa dos
        scores comprimidos entre 0.3 e 0.5 (spec §3).

        A granularidade da chamada ao LLM NÃO muda: continua uma por arquivo,
        sobre a união deduplicada.
        """
        linhas = file_diff.added_lines
        console.log(
            f"[dim]Retriever:[/dim] buscando normas para "
            f"[bold]{file_diff.filename}[/bold] ({len(linhas)} linha(s))..."
        )

        vistos: set[tuple[str, str]] = set()
        unidos: list[dict] = []

        for linha in linhas:
            vetor = self._embedder.embed([linha])[0].tolist()
            for chunk in self._store.search(
                query_vector=vetor,
                top_k=self._top_k,
                score_threshold=self._score_threshold,
            ):
                chave = (chunk["source"], chunk["section"])
                if chave in vistos:
                    continue
                vistos.add(chave)
                unidos.append(chunk)

        if not unidos:
            console.log(
                f"[dim]Retriever:[/dim] nenhum chunk relevante para "
                f"[bold]{file_diff.filename}[/bold]."
            )
            return None

        # Maior score primeiro, depois corta em max_chunks (o N da spec §4.3):
        # contexto excedente comprovadamente induz alucinação.
        unidos.sort(key=lambda c: c["score"], reverse=True)
        if self._max_chunks is not None:
            unidos = unidos[: self._max_chunks]

        console.log(
            f"[dim]Retriever:[/dim] {len(unidos)} chunk(s) para "
            f"[bold]{file_diff.filename}[/bold] "
            f"(top score: {unidos[0]['score']:.3f})."
        )

        return RetrievedContext(
            file_diff=file_diff,
            chunks=unidos,
            query_text="\n".join(linhas),
        )
```

Acrescente `max_chunks: int | None = None` ao `__init__`, guardando em `self._max_chunks` (default vindo de `get_settings()` se você adicionar a configuração; caso contrário, `8`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_retriever.py -v`
Expected: PASS. Testes antigos que assumiam consulta por arquivo precisarão ser atualizados — atualize-os, não os delete.

- [ ] **Step 5: Measure L2**

Run: `.venv/Scripts/python.exe -m evaluation.retrieval.run_retrieval_eval --label L2 --per-line`
Expected: `results_L2.json`. Registre o valor real.

- [ ] **Step 6: Commit**

```bash
git add rag_reviewer/retriever.py tests/unit/test_retriever.py evaluation/retrieval/results_L2.json
git commit -m "feat(rag): recuperacao por linha alinhada a D-001 (L2)"
```

---

## Task 8: Modelo de embedding multilíngue (L3)

Ataca a causa raiz medida: PT↔EN = 0.597 num par de traduções literais (spec §1.2).

**Files:**
- Modify: `rag_reviewer/config.py`, `.env.example`, `.env`
- Modify: `rag_reviewer/embedder.py` (apenas se o modelo escolhido exigir prefixos)
- Test: `tests/unit/test_embedder.py`

**Interfaces:**
- Consumes: guarda da Task 6.
- Produces: default de `embedding_model` passa a ser o modelo multilíngue.

- [ ] **Step 1: Escolher o modelo com medição, não por intuição**

Run:
```bash
.venv/Scripts/python.exe -c "
import sys, numpy as np; sys.stdout.reconfigure(encoding='utf-8')
from sentence_transformers import SentenceTransformer
def cos(a,b): return float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))
pt='Comparações booleanas: Não compare valores booleanos com == True ou == False.'
en='Boolean comparisons: Do not compare boolean values with == True or == False.'
alvo='if user.is_admin == True:'
distr='1.1 Tamanho Máximo de Linha: o limite é de 79 caracteres.'
for nome in ['sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
             'intfloat/multilingual-e5-small']:
    m=SentenceTransformer(nome); V=m.encode([pt,en,alvo,distr])
    print(nome)
    print('   PT<->EN (deveria ser ~0.95):', round(cos(V[0],V[1]),3))
    print('   norma<->violacao           :', round(cos(V[0],V[2]),3))
    print('   margem sobre distrator     :', round(cos(V[0],V[2])-cos(V[3],V[2]),3))
"
```

Escolha o modelo com **maior margem sobre distrator**. Registre ambos os números no relatório — é o dado que justifica o ADR-002 reescrito.

- [ ] **Step 2: Write the failing test**

```python
# acrescente a tests/unit/test_embedder.py
def test_modelo_default_e_multilingue():
    """
    O corpus normativo é integralmente em português. Um modelo treinado em
    inglês dá 0.597 entre traduções literais, quando o esperado é ~0.95
    (spec §1.2).
    """
    from rag_reviewer.config import Settings

    modelo = Settings().embedding_model
    assert "multilingual" in modelo, (
        f"modelo {modelo!r} nao e multilingue; o corpus e em portugues"
    )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_embedder.py -k multilingue -v`
Expected: FAIL — `modelo 'all-MiniLM-L6-v2' nao e multilingue`

- [ ] **Step 4: Change the default**

Em `rag_reviewer/config.py`, troque o default de `embedding_model` pelo modelo vencedor do Step 1. Atualize `.env.example` e o `.env` local.

> Se o vencedor for da família **e5**, os prefixos `"query: "` e `"passage: "` são obrigatórios: consultas recebem `query: `, chunks indexados recebem `passage: `. Omiti-los degrada a qualidade em silêncio. Implemente em `Embedder` com um método `embed_query` distinto de `embed`, e escreva um teste que verifique o prefixo aplicado.

- [ ] **Step 5: Run test and re-index**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_embedder.py -v`
Expected: PASS

Then: `.venv/Scripts/python.exe -m indexer.index_pipeline --docs-dir docs/style_guides --recreate`
Expected: conclui sem erro. **Se você esquecer o `--recreate`, a guarda da Task 6 deve derrubar a próxima busca** — confirme que ela funciona rodando a avaliação sem reindexar antes.

- [ ] **Step 6: Measure L3**

Run: `.venv/Scripts/python.exe -m evaluation.retrieval.run_retrieval_eval --label L3 --per-line`
Expected: `results_L3.json`. Esta é a camada com maior expectativa de ganho.

- [ ] **Step 7: Commit**

```bash
git add rag_reviewer/config.py rag_reviewer/embedder.py .env.example tests/unit/test_embedder.py evaluation/retrieval/results_L3.json
git commit -m "feat(rag): modelo de embedding multilingue (L3)"
```

---

## Task 9: Busca híbrida densa + esparsa (L4)

A camada que responde diretamente à objeção de que embedding semântico é a ferramenta errada para casar `== True`, que é uma string literal.

**Files:**
- Create: `rag_reviewer/sparse_encoder.py`
- Modify: `rag_reviewer/vector_store.py`, `indexer/index_pipeline.py`, `requirements.txt`
- Test: `tests/unit/test_sparse_encoder.py`

**Interfaces:**
- Consumes: `Chunk.text`.
- Produces:
  - `SparseEncoder.encode(text: str) -> tuple[list[int], list[float]]` — (índices, valores)
  - `VectorStore.search_hybrid(dense: list[float], sparse: tuple[list[int], list[float]], top_k: int) -> list[dict]`

- [ ] **Step 1: Add the dependency**

Acrescente a `requirements.txt`:
```
fastembed>=0.4.0
```
Run: `.venv/Scripts/pip.exe install -r requirements.txt`

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_sparse_encoder.py
import pytest

from rag_reviewer.sparse_encoder import SparseEncoder


def test_tokens_identicos_produzem_indices_em_comum():
    """
    `== True` é uma string literal. O casamento lexical não depende de o
    modelo entender português nem Python — é o ponto da camada esparsa.
    """
    enc = SparseEncoder()
    idx_norma, _ = enc.encode("Não compare valores booleanos com == True ou == False.")
    idx_linha, _ = enc.encode("if user.is_admin == True:")

    assert set(idx_norma) & set(idx_linha), "nenhum token em comum"


def test_textos_sem_relacao_nao_compartilham_tokens_relevantes():
    enc = SparseEncoder()
    idx_a, _ = enc.encode("comparações booleanas com == True")
    idx_b, _ = enc.encode("tamanho máximo de linha 79 caracteres")

    assert len(set(idx_a) & set(idx_b)) < len(set(idx_a)) / 2


def test_encoder_indisponivel_falha_alto(monkeypatch):
    """
    Cair para 'só denso' mudaria em silêncio a configuração sob medição,
    invalidando a ablação (spec §8.2).
    """
    enc = SparseEncoder()
    monkeypatch.setattr(
        enc, "_ensure_model_loaded", lambda: (_ for _ in ()).throw(ImportError("boom"))
    )
    with pytest.raises(ImportError):
        enc.encode("qualquer texto")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_sparse_encoder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rag_reviewer.sparse_encoder'`

- [ ] **Step 4: Implement `SparseEncoder`**

```python
# rag_reviewer/sparse_encoder.py
"""
sparse_encoder.py — Vetores esparsos BM25 para a metade lexical da busca.

`== True` e `!= None` são padrões LEXICAIS: strings literais. Nenhum modelo
semântico deveria ser responsável por casar uma string exata — é a ferramenta
errada, e foi o que manteve todos os scores comprimidos entre 0.3 e 0.5
(spec §1.3). O casamento por token exato não depende de o modelo entender
português nem Python.
"""

from __future__ import annotations

from rich.console import Console

console = Console()

_MODEL_NAME = "Qdrant/bm25"


class SparseEncoder:
    """Gera vetores esparsos BM25 via fastembed, com carregamento preguiçoso."""

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        self._model_name = model_name
        self._model = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def encode(self, text: str) -> tuple[list[int], list[float]]:
        """
        Codifica um texto em (índices, valores) esparsos.

        Raises:
            ImportError: Se o fastembed não estiver instalado. NÃO há fallback
                para "só denso": isso mudaria em silêncio a configuração sob
                medição e invalidaria a ablação (spec §8.2).
        """
        self._ensure_model_loaded()
        emb = next(iter(self._model.embed([text])))  # type: ignore[union-attr]
        return [int(i) for i in emb.indices], [float(v) for v in emb.values]

    def encode_batch(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        """Versão em lote, usada na indexação."""
        self._ensure_model_loaded()
        return [
            ([int(i) for i in e.indices], [float(v) for v in e.values])
            for e in self._model.embed(texts)  # type: ignore[union-attr]
        ]

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from fastembed import SparseTextEmbedding  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "fastembed não está instalado e é obrigatório para a busca "
                "híbrida. Execute: pip install fastembed"
            ) from exc

        console.log(f"[cyan]SparseEncoder:[/cyan] carregando '{self._model_name}'...")
        self._model = SparseTextEmbedding(model_name=self._model_name)
```

- [ ] **Step 5: Store sparse vectors at index time**

Em `rag_reviewer/vector_store.py`, o vetor denso passa a ser **nomeado** (`"dense"`), porque a Query API precisa endereçar as duas modalidades por nome:

```python
    def recreate_collection(self, vector_size: int, embedding_model: str) -> None:
        from qdrant_client.models import (  # type: ignore
            Distance,
            HnswConfigDiff,
            SparseVectorParams,
            VectorParams,
        )

        client = self._get_client()
        existing = [c.name for c in client.get_collections().collections]
        if self._collection in existing:
            client.delete_collection(self._collection)

        client.create_collection(
            collection_name=self._collection,
            vectors_config={
                "dense": VectorParams(size=vector_size, distance=Distance.COSINE)
            },
            sparse_vectors_config={"bm25": SparseVectorParams()},
            hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
        )
        console.log(
            f"[green]✅ Coleção '{self._collection}' criada "
            f"(dim={vector_size}, modelo={embedding_model}).[/green]"
        )
```

E `upsert` grava as duas modalidades mais o modelo (a guarda da Task 6 lê essa chave):

```python
    def upsert(self, chunks: list, embeddings, sparse, embedding_model: str) -> None:
        from qdrant_client.models import PointStruct, SparseVector  # type: ignore

        client = self._get_client()
        points = []
        for chunk, vector, (idx, vals) in zip(chunks, embeddings, sparse):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        "dense": vector.tolist(),
                        "bm25": SparseVector(indices=idx, values=vals),
                    },
                    payload={
                        "text": chunk.text,
                        "source": chunk.source,
                        "section": chunk.section,
                        "page": chunk.page,
                        "chunk_index": chunk.chunk_index,
                        "char_count": len(chunk.text),
                        "indexed_at": chunk.indexed_at,
                        "embedding_model": embedding_model,
                    },
                )
            )

        for i in range(0, len(points), 100):
            client.upsert(collection_name=self._collection, points=points[i : i + 100])

        console.log(f"[green]✅ {len(points)} chunks inseridos no Qdrant.[/green]")
```

Em `indexer/index_pipeline.py`, instancie o `SparseEncoder`, gere `sparse = encoder.encode_batch([c.text for c in chunks])` e repasse `embedder.model_name` às duas chamadas.

- [ ] **Step 6: Implement `search` (dense named) and `search_hybrid` (RRF)**

O vetor denso virou nomeado, então `search` precisa endereçá-lo — sem isso, todo o caminho denso quebra:

```python
    def search(
        self, query_vector: list, top_k: int = 5, score_threshold: float = 0.55
    ) -> list[dict]:
        """Busca apenas densa. Mantida para as configurações L0–L3."""
        client = self._get_client()
        res = client.query_points(
            collection_name=self._collection,
            query=query_vector,
            using="dense",
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return [self._to_dict(p) for p in res.points]

    def search_hybrid(
        self,
        dense: list,
        sparse: tuple[list[int], list[float]],
        top_k: int = 5,
        prefetch_limit: int = 20,
    ) -> list[dict]:
        """
        Busca híbrida com fusão Reciprocal Rank Fusion.

        Após a fusão o score é POSTO, não cosseno — por isso o
        `score_threshold` absoluto não se aplica aqui e foi removido do
        caminho híbrido (spec §4.4). O corte passa a ser `top_k`, calibrado
        contra o gabarito.
        """
        from qdrant_client import models  # type: ignore

        client = self._get_client()
        indices, values = sparse
        res = client.query_points(
            collection_name=self._collection,
            prefetch=[
                models.Prefetch(query=dense, using="dense", limit=prefetch_limit),
                models.Prefetch(
                    query=models.SparseVector(indices=indices, values=values),
                    using="bm25",
                    limit=prefetch_limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        return [self._to_dict(p) for p in res.points]

    @staticmethod
    def _to_dict(point) -> dict:
        return {
            "text": point.payload["text"],
            "source": point.payload["source"],
            "section": point.payload.get("section", ""),
            "page": point.payload.get("page", 0),
            "score": point.score,
        }
```

- [ ] **Step 7: Wire hybrid into the retriever AND the harness**

Sem este passo o L4 **não mede nada de novo**: o harness continuaria chamando `search`, e a fusão RRF nunca entraria no caminho.

- `Retriever.__init__` ganha `sparse_encoder: SparseEncoder | None = None` e `hybrid: bool = True`; quando ativo, o laço por linha chama `search_hybrid(dense, sparse_encoder.encode(linha), top_k)`.
- `run_retrieval_eval` ganha a flag `--hybrid`, que ativa o mesmo caminho.

- [ ] **Step 8: Run tests, re-index and measure L4**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
.venv/Scripts/python.exe -m indexer.index_pipeline --docs-dir docs/style_guides --recreate
.venv/Scripts/python.exe -m evaluation.retrieval.run_retrieval_eval --label L4 --per-line --hybrid
```
Expected: `results_L4.json`, com `config.hybrid: true` registrado. **Confirme esse campo** — é a prova de que a camada foi de fato exercitada.

- [ ] **Step 9: Commit**

```bash
git add rag_reviewer/sparse_encoder.py rag_reviewer/vector_store.py rag_reviewer/retriever.py indexer/index_pipeline.py evaluation/retrieval/run_retrieval_eval.py requirements.txt tests/unit/test_sparse_encoder.py evaluation/retrieval/results_L4.json
git commit -m "feat(rag): busca hibrida densa+esparsa com fusao RRF (L4)"
```

---

## Task 10: Tabela de ablação e teste de remoção

**Files:**
- Create: `evaluation/retrieval/ablation.py`
- Create: `docs/agent-reports/2026-09-01-ablacao-retrieval.md`

- [ ] **Step 1: Build the consolidation script**

```python
# evaluation/retrieval/ablation.py
"""
ablation.py — Consolida os resultados das configurações L0..L4.

Lê os `results_<label>.json` produzidos por `run_retrieval_eval` e monta a
tabela de ablação: o valor de cada métrica por configuração e o ganho
incremental de cada camada sobre a anterior.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console(highlight=False)

_AQUI = Path(__file__).parent
_ORDEM = ["L0", "L1", "L2", "L3", "L4"]
_METRICAS = ["recall_at_1", "recall_at_3", "recall_at_5", "context_precision_at_5"]


def carregar() -> list[dict]:
    """Carrega os resultados existentes, na ordem canônica das camadas."""
    resultados = []
    for label in _ORDEM:
        caminho = _AQUI / f"results_{label}.json"
        if caminho.exists():
            resultados.append(json.loads(caminho.read_text(encoding="utf-8")))
        else:
            console.print(f"[yellow]aviso:[/yellow] {caminho.name} ausente — pulando.")
    return resultados


def main() -> None:
    resultados = carregar()
    if not resultados:
        console.print("[red]Nenhum resultado encontrado.[/red]")
        return

    tabela = Table(title="Ablação da camada de RAG", header_style="bold cyan")
    tabela.add_column("Config", style="bold")
    for m in _METRICAS:
        tabela.add_column(m, justify="right")
    tabela.add_column("Δ recall@5", justify="right")

    anterior = None
    for r in resultados:
        if anterior is None:
            delta = "—"
        else:
            d = r["recall_at_5"] - anterior
            delta = f"[green]+{d:.4f}[/green]" if d > 0 else f"[red]{d:.4f}[/red]"
        tabela.add_row(
            r["label"], *[f"{r[m]:.4f}" for m in _METRICAS], delta
        )
        anterior = r["recall_at_5"]

    console.print(tabela)

    melhor = max(resultados, key=lambda r: r["recall_at_5"])
    atingiu = melhor["recall_at_5"] >= 0.95
    icone = "[OK]" if atingiu else "[FAIL]"
    cor = "green" if atingiu else "red"
    console.print(
        f"\n  {icone} [{cor}]Melhor: {melhor['label']} com "
        f"recall@5 = {melhor['recall_at_5']:.4f} (critério: >= 0.95)[/{cor}]\n"
    )


if __name__ == "__main__":
    main()
```

Run: `.venv/Scripts/python.exe -m evaluation.retrieval.ablation`

- [ ] **Step 2: Run the correct counterfactual**

⚠️ **Cuidado com um contrafactual inútil.** Numa ablação cumulativa, "L4 sem a camada esparsa" **é exatamente o L3** — a comparação L4 vs L3 da tabela já mede isso. Rodar essa configuração de novo não produz informação nova.

O contrafactual que informa é o **leave-one-out do meio da pilha**: busca híbrida **sem** o modelo multilíngue (L4 com o `all-MiniLM-L6-v2` de volta). Ele responde a pergunta que a tabela cumulativa não responde: *o casamento lexical exato torna a troca de modelo dispensável?*

Isso importa porque o modelo multilíngue é a camada mais cara em produção — 470MB baixados a cada execução do Actions (spec §10.1). Se a híbrida sozinha entregar o mesmo recall, o custo de CI cai por cinco.

```bash
# LLM_MODEL não muda; só o modelo de EMBEDDING volta ao antigo
EMBEDDING_MODEL=all-MiniLM-L6-v2 .venv/Scripts/python.exe -m indexer.index_pipeline --docs-dir docs/style_guides --recreate
EMBEDDING_MODEL=all-MiniLM-L6-v2 .venv/Scripts/python.exe -m evaluation.retrieval.run_retrieval_eval --label L4_sem_multilingue --per-line --hybrid
```

Ao terminar, **reindexe de volta com o modelo multilíngue** — senão a Task 13 roda contra um índice errado, e a guarda da Task 6 vai (corretamente) derrubá-la.

- [ ] **Step 3: Check the success criterion**

`recall@5 >= 0.95` na configuração vencedora (spec §2).

Se não for atingido mesmo com todas as camadas: **não baixe a barra e não reduza o corpus** (D-007). Documente o valor atingido, o que foi tentado, e escale a decisão ao autor.

- [ ] **Step 4: Write the report and commit**

```bash
git add evaluation/retrieval/ablation.py docs/agent-reports/2026-09-01-ablacao-retrieval.md evaluation/retrieval/results_L4_sem_esparso.json
git commit -m "docs: tabela de ablacao do retrieval e teste de remocao"
```

---

## Task 11: Corrigir o regex de citação e cobrir `evaluation/`

**Files:**
- Modify: `evaluation/metrics.py` (`_SECTION_5_PATTERN`)
- Test: `tests/unit/test_metrics.py` (criar)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_metrics.py
from evaluation.metrics import _SECTION_5_PATTERN


def test_regex_casa_o_nome_de_secao_que_o_corpus_realmente_usa():
    """
    O corpus rotula a norma como "5. Práticas de Código e Idiomas Pythonicos",
    sem a palavra "Seção". O regex antigo exigia "Seção 5" e portanto NUNCA
    casaria uma citação correta — norm_reference_precision saía 0.0 por bug,
    não por desempenho.
    """
    assert _SECTION_5_PATTERN.search(
        "guia_python_pep8.md | Seção: 5. Práticas de Código e Idiomas Pythonicos"
    )
    assert _SECTION_5_PATTERN.search("guia_python_pep8.md — Seção 5")


def test_regex_nao_casa_outras_secoes():
    assert not _SECTION_5_PATTERN.search("guia_python_pep8.md | Seção: 1.1 Tamanho Máximo")
    assert not _SECTION_5_PATTERN.search("coding_standards.md | Seção: Correto")
    assert not _SECTION_5_PATTERN.search("guia_python_pep8.md | Seção: 5.1 Docstrings")
```

Nota: `5.1 Docstrings` pertence a outro documento e **não** deve casar — o regex precisa distinguir `5.` de `5.1`.

- [ ] **Step 2: Run, fix the regex, run again**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_metrics.py -v`
Corrija `_SECTION_5_PATTERN` até passar. Confirme o nome real da seção após a Task 4 rodando o comando de auditoria da Task 1, Step 5.

- [ ] **Step 3: Cover the rest of `evaluation/metrics.py`**

Hoje é o único módulo sem cobertura, e é o que produz os números do TCC. Cubra no mínimo: a invariante `TP+FP+FN+TN == N`, a normalização de D-003, a exclusão de alucinações da matriz, a deduplicação de detecções na mesma linha, e a agregação a nível de PR.

- [ ] **Step 4: Run the full suite and commit**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
git add evaluation/metrics.py tests/unit/test_metrics.py
git commit -m "fix(eval): regex de citacao normativa + cobertura de evaluation/"
```

---

## Task 12: ADRs e cache do workflow

**Files:**
- Rewrite: `docs/adr/ADR-002-embedding-model.md`, `docs/adr/ADR-003-llm-choice.md`
- Create: `docs/adr/ADR-004-hybrid-retrieval.md`
- Modify: `.github/workflows/rag_reviewer.yml`

- [ ] **Step 1: Rewrite ADR-002**

A justificativa atual não menciona idioma. Reescreva com o dado medido: PT↔EN = 0.597 entre traduções literais, e a comparação de margem entre os candidatos (Task 8, Step 1).

- [ ] **Step 2: Rewrite ADR-003**

`llama-3.3-70b-versatile` foi descomissionado — confirmado via `models.list()`, e não há **nenhum** Llama de propósito geral no catálogo da Groq. D-006 escolheu `qwen/qwen3.8-27b`. Registre também a rejeição explícita de `groq/compound*`: são agênticos com busca web embutida e destruiriam a validade interna do estudo.

- [ ] **Step 3: Write ADR-004**

Recuperação híbrida densa+esparsa com fusão RRF. Inclua os números reais do teste de remoção da Task 10 — se a camada não se justificou, o ADR deve dizer isso.

- [ ] **Step 4: Add the HuggingFace cache to CI**

O modelo salta de ~90MB para ~470MB, baixado a cada execução, contra um `timeout-minutes: 10`. Acrescente ao workflow, antes do passo de execução:

```yaml
      - name: Cache do modelo de embedding
        uses: actions/cache@v4
        with:
          path: ~/.cache/huggingface
          key: hf-${{ hashFiles('requirements.txt') }}
```

- [ ] **Step 5: Commit**

```bash
git add docs/adr/ .github/workflows/rag_reviewer.yml
git commit -m "docs: ADRs 002/003/004 e cache do modelo no CI"
```

---

## Task 13: Reexecutar a avaliação de detecção

Só agora, com `recall@5 >= 0.95` atingido, a métrica de detecção volta a medir o modelo em vez do encanamento.

- [ ] **Step 1: Confirm the gate**

Confirme em `results_L4.json` (ou na configuração vencedora) que `recall@5 >= 0.95`. **Se não atingiu, pare** — esta tarefa não deve rodar, e a decisão volta ao autor.

- [ ] **Step 2: Run the official detection evaluation**

Com `qwen/qwen3.8-27b` (D-006), temperatura 0.0 e 3 repetições (D-005):

Run: `.venv/Scripts/python.exe -m evaluation.run_evaluation --repeticoes 3`
Expected: `results.json` com média ± desvio-padrão e a matriz do F1 mediano.

- [ ] **Step 3: Commit**

```bash
git add evaluation/results.json
git commit -m "feat(eval): resultado oficial de deteccao apos refacao do retrieval"
```

---

## Pendência não resolvida por este plano

Os 30 patches do dataset são todos de arquivo novo (`@@ -0,0 +1,N @@`), sem linhas de contexto. A regra 4 do `system_prompt.txt` — "não comentar linhas não modificadas" — **não tem como ser exercitada**. Decisão pendente do autor: adicionar contexto pré-existente ao dataset, incluindo linhas de contexto que violam a regra e que o sistema deve ignorar por não terem sido modificadas.
