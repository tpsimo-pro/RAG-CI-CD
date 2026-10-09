# Status do projeto

Atualizado em 2026-10-09. Branch `feat/workflow-github`, a partir da `main` com
D-010 mesclado (PR #14).

Fluxo do sistema e das avaliações: `docs/GUIA-DO-PROJETO.md`.
Resultados: `docs/RELATORIO-RESULTADOS.md`. Decisões: `docs/DECISIONS.md`.

## Onde estamos

D-010 implementado: dataset realista de 25 PRs e 35 arquivos (21 novos, 14
modificados), 23 normas da PEP 8, ensaio do workflow do GitHub. A **rodada 1**
da avaliação oficial deu P 0,80, R 0,79, F1 0,79. A investigação dos 40 erros
achou 15 erros de rótulo do dataset; foram corrigidos (D-010, "Revisão após a
primeira rodada") e a **rodada 2**, com o dataset corrigido, deu **P 0,86, R 0,79,
F1 0,82** (metas atingidas; gate TP 19, FP 4, FN 1, TN 1). Com a norma no
contexto o recall é 0,87; sem ela, 0,69.

**D-011 (em andamento):** o workflow do GitHub. O Action coleta o diff do PR pela
API, recupera as normas da PEP 8, chama o LLM por arquivo e publica uma review
`COMMENT` com um comentário inline por violação (norma, severidade, como
corrigir). O PR nunca é bloqueado, `CRITICAL` deixou de existir e o modelo marca
`ambiguous` quando a PEP 8 não decide. O código está implementado e testado com
HTTP simulado; faltam a rodada 3 da avaliação (o prompt mudou) e o teste em PR real.
O registro de cada arquivo e função está na tabela de D-011 em `docs/DECISIONS.md`.

## Feito em D-010 (mesclado, PR #14)

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

- **Linha de base sem recuperação.** Sem ela não se separa a contribuição do RAG
  do conhecimento prévio do modelo sobre a PEP 8.
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
