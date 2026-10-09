# Workflow do GitHub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um GitHub Action que, em cada PR, coleta o diff pela API, recupera normas da PEP 8, pede as violacoes ao LLM e publica uma review `COMMENT` com um comentario inline por violacao (norma, severidade, como corrigir).

**Architecture:** Portar para a `main` atual somente o que e workflow da `main-completa` (coleta do diff, publisher, orquestrador, entrada do Action, YAML do workflow e os testes desses modulos). Corpus, prompts, retriever, `llm_client`, `vector_store`, `config` e o restante ficam como estao na `main`. O orquestrador chama `Retriever.retrieve_for_diff`, que apenas aplica o `retrieve_for_file` da `main` a cada arquivo.

**Tech Stack:** Python 3.11, `requests` (API REST do GitHub), `groq`, `qdrant-client`, `sentence-transformers`, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-09-workflow-github-design.md`

## Global Constraints

- A `main` e a fonte principal. Da `main-completa` entram so: `rag_reviewer/diff_parser.py`, `rag_reviewer/github_publisher.py`, `rag_reviewer/reviewer.py`, `rag_reviewer/main.py`, `.github/workflows/rag_reviewer.yml`, `tests/unit/test_diff_parser.py`, `tests/unit/test_github_publisher.py`, `tests/integration/` e o alvo `test-integration` do `Makefile`. Nada mais: nem prompts, nem `retriever.py`, `llm_client.py`, `vector_store.py`, `config.py`, nem `requirements.txt` (exceto `requests`).
- Nao portar `PyGithub`, `tiktoken`, `max_diff_tokens`, pypdf, python-docx, markdown, beautifulsoup4.
- Severidades validas: `HIGH`, `MEDIUM`, `LOW`. `CRITICAL`, `block_on_critical` e `request_changes` deixam de existir.
- Toda review sai com `event: "COMMENT"`. O Action nunca bloqueia o PR.
- Texto dos comentarios em portugues, sem emojis, severidade entre colchetes.
- Python do Action: 3.11. `timeout-minutes: 10`. Permissoes: `contents: read`, `pull-requests: write`.
- Nenhum teste chama a API real do GitHub, do Qdrant ou da Groq.
- Execucao dos testes: `.venv/Scripts/python -m pytest ...` (Windows, Git Bash). Ao usar `git show origin/main-completa:CAMINHO`, definir `export MSYS_NO_PATHCONV=1`.
- Nao commitar o `requirements-dev.txt` local do autor (alteracao para ruff 0.16.10). Usar `git add` por caminho, nunca `git add -A`.
- Convencao do projeto: sem emojis nem travessoes em texto escrito, portugues conciso.
- **Documentar durante a implementacao** (pedido do autor): cada tarefa termina acrescentando linhas a tabela "Registro da implementacao" de D-011 em `docs/DECISIONS.md` (arquivo, funcao, para que serve), em uma linha cada. A tarefa 1 cria a tabela.

## Review Focus

Entradas que o spec implica e nenhuma tarefa de comportamento principal exercita; cada uma tem teste na tarefa dona:

1. `line_content` devolvido pelo LLM que nao existe no patch (alucinacao ou reformatacao): vai ao sumario, nao quebra a review. (Tarefa 4)
2. Duas violacoes com o mesmo texto de linha, ou linhas repetidas no arquivo: cada uma vai a uma linha diferente do diff. (Tarefa 4)
3. Execucao repetida em `synchronize`: comentario ja publicado nao e repetido. (Tarefa 4)
4. API recusa a review com 422 por posicao invalida: nova tentativa so com o sumario. (Tarefa 4)
5. Falha do LLM em um arquivo: os demais seguem e o arquivo aparece como nao revisado; falha em todos os arquivos faz o job falhar. (Tarefa 5)
6. PR sem nenhum arquivo `.py` revisavel e PR cujo contexto recuperado e vazio: aviso curto, sem erro. (Tarefa 5)
7. Resposta do LLM com `"ambiguous"` ausente, `false` ou string `"false"`: nunca vira ambigua por engano. (Tarefa 1)

---

## File Structure

| Arquivo | Acao | Responsabilidade |
|---|---|---|
| `rag_reviewer/llm_client.py` | modificar | `Violation.ambiguous`, severidades sem `CRITICAL`, ambigua vira `LOW` |
| `rag_reviewer/prompts/system_prompt.txt`, `review_template.txt` | modificar | sem `CRITICAL`, campo `ambiguous` |
| `rag_reviewer/config.py` | modificar | remove `block_on_critical` |
| `rag_reviewer/diff_parser.py` | substituir pelo da `main-completa` | `PullRequestDiff`, `DiffCollector`, filtro de arquivos |
| `rag_reviewer/retriever.py` | modificar | `retrieve_for_diff` |
| `rag_reviewer/github_publisher.py` | criar (adaptado) | review `COMMENT`, posicao exata, dedupe, fallback 422 |
| `rag_reviewer/reviewer.py`, `rag_reviewer/main.py` | criar (adaptados) | orquestracao e entrada do Action |
| `.github/workflows/rag_reviewer.yml` | criar (adaptado) | Action no `pull_request` |
| `requirements.txt`, `Makefile` | modificar | `requests`, alvo `test-integration` |
| `scripts/montar_prs_demo.py`, `scripts/conferir_prs_demo.py` | criar | PRs de teste a partir do dataset e conferencia com o gabarito |
| `docs/...`, `arquitetura.md`, `README.md` | modificar | documentacao |

---

### Task 1: Severidade sem CRITICAL e campo `ambiguous`

**Files:**
- Modify: `rag_reviewer/llm_client.py` (`_VALID_SEVERITIES`, `Violation`, `_parse_single_violation`)
- Modify: `rag_reviewer/prompts/system_prompt.txt`, `rag_reviewer/prompts/review_template.txt`
- Modify: `rag_reviewer/config.py` (remove `block_on_critical`)
- Modify: `tests/unit/test_llm_client.py` (linhas que citam `CRITICAL`)
- Modify: `.env.example` (se citar `BLOCK_ON_CRITICAL`)
- Modify: `docs/DECISIONS.md` (cria D-011 e a tabela de registro)

**Interfaces:**
- Produces: `Violation(line_content, violation_description, norm_reference, severity, suggestion, ambiguous: bool = False)`; `_VALID_SEVERITIES == frozenset({"HIGH", "MEDIUM", "LOW"})`. Quando `ambiguous` e verdadeiro, `severity` e sempre `"LOW"`.

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/unit/test_llm_client.py`, trocar `test_valid_severities_set` e `test_severity_normalized_to_uppercase` e acrescentar a classe nova ao final do arquivo:

```python
    def test_valid_severities_set(self):
        assert _VALID_SEVERITIES == frozenset({"HIGH", "MEDIUM", "LOW"})
        assert "CRITICAL" not in _VALID_SEVERITIES
```

```python
    def test_severity_normalized_to_uppercase(self):
        client = make_llm_client()
        d = make_violation_dict(severity="high")
        v = client._parse_single_violation(d)
        assert v.severity == "HIGH"

    def test_critical_is_no_longer_valid_and_defaults_to_low(self):
        client = make_llm_client()
        v = client._parse_single_violation(make_violation_dict(severity="CRITICAL"))
        assert v.severity == "LOW"
```

```python
class TestAmbiguous:
    def test_ambiguous_true_forces_low(self):
        client = make_llm_client()
        d = make_violation_dict(severity="HIGH")
        d["ambiguous"] = True
        v = client._parse_single_violation(d)
        assert v.ambiguous is True
        assert v.severity == "LOW"

    def test_ambiguous_absent_defaults_to_false(self):
        client = make_llm_client()
        v = client._parse_single_violation(make_violation_dict())
        assert v.ambiguous is False

    @pytest.mark.parametrize("valor", [False, "false", "true", 1, None])
    def test_only_boolean_true_is_ambiguous(self, valor):
        client = make_llm_client()
        d = make_violation_dict()
        d["ambiguous"] = valor
        assert client._parse_single_violation(d).ambiguous is False


class TestPromptsDaProducao:
    def test_prompts_nao_citam_critical_nem_normas_organizacionais(self):
        from pathlib import Path

        pasta = Path(__file__).resolve().parents[2] / "rag_reviewer" / "prompts"
        for nome in ("system_prompt.txt", "review_template.txt"):
            texto = (pasta / nome).read_text(encoding="utf-8")
            assert "CRITICAL" not in texto
            assert "organizacion" not in texto.lower()

    def test_template_pede_o_campo_ambiguous(self):
        from pathlib import Path

        pasta = Path(__file__).resolve().parents[2] / "rag_reviewer" / "prompts"
        assert '"ambiguous"' in (pasta / "review_template.txt").read_text(encoding="utf-8")
```

Procurar tambem a linha `assert v.severity == "CRITICAL"` (teste antigo, `test_severity_normalized_to_uppercase`) e confirmar que foi substituida; `grep -n CRITICAL tests/unit/test_llm_client.py` deve restar so nas linhas novas acima.

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/unit/test_llm_client.py -q`
Expected: FAIL (`CRITICAL` ainda valido, `Violation` sem `ambiguous`, prompts citam `CRITICAL`).

- [ ] **Step 3: Implementar em `llm_client.py`**

```python
# Severidades validas: a PEP 8 e estilo, entao nao ha CRITICAL nem bloqueio de PR
_VALID_SEVERITIES = frozenset({"HIGH", "MEDIUM", "LOW"})
```

Em `Violation`, trocar a docstring de `severity` por `"""Severidade da violação: 'HIGH' | 'MEDIUM' | 'LOW'."""` e acrescentar ao final da dataclass:

```python
    ambiguous: bool = False
    """True quando o texto da PEP 8 não decide o caso; a severidade é então LOW."""
