# Status do projeto

Atualizado em 2026-10-08. Branch `feat/dataset-realista`, a partir da `main`
com D-009 mesclado (PR #13). Ainda sem PR aberto para esta branch.

Fluxo do sistema e das avaliações: `docs/GUIA-DO-PROJETO.md`.
Resultados: `docs/RELATORIO-RESULTADOS.md`. Decisões: `docs/DECISIONS.md`.

## Onde estamos

D-010 implementado: dataset realista de 25 PRs e 35 arquivos (21 novos, 14
modificados), 23 normas da PEP 8, ensaio do workflow do GitHub. A **rodada 1**
da avaliação oficial deu P 0,80, R 0,79, F1 0,79 (metas atingidas). A
investigação dos 40 erros achou 15 erros de rótulo do dataset; foram corrigidos
(D-010, "Revisão após a primeira rodada") e o dataset corrigido ainda **não foi
reavaliado**: falta a **rodada 2**.

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
| Relatório da rodada 1, README, STATUS | não commitado |

## Falta

1. **Rodada 2** da avaliação oficial com o dataset corrigido
   (`python -m evaluation.run_evaluation --output evaluation/results_realista_r2.json`
   com `QDRANT_COLLECTION=pep8_chunks`). Custa cerca de 130 mil tokens e a cota
   diária da Groq (200 mil, zera às 00:00 UTC) estava esgotada no dia 08/10 até
   as 20:00 no horário local. Rodar com memória livre: o processo foi encerrado
   pelo sistema por memória baixa em 3 execuções.
2. Cruzar `context_coverage` com as detecções da rodada 2 (a norma no contexto
   contra a norma ausente), para medir quanto o modelo depende do contexto.
3. Acrescentar a rodada 2 ao relatório e abrir o PR.

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
