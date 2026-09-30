# Status do projeto

Atualizado em 2026-09-29, 23:30. Branch `feat/dataset-conforme-corpus`,
com PR aberto para a `main`.

Fluxo do sistema e das avaliações: `docs/GUIA-DO-PROJETO.md`.
Resultados: `docs/RELATORIO-RESULTADOS.md`.

## Onde estamos

D-008 concluída. A avaliação oficial com o retriever corrigido atingiu as
três metas do TCC: Precisão 0,87, Recall 0,88, F1 0,88.

## Feito nesta branch

| O quê | Commit |
|---|---|
| Dataset de 75 PRs reescrito para cumprir o corpus inteiro (D-008) | até `b1d7b3b` |
| Primeira rodada oficial, com o bug do retriever: P 0,79 · R 0,64 · F1 0,71 | `b2eddf4` |
| Bug corrigido: a união do retriever guardava o score da primeira linha, não o maior. Norma no contexto do LLM: 25 -> 47 de 54 PRs violadores | `fb05820` |
| Ablação de recuperação (L0 a L4) refeita no dataset atual. L4: recall@5 0,84 | `74fb75a` |
| Guia do projeto | `5750473` |
| Rodada oficial final: P 0,87 · R 0,88 · F1 0,88, relatório, D-008 e README | este PR |

## Decisões em aberto

- **`captura_silenciosa`** (recall 0,13): aceitar como limitação do modelo
  ou ajustar o exemplo da cs 4.1 no corpus (exige nova rodada).
- **Modelo de embedding.** Na ablação nova, o MiniLM em inglês superou o
  multilíngue com o BM25 ativo (recall@5 0,89 contra 0,84). Trocar muda o
  ADR-002 e exige reindexar e rodar a avaliação de novo. ADR-002 e ADR-004
  ainda citam os números antigos.
- **Makefile.** `make eval-retrieval` mede a configuração antiga (sem
  `--per-line --hybrid`), e `make docker-qdrant` não é usado.

## Limitações conhecidas

- Nomes de função (`def CalculateTax`) não recuperam a norma de
  nomenclatura; o modelo acerta 14 de 16 mesmo assim.
- 11 dos 21 PRs de controle seriam bloqueados no gate, a maioria por FPs
  em normas fora do piloto (cs 1.1).
- Dataset sintético e escrito pelo autor (D-004). Calibração e avaliação
  no mesmo dataset.
- Uma rodada completa consome a cota diária de tokens da Groq.