```

Substituir `_parse_single_violation` por:

```python
    def _parse_single_violation(self, v: dict) -> Violation:
        """Converte um dict em Violation, validando campos obrigatórios."""
        ambiguous = v.get("ambiguous", False) is True
        severity = str(v.get("severity", "LOW")).upper()
        if severity not in _VALID_SEVERITIES or ambiguous:
            severity = "LOW"

        return Violation(
            line_content=str(v["line_content"]),
            violation_description=str(v["violation_description"]),
            norm_reference=str(v["norm_reference"]),
            severity=severity,
            suggestion=str(v["suggestion"]),
            ambiguous=ambiguous,
        )
```

- [ ] **Step 4: Prompts**

`rag_reviewer/prompts/system_prompt.txt`: trocar a regra 6 por
`6. Classifique cada violação como HIGH, MEDIUM ou LOW.`

`rag_reviewer/prompts/review_template.txt`: o bloco `## Tarefa` e o schema ficam assim (o resto do arquivo nao muda):

```
## Tarefa
Analise as linhas adicionadas e identifique violações à PEP 8 nos trechos acima.
Quando a violação depender de um bloco de várias linhas, use em
"line_content" a linha que abre o bloco (por exemplo, a linha "except ...:"),
não as linhas do corpo.
Se o texto da PEP 8 não decide o caso (por exemplo, um literal global em
minúsculas, que pode ou não ser uma constante), use "ambiguous": true e
severity "LOW"; caso contrário use "ambiguous": false.

Responda em JSON com o seguinte schema:
{{
  "violations": [
    {{
      "line_content": "trecho exato da linha violada",
      "violation_description": "descrição objetiva da violação, no máximo 15 palavras",
      "norm_reference": "seção da PEP 8 que a linha viola",
      "severity": "HIGH | MEDIUM | LOW",
      "suggestion": "como corrigir, no máximo 15 palavras",
      "ambiguous": true | false
    }}
  ]
}}
```

- [ ] **Step 5: Config e `.env.example`**

Em `rag_reviewer/config.py` remover o bloco `# ── Comportamento ──` e o campo `block_on_critical`. Rodar `grep -rn "block_on_critical\|BLOCK_ON_CRITICAL" --include=*.py --include=.env.example --include=*.yml .`; remover o que restar fora de `docs/` e `arquitetura.md` (esses ficam para a tarefa 7).

- [ ] **Step 6: Rodar os testes**

Run: `.venv/Scripts/python -m pytest tests/unit -q --deselect tests/unit/test_embedder.py`
Expected: PASS.

- [ ] **Step 7: Criar D-011 em `docs/DECISIONS.md` (antes de `## Pendências`, precedido de `---`)**

