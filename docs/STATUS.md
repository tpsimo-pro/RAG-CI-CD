# Status do projeto

Atualizado em 2026-10-08. Branch `feat/corpus-pep8`, empilhada em
`feat/dataset-conforme-corpus` (PR #12 aberto para a `main`, não mesclado).
Nada desta rodada final foi commitado: o working tree tem o relatório, o
STATUS, o README e `evaluation/results_pep8.json`.

Fluxo do sistema e das avaliações: `docs/GUIA-DO-PROJETO.md`.
Resultados: `docs/RELATORIO-RESULTADOS.md`.

## Onde estamos

D-009 concluída. O corpus indexado é só a PEP 8 completa, em inglês, sem chunks
redundantes. A avaliação oficial no corpus novo atingiu as três metas do TCC:
Precisão 0,96, Recall 0,97, F1 0,97 (D-008: 0,87, 0,88, 0,88). A comparação
não é um a um: mudaram o corpus, as regras de exceção e o prompt. Ver a seção 7
do relatório.

## Feito nesta branch

| O quê | Commit |
|---|---|
| Spec e corpus: `pep-0008.md` no lugar dos três guias; carregador e chunker corrigidos | `e4057e8`, `339e75a` |
| Gabarito e citação de normas apontam a PEP 8 | `36209f9` |
| Dataset, validador e conformidade reapontados; `except_nu` no lugar de `captura_*` | `88f94db` |
| Prompts e SCHEMA | `33e10c4` |
| D-009, README, guia, arquitetura, ablação de recuperação | `151880b` |
| Avaliação oficial, relatório, STATUS e README com resultados | não commitado |

## Decisões em aberto

- **Linha de base sem recuperação.** O recall de detecção (0,97) é maior que o
  recall@5 de recuperação (0,74). Sem medir o mesmo prompt sem os chunks, não
  se separa o que o RAG contribui do que o modelo já sabe da PEP 8.
- **`except:` nu.** 4 dos 5 FPs da rodada: `except Exception:` (que a PEP 8
  recomenda) e os dois casos tolerados do `except:` nu. Ajustar prompt ou
  corpus exige nova rodada.
- **Modelo de embedding.** O MiniLM em inglês dá recall@1 de 0,43 contra 0,30
  do multilíngue, com recall@5 igual. ADR-002 e ADR-004 têm uma nota de
  D-009, mas ainda citam os números do corpus antigo.
- **Coleção do Qdrant.** O padrão passou a `pep8_chunks` em `config.py` e
  `.env.example`. O `.env` local do autor ainda aponta `style_guide_chunks`
  (corpus antigo, 52 pontos, mantida para a PR #12).
- **Ampliação do dataset.** Ao incluir outras normas da PEP 8, limitar a cerca
  de 50 PRs por rodada ou reduzir os tokens por chamada: 75 PRs não cabem na
  cota diária de 200 mil tokens da Groq.
- **Makefile.** `make eval-retrieval` mede a configuração antiga (sem
  `--per-line --hybrid`), e `make docker-qdrant` não é usado.

## Limitações conhecidas

- Dataset sintético escrito pelo autor (D-004).
- Uma repetição por rodada (D-005).
- `except_nu` tem 18 positivas, `nome_funcao` falha 1 de 16.
- Nome de função tem recall@5 de recuperação 0,00: a norma é prosa e a
  consulta é código.
- Um teste, `test_embedder.py::TestImportError`, falha por causa do ambiente
  local (já falhava antes de D-009).
