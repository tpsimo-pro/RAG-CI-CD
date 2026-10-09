# Status do projeto

Atualizado em 2026-10-09. Branch `feat/dataset-realista`, a partir da `main`
com D-009 mesclado (PR #13). Ainda sem PR aberto para esta branch.

Fluxo do sistema e das avaliações: `docs/GUIA-DO-PROJETO.md`.
Resultados: `docs/RELATORIO-RESULTADOS.md`. Decisões: `docs/DECISIONS.md`.

## Onde estamos

D-010 implementado: dataset realista de 25 PRs e 35 arquivos (21 novos, 14
modificados), 23 normas da PEP 8, ensaio do workflow do GitHub. A **rodada 1**
da avaliação oficial deu P 0,80, R 0,79, F1 0,79. A investigação dos 40 erros
achou 15 erros de rótulo do dataset; foram corrigidos (D-010, "Revisão após a
primeira rodada") e a **rodada 2**, com o dataset corrigido, deu **P 0,86, R 0,79,
F1 0,82** (metas atingidas; gate TP 19, FP 4, FN 1, TN 1). Com a norma no
contexto o recall é 0,87; sem ela, 0,69. A **linha de base sem recuperação** (branch
`feat/baseline-sem-recuperacao`) deu P 0,77, R 0,73, F1 0,75: o RAG soma cerca de 7
pontos de F1 sobre o conhecimento prévio do modelo.

## Feito nesta branch

| O quê | Commit |
|---|---|
| Spec do dataset realista | `169058e` |
| Catálogo único das 23 normas, com teste contra o ruff e o corpus | `975ce0a` |
| Validador v2 (ruff como oráculo, patch com hunks) | `5b55d76` |
| Harness para PRs de vários arquivos | `a92ea49` |
| Dataset de 25 PRs, 35 arquivos | `bb7d405` |
| Dataset corrigido (docstrings, `import_ordem`, negativos, ambiguidade) | `9adc83a` |
| SCHEMA v2, D-010 com a revisão dos rótulos | `cad91fe` |
| Cobertura do contexto entregue ao LLM e teste de chunks menores | `2eaa103` |
| Relatório da rodada 1, README, STATUS | `365016e` |
| Rodada 2, parsing de JSON truncado, relatório | este commit |

## Falta

Abrir o PR de `feat/dataset-realista`. Os FPs da rodada 2 sem causa registrada
(`LoadFile(...)`, `sys.stdout.write(...)`, `def __init__(self, sku, qty):`,
`round(..., ndigits=2)` e 3 linhas longas) não foram investigados.

## Decisões em aberto

- **Falhas do modelo no `except`.** `except Exception:` e o `except:` tolerado
  (com `logger.exception` ou `raise`) são acusados como violação. Ajustar prompt
  ou corpus exige nova rodada.
- **Ambiguidade no workflow.** O modelo deve sinalizar casos ambíguos da norma
  (`docs/TODO-FUTURO.md`, F-004).
- **Modelo de embedding.** ADR-002 e ADR-004 têm uma nota de D-009, mas ainda citam
  números do corpus antigo.
- **`requirements-dev.txt`.** O autor tem uma alteração local pedindo ruff 0.16.10;
  o `.venv` usa 0.4.9, e os códigos do catálogo são verificados contra o instalado.
- **Seu `.env` local** ainda aponta `QDRANT_COLLECTION=style_guide_chunks` (corpus
  antigo); a coleção atual é `pep8_chunks`.

## Limitações conhecidas

- Dataset sintético escrito pelo autor (D-004); erros de rótulo achados depois do
  resultado, corrigidos com base no texto da PEP 8.
- Uma repetição por rodada (D-005); cerca de 4 positivas por norma.
- A norma chega ao LLM em 54% das linhas positivas; a recuperação limita o recall.
- A `suggestion` e a `severity` não são medidas.
- Um teste, `test_embedder.py::TestImportError`, falha por causa do ambiente
  local (já falhava antes de D-009).