```markdown
## D-011 — Workflow do GitHub: o RAG-Reviewer revisando PRs reais

Spec: `docs/superpowers/specs/2026-10-09-workflow-github-design.md`. Plano:
`docs/superpowers/plans/2026-10-09-workflow-github.md`. Branch
`feat/workflow-github`. O PR de revisão nunca é bloqueado (a PEP 8 é estilo);
`CRITICAL` deixou de existir; o modelo marca `ambiguous` quando a PEP 8 não decide
(F-004). Da `main-completa` entrou só o que é workflow; o resto é da `main`.

### Registro da implementação

| Arquivo | Função / elemento | Para que serve |
|---|---|---|
| `rag_reviewer/llm_client.py` | `_VALID_SEVERITIES`, `Violation.ambiguous`, `_parse_single_violation` | Severidade só HIGH/MEDIUM/LOW; campo `ambiguous` (só `true` booleano vale) força LOW |
| `rag_reviewer/prompts/*.txt` | regra 6, schema | Sem CRITICAL; o modelo marca a ambiguidade |
| `rag_reviewer/config.py` | remoção de `block_on_critical` | O Action nunca bloqueia |
```

- [ ] **Step 8: Commit**

```bash
git add rag_reviewer/llm_client.py rag_reviewer/prompts rag_reviewer/config.py tests/unit/test_llm_client.py docs/DECISIONS.md
git commit -m "feat: severidade sem CRITICAL e campo ambiguous na resposta do LLM (D-011)"
```
(Se `.env.example` mudou, incluir no `git add`.)

---

### Task 2: Coleta do diff (`DiffCollector`)

**Files:**
- Replace: `rag_reviewer/diff_parser.py` (conteudo da `main-completa`)
- Modify: `requirements.txt`
- Create: `tests/unit/test_diff_parser.py` (da `main-completa`, ajustado)
- Modify: `docs/DECISIONS.md` (tabela)

**Interfaces:**
- Produces: `FileDiff` (mesmos campos de hoje), `PullRequestDiff(pr_number, repo, files, total_additions, total_deletions)`, `DiffCollector(token=None, repo=None, pr_number=None).collect() -> PullRequestDiff`, `_extract_added_lines(patch)`, `_is_ignored_file(filename)`, `build_query_text(file_diff, max_chars)`.

- [ ] **Step 1: Trazer o modulo e o teste da `main-completa`**

```bash
export MSYS_NO_PATHCONV=1
git show origin/main-completa:rag_reviewer/diff_parser.py > rag_reviewer/diff_parser.py
git show origin/main-completa:tests/unit/test_diff_parser.py > tests/unit/test_diff_parser.py
```

- [ ] **Step 2: Acrescentar o teste do filtro `.py` (falha)**

Em `tests/unit/test_diff_parser.py`, dentro de `class TestDiffCollectorParseFiles`, acrescentar (usa o helper `make_raw_file` e o coletor ja criado nos outros testes da classe; copiar o padrao de `test_skips_deleted_files`):

```python
    def test_skips_non_python_files(self):
        collector = DiffCollector(token="t", repo="o/r", pr_number=1)
        raw = [
            make_raw_file(filename="README.md"),
            make_raw_file(filename="app/x.py"),
        ]
        files = collector._parse_files(raw)
        assert [f.filename for f in files] == ["app/x.py"]
```

Run: `.venv/Scripts/python -m pytest tests/unit/test_diff_parser.py -q`
Expected: FAIL em `test_skips_non_python_files` (e possivelmente em testes portados que usam nomes nao `.py`).

- [ ] **Step 3: Filtro `.py` em `_parse_files`**

Logo apos o bloco `if status == "deleted": ... continue`, acrescentar:

```python
            # O piloto revisa só Python (PEP 8)
            if not filename.endswith(".py"):
                skipped += 1
                continue
```
Atualizar a docstring de `_parse_files` (lista de filtros) e a de `collect` com "arquivos que não são `.py`".

- [ ] **Step 4: Ajustar testes portados**

Rodar `.venv/Scripts/python -m pytest tests/unit/test_diff_parser.py -q`. Os testes que falharem so porque o nome do arquivo nao termina em `.py` ganham nome `.py` (ex.: `"image.png"` continua valido em testes de ignorados; `"src/a.js"` vira `"src/a.py"`). Nao alterar a logica dos testes.

- [ ] **Step 5: `requirements.txt`**

Sob o comentario `# GitHub API`, acrescentar a linha `requests==2.32.3`.
Run: `.venv/Scripts/python -c "import requests; print(requests.__version__)"`; se faltar, `.venv/Scripts/python -m pip install requests==2.32.3`.

- [ ] **Step 6: Rodar tudo**

Run: `.venv/Scripts/python -m pytest tests/unit -q --deselect tests/unit/test_embedder.py`
Expected: PASS.

- [ ] **Step 7: Registrar e commitar**

Linhas na tabela de D-011:
`| rag_reviewer/diff_parser.py | PullRequestDiff, DiffCollector.collect/_paginate/_parse_files | Lista os arquivos do PR pela API (com paginação), descarta deletados, binários, sem patch e não .py, e monta cada FileDiff |`
`| requirements.txt | requests | Cliente HTTP da API do GitHub |`

```bash
git add rag_reviewer/diff_parser.py tests/unit/test_diff_parser.py requirements.txt docs/DECISIONS.md
git commit -m "feat: coleta do diff do PR pela API do GitHub (D-011)"
```

---

### Task 3: `Retriever.retrieve_for_diff`

**Files:**
- Modify: `rag_reviewer/retriever.py`
- Modify: `tests/unit/test_retriever.py`
- Modify: `docs/DECISIONS.md` (tabela)

**Interfaces:**
- Consumes: `PullRequestDiff.files: list[FileDiff]`; `Retriever.retrieve_for_file(file_diff) -> RetrievedContext | None` (ja existe).
- Produces: `Retriever.retrieve_for_diff(pr_diff: PullRequestDiff) -> list[RetrievedContext]`.

- [ ] **Step 1: Teste que falha**

Ler o inicio de `tests/unit/test_retriever.py` para reaproveitar o helper que cria um `Retriever` com `Embedder` e `VectorStore` simulados; acrescentar ao final:

```python
class TestRetrieveForDiff:
    def test_ignora_arquivo_sem_linhas_adicionadas_e_sem_contexto(self):
        from rag_reviewer.diff_parser import FileDiff, PullRequestDiff
        from unittest.mock import MagicMock

        retriever = Retriever.__new__(Retriever)
        com_linhas = FileDiff(filename="a.py", patch="p", status="added", added_lines=["x = 1"])
        sem_linhas = FileDiff(filename="b.py", patch="p", status="modified", added_lines=[])
        sem_contexto = FileDiff(filename="c.py", patch="p", status="added", added_lines=["y = 2"])
        ctx_a = MagicMock()
        retriever._retrieve_for_file = MagicMock(
            side_effect=lambda fd: ctx_a if fd.filename == "a.py" else None
        )
        pr_diff = PullRequestDiff(
            pr_number=1, repo="o/r",
            files=[com_linhas, sem_linhas, sem_contexto],
            total_additions=2, total_deletions=0,
        )
        assert retriever.retrieve_for_diff(pr_diff) == [ctx_a]
        consultados = [c.args[0].filename for c in retriever._retrieve_for_file.call_args_list]
        assert consultados == ["a.py", "c.py"]

    def test_pr_sem_arquivos_devolve_lista_vazia(self):
        from rag_reviewer.diff_parser import PullRequestDiff

        retriever = Retriever.__new__(Retriever)
        pr_diff = PullRequestDiff(pr_number=1, repo="o/r", files=[], total_additions=0, total_deletions=0)
        assert retriever.retrieve_for_diff(pr_diff) == []
```

Run: `.venv/Scripts/python -m pytest tests/unit/test_retriever.py -q -k RetrieveForDiff`
Expected: FAIL (`retrieve_for_diff` nao existe).

- [ ] **Step 2: Implementar**

Em `rag_reviewer/retriever.py`: importar `from rag_reviewer.diff_parser import FileDiff, PullRequestDiff` e inserir antes de `retrieve_for_file`:

```python
    def retrieve_for_diff(self, pr_diff: PullRequestDiff) -> list[RetrievedContext]:
        """
        Recupera o contexto normativo de cada arquivo do PR.

        Ignora arquivos sem linhas adicionadas e arquivos em que nenhum chunk
        atinge o `score_threshold`. Cada arquivo usa `_retrieve_for_file`
        (busca por linha, união com o maior score, corte em 8 chunks).
        """
        candidatos = [f for f in pr_diff.files if f.added_lines]
        console.log(
            f"[cyan]Retriever:[/cyan] {len(candidatos)}/{len(pr_diff.files)} "
            f"arquivo(s) com linhas adicionadas para revisar."
        )
        contextos: list[RetrievedContext] = []
        for file_diff in candidatos:
            contexto = self._retrieve_for_file(file_diff)
            if contexto is not None:
                contextos.append(contexto)
        return contextos
```
Atualizar a linha "Uso típico" do docstring do modulo para citar `retrieve_for_diff`.

- [ ] **Step 3: Rodar**

Run: `.venv/Scripts/python -m pytest tests/unit/test_retriever.py -q`
Expected: PASS.

- [ ] **Step 4: Registrar e commitar**

`| rag_reviewer/retriever.py | Retriever.retrieve_for_diff | Aplica a recuperação por arquivo a todos os arquivos do PR e descarta os sem linhas adicionadas ou sem contexto |`

```bash
git add rag_reviewer/retriever.py tests/unit/test_retriever.py docs/DECISIONS.md
git commit -m "feat: retrieve_for_diff recupera o contexto de todos os arquivos do PR (D-011)"
```

---

### Task 4: `GitHubPublisher`

**Files:**
- Create: `rag_reviewer/github_publisher.py`
- Create: `tests/unit/test_github_publisher.py`
- Modify: `docs/DECISIONS.md` (tabela)

**Interfaces:**
- Consumes: `Violation` (Task 1), `FileDiff`/`PullRequestDiff` (Task 2).
- Produces: `GitHubPublisher(token=None, repo=None, pr_number=None, head_sha=None)` com `publish(violations, pr_diff, unreviewed=None, model=None) -> None` e `post_summary(message) -> None`; funcoes puras `_find_diff_position(patch, line_content, usadas=None) -> int | None`, `_format_inline_comment(violation) -> str`, `_count_by_severity(violations) -> dict[str, int]`, `_build_summary_body(total, counts, notas=None, unreviewed=None, model=None) -> str`. `ViolationList = list[tuple[FileDiff, Violation]]`.

- [ ] **Step 1: Escrever `tests/unit/test_github_publisher.py` (falha: modulo nao existe)**

```python
"""Testes do GitHubPublisher (HTTP simulado, sem rede)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rag_reviewer.diff_parser import FileDiff, PullRequestDiff
from rag_reviewer.github_publisher import (
    GitHubPublisher,
    _build_summary_body,
    _count_by_severity,
    _find_diff_position,
    _format_inline_comment,
)
from rag_reviewer.llm_client import Violation

PATCH = (
    "@@ -0,0 +1,4 @@\n"
    "+import os\n"
    "+x = 1\n"
    "+y = 2\n"
    "+x = 1"
)


def make_violation(line="x = 1", severity="HIGH", ambiguous=False) -> Violation:
    return Violation(
        line_content=line,
        violation_description="Descrição",
        norm_reference="PEP 8 - Naming Conventions",
        severity=severity,
        suggestion="Corrija",
        ambiguous=ambiguous,
    )


def make_file(patch=PATCH, name="app/a.py") -> FileDiff:
    return FileDiff(filename=name, patch=patch, status="added", added_lines=[])


def make_pr(files=None) -> PullRequestDiff:
    return PullRequestDiff(
        pr_number=7, repo="o/r", files=files or [make_file()],
        total_additions=4, total_deletions=0,
    )


def make_publisher() -> GitHubPublisher:
    return GitHubPublisher(token="t", repo="o/r", pr_number=7, head_sha="abc")


def resp(status=200, json=None, links=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json if json is not None else []
    r.links = links or {}
    r.raise_for_status.side_effect = (
        None if status < 400 else RuntimeError(f"HTTP {status}")
    )
    return r


class TestFindDiffPosition:
    def test_acha_linha_adicionada(self):
        assert _find_diff_position(PATCH, "import os") == 2

    def test_nao_acha_trecho_ausente(self):
        assert _find_diff_position(PATCH, "z = 9") is None

    def test_patch_ou_trecho_vazio(self):
        assert _find_diff_position("", "x") is None
        assert _find_diff_position(PATCH, "") is None
        assert _find_diff_position(PATCH, "   ") is None

    def test_nao_casa_linha_removida_nem_contexto(self):
        patch = "@@ -1,2 +1,1 @@\n-velha = 1\n contexto = 2"
        assert _find_diff_position(patch, "velha = 1") is None
        assert _find_diff_position(patch, "contexto = 2") is None

    def test_cabecalho_de_hunk_conta_posicao(self):
        assert _find_diff_position("@@ -0,0 +1 @@\n+a = 1", "a = 1") == 2

    def test_linhas_repetidas_vao_a_posicoes_diferentes(self):
        usadas: set[int] = set()
        primeira = _find_diff_position(PATCH, "x = 1", usadas)
        segunda = _find_diff_position(PATCH, "x = 1", usadas)
        assert (primeira, segunda) == (3, 5)
        assert _find_diff_position(PATCH, "x = 1", usadas) is None

    def test_igualdade_exata_vence_substring(self):
        patch = "@@ -0,0 +1,2 @@\n+total = x + 1\n+x = 1"
        assert _find_diff_position(patch, "x = 1") == 3

    def test_substring_quando_nao_ha_igualdade(self):
        assert _find_diff_position(PATCH, "import") == 2


class TestFormat:
    def test_comentario_normal(self):
        texto = _format_inline_comment(make_violation(severity="MEDIUM"))
        assert texto.startswith("**[MEDIUM]** Descrição")
        assert "**Norma:** `PEP 8 - Naming Conventions`" in texto
        assert "**Como corrigir:** Corrija" in texto

    def test_comentario_ambiguo_nao_afirma_violacao(self):
        texto = _format_inline_comment(make_violation(severity="LOW", ambiguous=True))
        assert texto.startswith("**[LOW] Possível ambiguidade.**")
        assert "Descrição" in texto

    def test_sem_emojis(self):
        texto = _format_inline_comment(make_violation())
        assert all(ord(c) < 0x2000 for c in texto)

    def test_contagem_por_severidade(self):
        fd = make_file()
        v = [(fd, make_violation(severity="HIGH")), (fd, make_violation(severity="LOW")),
             (fd, make_violation(severity="HIGH"))]
        assert _count_by_severity(v) == {"HIGH": 2, "LOW": 1}

    def test_sumario_com_violacoes(self):
        corpo = _build_summary_body(3, {"LOW": 1, "HIGH": 2}, model="m")
        assert "3 violação(ões) detectada(s)" in corpo
        assert corpo.index("HIGH") < corpo.index("LOW")
        assert "CRITICAL" not in corpo
        assert "`m`" in corpo

    def test_sumario_lista_notas_e_nao_revisados(self):
        corpo = _build_summary_body(1, {"HIGH": 1}, notas=["- `a.py`: algo"], unreviewed=["b.py"])
        assert "- `a.py`: algo" in corpo
        assert "- `b.py`" in corpo

    def test_sumario_sem_violacoes_novas(self):
        assert "nenhuma violação nova" in _build_summary_body(0, {})


class TestPublish:
    def test_sem_violacoes_publica_aprovacao(self):
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.post.return_value = resp(201)
            make_publisher().publish([], make_pr())
        url = req.post.call_args.args[0]
        assert url.endswith("/issues/7/comments")

    def test_comentario_inline_vai_com_a_posicao(self):
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [])
            req.post.return_value = resp(200)
            make_publisher().publish([(make_file(), make_violation("import os"))], make_pr())
        payload = req.post.call_args.kwargs["json"]
        assert payload["event"] == "COMMENT"
        assert payload["commit_id"] == "abc"
        assert payload["comments"][0]["position"] == 2
        assert payload["comments"][0]["path"] == "app/a.py"

    def test_linha_inexistente_no_diff_vai_ao_sumario(self):
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [])
            req.post.return_value = resp(200)
            make_publisher().publish([(make_file(), make_violation("nao existe"))], make_pr())
        payload = req.post.call_args.kwargs["json"]
        assert payload["comments"] == []
        assert "sem linha localizável" in payload["body"]
        assert "nao existe" in payload["body"] or "Descrição" in payload["body"]

    def test_violacoes_de_mesmo_texto_vao_a_linhas_diferentes(self):
        fd = make_file()
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [])
            req.post.return_value = resp(200)
            make_publisher().publish(
                [(fd, make_violation("x = 1")), (fd, make_violation("x = 1"))], make_pr()
            )
        posicoes = [c["position"] for c in req.post.call_args.kwargs["json"]["comments"]]
        assert posicoes == [3, 5]

    def test_nao_repete_comentario_ja_publicado(self):
        fd = make_file()
        corpo = _format_inline_comment(make_violation("import os"))
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [{"path": "app/a.py", "body": corpo}])
            make_publisher().publish([(fd, make_violation("import os"))], make_pr())
        req.post.assert_not_called()

    def test_422_tenta_de_novo_so_com_o_sumario(self):
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [])
            req.post.side_effect = [resp(422), resp(200)]
            make_publisher().publish([(make_file(), make_violation("import os"))], make_pr())
        assert req.post.call_count == 2
        segunda = req.post.call_args.kwargs["json"]
        assert segunda["comments"] == []
        assert "app/a.py" in segunda["body"]

    def test_falha_ao_ler_comentarios_existentes_nao_impede_publicar(self):
        import requests as real

        with patch("rag_reviewer.github_publisher.requests") as req:
            req.RequestException = real.RequestException
            req.get.side_effect = real.RequestException("falhou")
            req.post.return_value = resp(200)
            make_publisher().publish([(make_file(), make_violation("import os"))], make_pr())
        assert req.post.call_count == 1

    def test_so_arquivos_nao_revisados_publica_sumario(self):
        with patch("rag_reviewer.github_publisher.requests") as req:
            req.get.return_value = resp(200, [])
            req.post.return_value = resp(200)
            make_publisher().publish([], make_pr(), unreviewed=["b.py"])
        assert "- `b.py`" in req.post.call_args.kwargs["json"]["body"]

    def test_publisher_nao_tem_request_changes(self):
        assert not hasattr(GitHubPublisher, "request_changes")
```

Run: `.venv/Scripts/python -m pytest tests/unit/test_github_publisher.py -q`
Expected: FAIL (ImportError: modulo nao existe).

- [ ] **Step 2: Implementar `rag_reviewer/github_publisher.py`**

```python
"""
github_publisher.py - Publicação da revisão no PR pela API REST do GitHub.

Responsabilidades:
  1. Achar a posição de cada violação no diff unificado.
  2. Criar UMA review `COMMENT` com um comentário inline por violação.
  3. Pular comentários que já existem no PR (o Action roda a cada push).
  4. Cair para um sumário sem inline quando a API recusa as posições (422).

O revisor nunca bloqueia o PR: a PEP 8 é estilo (D-011).
"""

from __future__ import annotations

import requests
from rich.console import Console

from rag_reviewer.config import get_settings
from rag_reviewer.diff_parser import FileDiff, PullRequestDiff
from rag_reviewer.llm_client import Violation

console = Console()

ViolationList = list[tuple[FileDiff, Violation]]

_SEVERITIES = ("HIGH", "MEDIUM", "LOW")
_GITHUB_API_BASE = "https://api.github.com"
_APPROVAL_MESSAGE = "Nenhuma violação da PEP 8 detectada nas linhas adicionadas."


class GitHubPublisher:
    """Publica a revisão no PR: uma review COMMENT com comentários inline."""

    def __init__(
        self,
        token: str | None = None,
        repo: str | None = None,
        pr_number: int | None = None,
        head_sha: str | None = None,
    ) -> None:
        settings = get_settings()
        self._token = token if token is not None else settings.github_token
        self._repo = repo if repo is not None else settings.repo_full_name
        self._pr_number = pr_number if pr_number is not None else settings.pr_number
        self._head_sha = head_sha if head_sha is not None else settings.pr_head_sha
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ── Interface pública ─────────────────────────────────────────────────

    def publish(
        self,
        violations: ViolationList,
        pr_diff: PullRequestDiff,
        unreviewed: list[str] | None = None,
        model: str | None = None,
    ) -> None:
        """
        Publica a revisão.

        Sem violações e sem arquivos não revisados, publica só a aprovação.
        Com violações, publica uma review com os comentários que ainda não
        existem no PR. Se nada é novo, não publica nada.
        """
        unreviewed = unreviewed or []
        if not violations and not unreviewed:
            self.post_summary(_APPROVAL_MESSAGE)
            return

        existentes = self._existing_comments()
        inline, sem_posicao, novas = self._build_review_comments(violations, existentes)
        if violations and not novas and not unreviewed:
            console.log(
                "[dim]GitHubPublisher:[/dim] todos os comentários já existem no PR; "
                "nada a publicar."
            )
            return

        notas = [_nota(fd, v) for fd, v in sem_posicao]
        counts = _count_by_severity(novas)
        self._create_review(inline, counts, notas, unreviewed, model)
        console.log(
            f"[green]GitHubPublisher:[/green] review publicada, "
            f"{len(novas)} violação(ões) nova(s), {len(inline)} comentário(s) inline."
        )

    def post_summary(self, message: str) -> None:
        """Publica um comentário geral (não inline) no PR."""
        url = f"{_GITHUB_API_BASE}/repos/{self._repo}/issues/{self._pr_number}/comments"
        response = requests.post(
            url, headers=self._headers, json={"body": message}, timeout=30
        )
        response.raise_for_status()

    # ── Internos ──────────────────────────────────────────────────────────

    def _existing_comments(self) -> set[tuple[str, str]]:
        """(path, corpo) dos comentários de review já publicados. Falha vira conjunto vazio."""
        url = f"{_GITHUB_API_BASE}/repos/{self._repo}/pulls/{self._pr_number}/comments"
        existentes: set[tuple[str, str]] = set()
        try:
            atual: str | None = url
            while atual:
                response = requests.get(
                    atual, headers=self._headers, params={"per_page": 100}, timeout=30
                )
                response.raise_for_status()
                existentes.update(
                    (c.get("path", ""), c.get("body", "")) for c in response.json()
                )
                atual = response.links.get("next", {}).get("url")
        except requests.RequestException as exc:
            console.log(
                f"[yellow]GitHubPublisher:[/yellow] não leu os comentários existentes "
                f"({exc}); publicando sem checar repetições."
            )
            return set()
        return existentes

    def _build_review_comments(
        self, violations: ViolationList, existentes: set[tuple[str, str]]
    ) -> tuple[list[dict], ViolationList, ViolationList]:
        """
        Separa as violações em comentários inline e violações sem posição.

        Returns:
            (inline, sem_posicao, novas): `novas` é tudo que ainda não existe no
            PR (inline mais sem posição), usado na contagem do sumário.
        """
        inline: list[dict] = []
        sem_posicao: ViolationList = []
        novas: ViolationList = []
        usadas: dict[str, set[int]] = {}
        for file_diff, violation in violations:
            corpo = _format_inline_comment(violation)
            if (file_diff.filename, corpo) in existentes:
                continue
            novas.append((file_diff, violation))
            posicao = _find_diff_position(
                file_diff.patch,
                violation.line_content,
                usadas.setdefault(file_diff.filename, set()),
            )
            if posicao is None:
                sem_posicao.append((file_diff, violation))
            else:
                inline.append(
                    {"path": file_diff.filename, "position": posicao, "body": corpo}
                )
        return inline, sem_posicao, novas

    def _create_review(
        self,
        comments: list[dict],
        counts: dict[str, int],
        notas: list[str],
        unreviewed: list[str],
        model: str | None,
    ) -> None:
        """Cria a review. Se a API recusar as posições (422), refaz só com o sumário."""
        url = f"{_GITHUB_API_BASE}/repos/{self._repo}/pulls/{self._pr_number}/reviews"
        total = sum(counts.values())
        payload = {
            "commit_id": self._head_sha,
            "body": _build_summary_body(total, counts, notas, unreviewed, model),
            "event": "COMMENT",
            "comments": comments,
        }
        response = requests.post(url, headers=self._headers, json=payload, timeout=30)
        if response.status_code == 422 and comments:
            console.log(
                "[yellow]GitHubPublisher:[/yellow] a API recusou os comentários inline "
                "(422); publicando só o sumário."
            )
            extras = [f"- `{c['path']}`: {c['body'].splitlines()[0]}" for c in comments]
            payload["body"] = _build_summary_body(
                total, counts, notas + extras, unreviewed, model
            )
            payload["comments"] = []
            response = requests.post(
                url, headers=self._headers, json=payload, timeout=30
            )
        response.raise_for_status()


# ── Funções puras ─────────────────────────────────────────────────────────────


def _find_diff_position(
    patch: str, line_content: str, usadas: set[int] | None = None
) -> int | None:
    """
    Posição (1-indexada) de uma linha adicionada dentro do patch.

    A posição conta a partir do primeiro cabeçalho de hunk, incluindo
    cabeçalhos, linhas de contexto e adicionadas, e não conta as removidas.
    Prefere a igualdade exata (após `strip`) à substring e ignora as posições
    em `usadas`, para que violações de texto igual caiam em linhas diferentes.
    A posição escolhida é registrada em `usadas`.
    """
    if not patch or not line_content or not line_content.strip():
        return None
    usadas = usadas if usadas is not None else set()
    alvo = line_content.strip()
    exata: int | None = None
    parcial: int | None = None
    posicao = 0
    for linha in patch.splitlines():
        if linha.startswith("-"):
            continue
        posicao += 1
        if (
            linha.startswith("+")
            and not linha.startswith("+++")
            and posicao not in usadas
        ):
            conteudo = linha[1:].strip()
            if conteudo == alvo and exata is None:
                exata = posicao
            elif alvo in conteudo and parcial is None:
                parcial = posicao
    escolhida = exata if exata is not None else parcial
    if escolhida is not None:
        usadas.add(escolhida)
    return escolhida


def _format_inline_comment(violation: Violation) -> str:
    """Corpo Markdown do comentário inline: severidade, descrição, norma e correção."""
    if violation.ambiguous:
        abertura = (
            "**[LOW] Possível ambiguidade.** O texto da PEP 8 não decide este caso."
            f"\n\n{violation.violation_description}"
        )
    else:
        abertura = f"**[{violation.severity}]** {violation.violation_description}"
    return (
        f"{abertura}\n\n"
        f"**Norma:** `{violation.norm_reference}`\n\n"
        f"**Como corrigir:** {violation.suggestion}"
    )


def _nota(file_diff: FileDiff, violation: Violation) -> str:
    """Linha do sumário para uma violação sem posição localizável no diff."""
    return (
        f"- `{file_diff.filename}`: [{violation.severity}] "
        f"{violation.violation_description} (`{violation.norm_reference}`). "
        f"Linha: `{violation.line_content}`"
    )


def _count_by_severity(violations: ViolationList) -> dict[str, int]:
    """Conta as violações por severidade."""
    counts: dict[str, int] = {}
    for _, v in violations:
        counts[v.severity] = counts.get(v.severity, 0) + 1
    return counts


def _build_summary_body(
    total: int,
    counts: dict[str, int],
    notas: list[str] | None = None,
    unreviewed: list[str] | None = None,
    model: str | None = None,
) -> str:
    """Corpo Markdown da review: tabela por severidade, notas e arquivos não revisados."""
    if total:
        linhas = [
            f"## RAG-Reviewer: {total} violação(ões) detectada(s)\n",
            "| Severidade | Quantidade |",
            "|---|---|",
        ]
        for severidade in _SEVERITIES:
            if counts.get(severidade, 0) > 0:
                linhas.append(f"| {severidade} | {counts[severidade]} |")
    else:
        linhas = ["## RAG-Reviewer: nenhuma violação nova detectada\n"]
    if notas:
        linhas += ["", "Violações sem linha localizável no diff:", *notas]
    if unreviewed:
        linhas += [
            "",
            "Arquivos não revisados (falha na chamada ao LLM):",
            *[f"- `{nome}`" for nome in unreviewed],
        ]
    rodape = "Revisão automática do RAG-Reviewer com base na PEP 8"
    if model:
        rodape += f" (modelo `{model}`)"
    linhas += ["", f"> *{rodape}.*"]
    return "\n".join(linhas)
```

- [ ] **Step 3: Rodar**

Run: `.venv/Scripts/python -m pytest tests/unit/test_github_publisher.py -q`
Expected: PASS. Se `test_nao_repete_comentario_ja_publicado` falhar por `req.get().links` ser `MagicMock`, e porque `resp(...)` ja define `links = {}`; conferir que o helper foi copiado inteiro.

- [ ] **Step 4: Registrar e commitar**

`| rag_reviewer/github_publisher.py | GitHubPublisher.publish/_create_review | Uma review COMMENT com comentários inline; cai para só o sumário se a API devolver 422 |`
`| rag_reviewer/github_publisher.py | _find_diff_position(…, usadas) | Posição exata da linha no diff; linhas repetidas vão a posições diferentes |`
`| rag_reviewer/github_publisher.py | _existing_comments, _build_review_comments | Não repete comentário já publicado (o Action roda a cada push) |`
`| rag_reviewer/github_publisher.py | _format_inline_comment, _build_summary_body | Texto do comentário (severidade, norma, como corrigir, ambiguidade) e sumário |`

```bash
git add rag_reviewer/github_publisher.py tests/unit/test_github_publisher.py docs/DECISIONS.md
git commit -m "feat: publisher da review COMMENT com posicao exata, dedupe e fallback 422 (D-011)"
```

---

### Task 5: Orquestrador e entrada do Action

**Files:**
- Create: `rag_reviewer/reviewer.py`, `rag_reviewer/main.py`
- Create: `tests/unit/test_reviewer.py`
- Create: `tests/integration/__init__.py`, `tests/integration/test_rag_pipeline.py` (da `main-completa`, ajustado)
- Modify: `Makefile` (alvo `test-integration`)
- Modify: `docs/DECISIONS.md` (tabela)

**Interfaces:**
- Consumes: `DiffCollector.collect()`, `Retriever.retrieve_for_diff`, `LLMClient.review(context) -> list[Violation]` e `LLMClient.model`, `GitHubPublisher.publish/post_summary`.
- Produces: `RAGReviewer(collector=None, embedder=None, store=None, retriever=None, llm=None, publisher=None).run() -> ViolationList`.

- [ ] **Step 1: Testes do orquestrador (falham)**

`tests/unit/test_reviewer.py`:

```python
"""Testes do RAGReviewer com todas as dependências simuladas."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rag_reviewer.diff_parser import FileDiff, PullRequestDiff
from rag_reviewer.llm_client import Violation
from rag_reviewer.reviewer import RAGReviewer


def fd(name="a.py") -> FileDiff:
    return FileDiff(filename=name, patch="@@ -0,0 +1 @@\n+x = 1", status="added", added_lines=["x = 1"])


def ctx(name="a.py"):
    c = MagicMock()
    c.file_diff = fd(name)
    return c


def viol(severity="HIGH") -> Violation:
    return Violation("x = 1", "desc", "PEP 8", severity, "fix")


def make(files=None, contextos=None, llm_side_effect=None, violacoes=None):
    collector = MagicMock()
    collector.collect.return_value = PullRequestDiff(
        pr_number=1, repo="o/r", files=files if files is not None else [fd()],
        total_additions=1, total_deletions=0,
    )
    retriever = MagicMock()
    retriever.retrieve_for_diff.return_value = contextos if contextos is not None else [ctx()]
    llm = MagicMock()
    llm.model = "modelo-x"
    if llm_side_effect is not None:
        llm.review.side_effect = llm_side_effect
    else:
        llm.review.return_value = violacoes if violacoes is not None else [viol()]
    publisher = MagicMock()
    return RAGReviewer(collector=collector, retriever=retriever, llm=llm, publisher=publisher), publisher, llm


def test_publica_as_violacoes_com_o_modelo():
    rev, pub, _ = make()
    resultado = rev.run()
    assert len(resultado) == 1
    args = pub.publish.call_args
    assert args.kwargs["model"] == "modelo-x"
    assert args.kwargs["unreviewed"] == []


def test_nunca_pede_mudancas_mesmo_com_severidade_alta():
    rev, pub, _ = make(violacoes=[viol("HIGH")])
    rev.run()
    assert not hasattr(pub, "request_changes") or not pub.request_changes.called


def test_pr_sem_arquivos_publica_aviso_curto():
    rev, pub, llm = make(files=[])
    assert rev.run() == []
    pub.post_summary.assert_called_once()
    llm.review.assert_not_called()


def test_sem_contexto_recuperado_publica_aviso_curto():
    rev, pub, llm = make(contextos=[])
    assert rev.run() == []
    pub.post_summary.assert_called_once()
    llm.review.assert_not_called()


def test_falha_em_um_arquivo_nao_derruba_os_outros():
    chamadas = {"n": 0}

    def efeito(context):
        chamadas["n"] += 1
        if context.file_diff.filename == "a.py":
            raise ValueError("JSON invalido")
        return [viol()]

    rev, pub, _ = make(contextos=[ctx("a.py"), ctx("b.py")], llm_side_effect=efeito)
    resultado = rev.run()
    assert [f.filename for f, _ in resultado] == ["b.py"]
    assert pub.publish.call_args.kwargs["unreviewed"] == ["a.py"]


def test_falha_em_todos_os_arquivos_falha_o_job_depois_de_publicar():
    rev, pub, _ = make(contextos=[ctx("a.py")], llm_side_effect=ValueError("x"))
    with pytest.raises(RuntimeError):
        rev.run()
    pub.publish.assert_called_once()


def test_rate_limit_tem_uma_nova_tentativa(monkeypatch):
    class RateLimitError(Exception):
        pass

    monkeypatch.setattr("rag_reviewer.reviewer.time.sleep", lambda s: None)
    respostas = [RateLimitError("429"), [viol()]]

    def efeito(context):
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    rev, pub, llm = make(llm_side_effect=efeito)
    assert len(rev.run()) == 1
    assert llm.review.call_count == 2
```

Run: `.venv/Scripts/python -m pytest tests/unit/test_reviewer.py -q`
Expected: FAIL (modulo nao existe).

- [ ] **Step 2: `rag_reviewer/reviewer.py`**

```python
"""
reviewer.py - Orquestrador do RAG-Reviewer (o que o GitHub Action executa).

Fluxo: diff do PR -> recuperação de normas -> LLM por arquivo -> publicação.
A revisão nunca bloqueia o PR (D-011): a PEP 8 é estilo.
"""

from __future__ import annotations

import time

from rich.console import Console

from rag_reviewer.diff_parser import DiffCollector, FileDiff
from rag_reviewer.embedder import Embedder
from rag_reviewer.llm_client import LLMClient, Violation
from rag_reviewer.retriever import RetrievedContext, Retriever
from rag_reviewer.vector_store import VectorStore

console = Console()

ViolationList = list[tuple[FileDiff, Violation]]

_ESPERA_RATE_LIMIT_PADRAO = 20.0
_ESPERA_RATE_LIMIT_MAXIMA = 30.0  # o Action tem timeout de 10 minutos


class RAGReviewer:
    """Coordena coleta, recuperação, LLM e publicação. Dependências injetáveis."""

    def __init__(
        self,
        collector: DiffCollector | None = None,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
        retriever: Retriever | None = None,
        llm: LLMClient | None = None,
        publisher=None,
    ) -> None:
        self._collector = collector or DiffCollector()
        self._retriever = retriever or Retriever(
            embedder=embedder or Embedder(), store=store or VectorStore()
        )
        self._llm = llm or LLMClient()
        self._publisher = publisher  # GitHubPublisher, criado sob demanda

    def run(self) -> ViolationList:
        """Revisa o PR e publica o resultado. Devolve as violações encontradas."""
        console.rule("[bold cyan]RAG-Reviewer: iniciando revisão[/bold cyan]")

        pr_diff = self._collector.collect()
        if not pr_diff.files:
            self._get_publisher().post_summary(
                "Nenhum arquivo Python com linhas adicionadas para revisar."
            )
            return []

        contextos = self._retriever.retrieve_for_diff(pr_diff)
        if not contextos:
            self._get_publisher().post_summary(
                "Nenhuma norma da PEP 8 foi recuperada para as linhas adicionadas."
            )
            return []

        violacoes, nao_revisados = self._review_all_contexts(contextos)
        self._get_publisher().publish(
            violacoes, pr_diff, unreviewed=nao_revisados, model=self._llm.model
        )
        if nao_revisados and len(nao_revisados) == len(contextos):
            raise RuntimeError(
                "Nenhum arquivo foi revisado: a chamada ao LLM falhou em todos."
            )

        console.rule(
            f"[bold green]RAG-Reviewer concluído: {self._build_summary(violacoes)}[/bold green]"
        )
        return violacoes

    # ── Internos ──────────────────────────────────────────────────────────

    def _review_all_contexts(
        self, contextos: list[RetrievedContext]
    ) -> tuple[ViolationList, list[str]]:
        """Uma chamada ao LLM por arquivo. Falha num arquivo não derruba os demais."""
        violacoes: ViolationList = []
        nao_revisados: list[str] = []
        for contexto in contextos:
            try:
                encontradas = self._review_with_retry(contexto)
            except Exception as exc:  # noqa: BLE001 - registra e segue com os demais
                console.log(
                    f"[red]Falha ao revisar {contexto.file_diff.filename}:[/red] {exc}"
                )
                nao_revisados.append(contexto.file_diff.filename)
                continue
            violacoes.extend((contexto.file_diff, v) for v in encontradas)
        return violacoes, nao_revisados

    def _review_with_retry(self, contexto: RetrievedContext) -> list[Violation]:
        """Chama o LLM; num rate limit (429) espera pouco e tenta uma única vez de novo."""
        try:
            return self._llm.review(contexto)
        except Exception as exc:
            if type(exc).__name__ != "RateLimitError":
                raise
            espera = _espera_rate_limit(exc)
            console.log(
                f"[yellow]Rate limit da Groq; aguardando {espera:.0f}s "
                "e tentando uma vez de novo.[/yellow]"
            )
            time.sleep(espera)
            return self._llm.review(contexto)

    def _get_publisher(self):
        if self._publisher is None:
            from rag_reviewer.github_publisher import GitHubPublisher

            self._publisher = GitHubPublisher()
        return self._publisher

    @staticmethod
    def _build_summary(violacoes: ViolationList) -> str:
        if not violacoes:
            return "nenhuma violação detectada"
        por_severidade: dict[str, int] = {}
        for _, v in violacoes:
            por_severidade[v.severity] = por_severidade.get(v.severity, 0) + 1
        partes = [f"{n} {sev}" for sev, n in sorted(por_severidade.items())]
        return f"{len(violacoes)} violação(ões): {', '.join(partes)}"


def _espera_rate_limit(exc: Exception) -> float:
    """Segundos de espera sugeridos pelo cabeçalho `retry-after`, no máximo 30."""
    cabecalhos = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        return min(float(cabecalhos.get("retry-after")), _ESPERA_RATE_LIMIT_MAXIMA)
    except (TypeError, ValueError):
        return _ESPERA_RATE_LIMIT_PADRAO
```

- [ ] **Step 3: `rag_reviewer/main.py`**

```python
"""
main.py - Ponto de entrada do GitHub Action: `python -m rag_reviewer.main`.
"""

from __future__ import annotations

import sys

from rich.console import Console

from rag_reviewer.reviewer import RAGReviewer

console = Console()


def main() -> None:
    try:
        RAGReviewer().run()
    except Exception as exc:  # noqa: BLE001 - o job precisa falhar com mensagem clara
        # show_locals=False: os locais podem conter tokens e chaves de API.
        console.print_exception(show_locals=False)
        console.log(f"[bold red]Erro fatal no RAG-Reviewer:[/bold red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar unitarios**

Run: `.venv/Scripts/python -m pytest tests/unit/test_reviewer.py -q`
Expected: PASS.

- [ ] **Step 5: Teste de integracao e Makefile**

```bash
export MSYS_NO_PATHCONV=1
mkdir -p tests/integration
git show origin/main-completa:tests/integration/__init__.py > tests/integration/__init__.py
git show origin/main-completa:tests/integration/test_rag_pipeline.py > tests/integration/test_rag_pipeline.py
```
Ajustes no arquivo portado: apagar `test_run_requests_changes_on_critical_violation`; trocar `severity="CRITICAL"` por `"HIGH"` onde restar; onde o teste do `RAGReviewer` mocka `retriever.retrieve_for_diff`, manter. Remover qualquer referencia a `request_changes` e a "normas organizacionais". No `Makefile`, depois do alvo `test-unit`:

```make
test-integration:
	$(PYTHON) -m pytest tests/integration/ -v
```
(adicionar `test-integration` na linha `.PHONY`).

Run: `.venv/Scripts/python -m pytest tests/integration -q`
Expected: PASS. Falhas por assinatura (`publish(..., unreviewed=..., model=...)`) se corrigem no teste, nunca no codigo.

- [ ] **Step 6: Registrar e commitar**

`| rag_reviewer/reviewer.py | RAGReviewer.run/_review_all_contexts/_review_with_retry | Orquestra diff, recuperação, LLM por arquivo e publicação; falha num arquivo vira "não revisado"; um retry curto em 429; falha em todos faz o job falhar |`
`| rag_reviewer/main.py | main | Entrada do Action (python -m rag_reviewer.main), sem show_locals |`
`| tests/integration/ | test_rag_pipeline | Fluxo ponta a ponta com GitHub, Qdrant e Groq simulados |`

```bash
git add rag_reviewer/reviewer.py rag_reviewer/main.py tests/unit/test_reviewer.py tests/integration Makefile docs/DECISIONS.md
git commit -m "feat: orquestrador e entrada do Action, sem bloqueio do PR (D-011)"
```

---

### Task 6: Workflow do GitHub Actions

**Files:**
- Create: `.github/workflows/rag_reviewer.yml`
- Create: `tests/unit/test_workflow_yaml.py`
- Modify: `docs/DECISIONS.md` (tabela)

- [ ] **Step 1: Teste que falha**

```python
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
    assert "QDRANT_COLLECTION: pep8_chunks" in TEXTO


def test_sem_bloqueio_e_sem_variaveis_sem_uso():
    assert "BLOCK_ON_CRITICAL" not in TEXTO
    assert "PR_BASE_SHA" not in TEXTO
```

Run: `.venv/Scripts/python -m pytest tests/unit/test_workflow_yaml.py -q`
Expected: FAIL (arquivo nao existe).

- [ ] **Step 2: Criar `.github/workflows/rag_reviewer.yml`**

```yaml
name: RAG-Reviewer

on:
  pull_request:
    types: [opened, synchronize, reopened]
    paths:
      - "**/*.py"

permissions:
  contents: read
  pull-requests: write   # necessário para publicar a review

# Um push novo cancela a execução anterior do mesmo PR
concurrency:
  group: rag-reviewer-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  review:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout do repositório
        uses: actions/checkout@v4

      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      # torch só CPU: a build padrão traz CUDA e passa de 2 GB
      - name: Instalar dependências
        run: |
          pip install torch --index-url https://download.pytorch.org/whl/cpu
          pip install -r requirements.txt

      # O modelo de embedding multilíngue (ADR-002) tem ~470MB
      - name: Cache do modelo de embedding
        uses: actions/cache@v4
        with:
          path: ~/.cache/huggingface
          key: hf-${{ hashFiles('requirements.txt') }}

      - name: Executar RAG-Reviewer
        env:
          GITHUB_TOKEN:       ${{ secrets.GITHUB_TOKEN }}
          GROQ_API_KEY:       ${{ secrets.GROQ_API_KEY }}
          QDRANT_URL:         ${{ secrets.QDRANT_URL }}
          QDRANT_API_KEY:     ${{ secrets.QDRANT_API_KEY }}
          QDRANT_COLLECTION:  pep8_chunks
          PR_NUMBER:          ${{ github.event.pull_request.number }}
          REPO_FULL_NAME:     ${{ github.repository }}
          PR_HEAD_SHA:        ${{ github.event.pull_request.head.sha }}
        run: python -m rag_reviewer.main
```

- [ ] **Step 3: Rodar e commitar**

Run: `.venv/Scripts/python -m pytest tests/unit/test_workflow_yaml.py -q` -> PASS.
Tabela de D-011: `| .github/workflows/rag_reviewer.yml | job review | Roda o revisor no pull_request (opened/synchronize/reopened) em .py; torch CPU, cache do modelo, cancela execução anterior do mesmo PR |`

```bash
git add .github/workflows/rag_reviewer.yml tests/unit/test_workflow_yaml.py docs/DECISIONS.md
git commit -m "feat: GitHub Action do RAG-Reviewer (D-011)"
```

---

### Task 7: Documentacao

**Files:**
- Modify: `arquitetura.md`, `README.md`, `docs/STATUS.md`, `docs/GUIA-DO-PROJETO.md`, `docs/TODO-FUTURO.md`, `docs/DECISIONS.md`, `docs/RELATORIO-RESULTADOS.md` (so a linha da secao 8 sobre `request_changes`)

- [ ] **Step 1: `arquitetura.md`**

`grep -n "CRITICAL\|BLOCK_ON_CRITICAL\|request_changes\|REQUEST_CHANGES" arquitetura.md` e reescrever cada trecho: severidades `HIGH | MEDIUM | LOW`; o publisher cria uma review `COMMENT` e nunca `REQUEST_CHANGES`; a tabela de configuracao perde `BLOCK_ON_CRITICAL`; o diagrama de sequencia perde o ramo "Has CRITICAL violations"; o schema de saida ganha `"ambiguous"`. Ao final, `grep` nao deve achar nenhuma das quatro expressoes.

- [ ] **Step 2: `docs/RELATORIO-RESULTADOS.md` secao 8**

Na linha da tabela sobre `request_changes`, trocar por: "`request_changes` | O Action nunca bloqueia (D-011); a avaliacao conta qualquer sinalizacao no gate". Na tabela da secao 8, as linhas "Gatilho", "DiffCollector", "GitHubPublisher" passam a dizer que foram implementadas em D-011 e exercitadas no teste em PR real (resultado na secao propria, tarefa 10).

- [ ] **Step 3: `README.md`, `docs/GUIA-DO-PROJETO.md`, `docs/STATUS.md`, `docs/TODO-FUTURO.md`**

README: secao curta "Workflow do GitHub" (gatilho, secrets necessarios, `QDRANT_COLLECTION=pep8_chunks`, review sempre `COMMENT`, severidades). GUIA: acrescentar o fluxo do Action. STATUS: item D-011 em andamento. TODO-FUTURO: F-004 recebe "Implementado em D-011 (campo `ambiguous`)".

- [ ] **Step 4: Registrar e commitar**

`| arquitetura.md, README.md, docs/ | CRITICAL/BLOCK_ON_CRITICAL removidos, secao do workflow | A documentacao descreve a review COMMENT e o Action |`

```bash
git add arquitetura.md README.md docs
git commit -m "docs: workflow do GitHub, sem CRITICAL e sem bloqueio (D-011)"
```

---

### Task 8: Verificacao completa e PR da implementacao

- [ ] **Step 1: Suite inteira**

Run: `.venv/Scripts/python -m pytest tests -q --deselect tests/unit/test_embedder.py`
Expected: PASS. (`test_embedder.py::TestImportError` ja falhava antes por causa do ambiente.)

- [ ] **Step 2: Conferir que nada indevido foi tocado**

Run: `git diff --stat main -- rag_reviewer/vector_store.py rag_reviewer/embedder.py rag_reviewer/sparse_encoder.py indexer evaluation docs/style_guides`
Expected: sem alteracao nesses caminhos.

- [ ] **Step 3: Conferir o prompt e a avaliacao**

Run: `grep -rn "CRITICAL" rag_reviewer evaluation .github --include=*.py --include=*.txt --include=*.yml`
Expected: nenhuma ocorrencia.

- [ ] **Step 4: Push e PR**

```bash
git push -u origin feat/workflow-github
gh pr create --base main --head feat/workflow-github --title "D-011: workflow do GitHub (revisao COMMENT, sem CRITICAL)" --body "<resumo + testes + itens em aberto: rodada 3 e teste em PR real>"
```
Parar aqui e esperar o autor confirmar o merge. O corpo do PR termina com a linha de atribuicao exigida pela sessao.

---

### Task 9: Rodada 3 da avaliacao (so quando o autor pedir)

**Contexto:** retirar `CRITICAL` e acrescentar `ambiguous` mudou o prompt; os numeros da rodada 2 (P 0,8556, R 0,7857, F1 0,8191) nao valem para ele.

- [ ] **Step 1: Pre-condicoes**

Autor pediu a rodada; RAM livre; cota da Groq livre (janela deslizante: uma chamada de 5 tokens que passe nao basta; a rodada custa ~130 mil tokens e a cota e de 200 mil por 24 h, entao confirmar que a rodada 2 e a linha de base ja saíram da janela).

- [ ] **Step 2: Rodar em segundo plano**

```bash
QDRANT_COLLECTION=pep8_chunks PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python -m evaluation.run_evaluation --repeticoes 1 --output evaluation/results_realista_r3.json
```
Retoma do `evaluation/.eval_checkpoint.json` se cair (o hash inclui os prompts novos, entao o checkpoint antigo e descartado). Nao relancar sozinho depois de uma queda; so a pedido.

- [ ] **Step 3: Comparar com a rodada 2 e registrar**

Comparar P, R, F1, gate e contagem de ambiguas sinalizadas. Criterio: nenhuma queda relevante de F1; queda fica registrada e investigada. Acrescentar a secao "Rodada 3" em `docs/RELATORIO-RESULTADOS.md` e uma subsecao em D-011. Commit `docs: rodada 3 de D-011 ...`.

---

### Task 10: PRs de teste no GitHub (depois do merge)

**Files:**
- Create: `scripts/montar_prs_demo.py`, `scripts/conferir_prs_demo.py`
- Create: `tests/unit/test_prs_demo.py`

**PRs escolhidos** (cobrem arquivo novo e modificado, ambiguidade, hard negatives e um PR sem violacao): `PR-003` (violacoes; 1 novo e 1 modificado), `PR-007` (5 violacoes e 1 ambigua), `PR-021` (sem violacao; arquivo modificado com hard negatives). Sao 4 arquivos, ~4 chamadas ao LLM (~15 mil tokens).

**Interfaces:**
- Produces: `reconstruir_antes(source_after: str, patch: str) -> str`; `linha_na_posicao(patch: str, posicao: int) -> str | None`.

- [ ] **Step 1: Testes de `reconstruir_antes` e `linha_na_posicao` (falham)**

`tests/unit/test_prs_demo.py`:

```python
from scripts.montar_prs_demo import reconstruir_antes
from scripts.conferir_prs_demo import linha_na_posicao

DEPOIS = "a = 1\nb = 2\nc = 3\nd = 4\n"
PATCH = "@@ -1,3 +1,4 @@\n a = 1\n-x = 0\n+b = 2\n c = 3\n+d = 4"


def test_reconstruir_antes_desfaz_adicoes_e_restaura_remocoes():
    assert reconstruir_antes(DEPOIS, PATCH) == "a = 1\nx = 0\nc = 3\n"


def test_linha_na_posicao():
    assert linha_na_posicao(PATCH, 1) is None          # cabecalho do hunk
    assert linha_na_posicao(PATCH, 3) == "b = 2"        # a linha removida nao conta
    assert linha_na_posicao(PATCH, 5) == "d = 4"
    assert linha_na_posicao(PATCH, 4) is None          # contexto
```
(criar `scripts/__init__.py` vazio se o import falhar.)

- [ ] **Step 2: `scripts/montar_prs_demo.py`**

```python
"""
montar_prs_demo.py - Monta as branches dos PRs de teste do workflow (D-011).

Para cada PR do dataset escolhido:
  - `demo/base` recebe o estado "antes" dos arquivos modificados;
  - `demo/<pr_id>` parte de `demo/base` e recebe o estado "depois".
Não abre o PR: quem abre é o autor (gh pr create), um a um.

Uso:
    python -m scripts.montar_prs_demo PR-003 PR-007 PR-021
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
_DATASET = _RAIZ / "evaluation" / "dataset" / "pilot_dataset.json"
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def reconstruir_antes(source_after: str, patch: str) -> str:
    """Desfaz o patch sobre o arquivo `depois`: tira as adições e devolve as remoções."""
    depois = source_after.splitlines()
    saida: list[str] = []
    cursor = 0  # índice em `depois`
    linhas = patch.splitlines()
    i = 0
    while i < len(linhas):
        casou = _HUNK.match(linhas[i])
        if not casou:
            i += 1
            continue
        inicio_novo = int(casou.group(3)) - 1
        saida.extend(depois[cursor:inicio_novo])
        cursor = inicio_novo
        i += 1
        while i < len(linhas) and not linhas[i].startswith("@@"):
            marca, texto = linhas[i][:1], linhas[i][1:]
            if marca == "+":
                cursor += 1
            elif marca == "-":
                saida.append(texto)
            elif marca == " ":
                saida.append(depois[cursor])
                cursor += 1
            i += 1
    saida.extend(depois[cursor:])
    return "\n".join(saida) + "\n"


def _git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=_RAIZ, check=True)


def _escrever(caminho: str, conteudo: str) -> None:
    destino = _RAIZ / caminho
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8", newline="\n")


def main() -> None:
    ids = sys.argv[1:]
    dataset = {pr["pr_id"]: pr for pr in json.loads(_DATASET.read_text(encoding="utf-8"))}
    _git("checkout", "-B", "demo/base", "main")
    for pr_id in ids:
        for arq in dataset[pr_id]["files"]:
            if arq["status"] == "modified":
                _escrever(arq["filename"], reconstruir_antes(arq["source_after"], arq["patch"]))
    _git("add", "app")
    _git("commit", "-m", "demo: estado anterior dos arquivos modificados")
    for pr_id in ids:
        _git("checkout", "-B", f"demo/{pr_id.lower()}", "demo/base")
        for arq in dataset[pr_id]["files"]:
            depois = arq.get("source_after") or "\n".join(
                l["line"] for l in arq["added_lines"]
            ) + "\n"
            _escrever(arq["filename"], depois)
        _git("add", "app")
        _git("commit", "-m", f"demo: {pr_id}")
    _git("checkout", "main")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: `scripts/conferir_prs_demo.py`**

```python
"""
conferir_prs_demo.py - Confere as reviews dos PRs de teste contra o gabarito.

Para cada PR do GitHub informado, lê os comentários inline da review (gh api),
traduz cada comentário para a linha adicionada (posição -> texto) e compara com
os rótulos do dataset: linhas sinalizadas contra `viola`, ambíguas à parte.

Uso:
    python -m scripts.conferir_prs_demo PR-003=12 PR-007=13 PR-021=14
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
_DATASET = _RAIZ / "evaluation" / "dataset" / "pilot_dataset.json"


def linha_na_posicao(patch: str, posicao: int) -> str | None:
    """Texto da linha adicionada na posição do diff (a mesma contagem do publisher)."""
    atual = 0
    for linha in patch.splitlines():
        if linha.startswith("-"):
            continue
        atual += 1
        if atual == posicao:
            if linha.startswith("+") and not linha.startswith("+++"):
                return linha[1:]
            return None
    return None


def _gh(caminho: str) -> list[dict]:
    saida = subprocess.run(
        ["gh", "api", "--paginate", caminho],
        cwd=_RAIZ, check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    # --paginate concatena arrays JSON: "[...][...]"
    return [item for bloco in saida.replace("][", "]\n[").splitlines() for item in json.loads(bloco)]


def main() -> None:
    repo = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        cwd=_RAIZ, check=True, capture_output=True, text=True,
    ).stdout.strip()
    dataset = {pr["pr_id"]: pr for pr in json.loads(_DATASET.read_text(encoding="utf-8"))}
    total = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for par in sys.argv[1:]:
        pr_id, numero = par.split("=")
        arquivos = {f["filename"]: f for f in _gh(f"repos/{repo}/pulls/{numero}/files")}
        sinalizadas: set[tuple[str, str]] = set()
        for c in _gh(f"repos/{repo}/pulls/{numero}/comments"):
            arq = arquivos.get(c["path"])
            texto = linha_na_posicao(arq["patch"], c["position"]) if arq and c.get("position") else None
            if texto is not None:
                sinalizadas.add((c["path"], texto.strip()))
        print(f"\n== {pr_id} (PR #{numero})")
        for arq in dataset[pr_id]["files"]:
            for l in arq["added_lines"]:
                if l.get("ambiguo"):
                    print(f"  ambigua {'sinalizada' if (arq['filename'], l['line'].strip()) in sinalizadas else 'nao sinalizada'}: {l['line']}")
                    continue
                sinal = (arq["filename"], l["line"].strip()) in sinalizadas
                celula = ("tp" if sinal else "fn") if l["viola"] else ("fp" if sinal else "tn")
                total[celula] += 1
                if celula in ("fp", "fn"):
                    print(f"  {celula.upper()}: {arq['filename']}: {l['line']}")
    print("\nTotal:", total)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar os testes e commitar os scripts**

Run: `.venv/Scripts/python -m pytest tests/unit/test_prs_demo.py -q` -> PASS.
```bash
git add scripts tests/unit/test_prs_demo.py docs/DECISIONS.md
git commit -m "feat: scripts dos PRs de teste do workflow (D-011)"
```
(Esses scripts podem ir no PR da implementacao, tarefa 8, se ja existirem antes do merge.)

- [ ] **Step 5: Pre-condicoes do teste real (autor confirma cada acao que publica no GitHub)**

1. O workflow ja esta na `main` (PR da implementacao mesclado).
2. Conferir que o secret `QDRANT_URL` aponta para o cluster com a `pep8_chunks`: acionar o Action uma vez e ler o log; `VectorStore.assert_model_matches` falha com mensagem clara se a colecao estiver vazia ou for de outro modelo.
3. Rodar `python -m scripts.montar_prs_demo PR-003 PR-007 PR-021`, `git push origin demo/base demo/pr-003 demo/pr-007 demo/pr-021`.
4. Para cada PR, com a confirmacao do autor: `gh pr create --base demo/base --head demo/pr-003 --title "demo: PR-003" --body "PR de teste do RAG-Reviewer (D-011)"`.

- [ ] **Step 6: Acompanhar e conferir**

`gh run list --workflow rag_reviewer.yml`, `gh run view <id> --log` (tempo do job, erro de secret, tempo de instalacao). Depois `python -m scripts.conferir_prs_demo PR-003=<n> PR-007=<n> PR-021=<n>`. Comparar a matriz com a da avaliacao local para os mesmos PRs (`evaluation/results_realista_r2.json`, ou o r3 se existir) e anotar as diferencas.

- [ ] **Step 7: Verificar na documentacao e no teste real o formato `position`**

Se a API recusar `position` (422 repetido), trocar `position` por `line` + `side: "RIGHT"` no `_build_review_comments` (numero da linha no arquivo novo, que sai dos cabecalhos `@@ -a,b +c,d @@`). Registrar a decisao em D-011.

- [ ] **Step 8: Encerrar**

Fechar os PRs de teste (`gh pr close <n> --delete-branch`), apagar `demo/base` local e remota, registrar o resultado em `docs/RELATORIO-RESULTADOS.md` (nova secao "Teste em PR real"), em D-011 e em `docs/STATUS.md`. Commit e PR de documentacao.

---

## Self-Review

**Cobertura do spec:** componentes (tarefas 2 a 6), fluxo e falhas por arquivo (5), comentario e ambiguidade (1, 4), correcoes do publisher: posicao, 422, repeticao (4), emojis e `show_locals` (4, 5), fim do `CRITICAL` (1, 7), consistencia com a avaliacao e rodada 3 (9), teste em PR real e verificacoes do spec (10), testes automatizados (todas), documentacao (7 e a tabela de cada tarefa). Lacuna conhecida: o spec estimava 10 a 15 chamadas no teste real; o plano usa 4 arquivos, ~4 chamadas (menos custo, mesma cobertura de tipos de caso).

**Placeholders:** nenhum passo descreve algo sem mostrar como. Os ajustes de teste portados (tarefas 2 e 5) dizem exatamente quais testes mudam e por que.

**Consistencia de tipos:** `Violation.ambiguous` (1) e usado em `_format_inline_comment` (4); `publish(violations, pr_diff, unreviewed, model)` (4) e chamado igual em `reviewer.py` (5); `retrieve_for_diff` (3) e chamado em `reviewer.py` (5); `_find_diff_position(patch, line_content, usadas)` (4) e espelhado por `linha_na_posicao` (10).
