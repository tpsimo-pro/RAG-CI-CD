# Backlog futuro — RAG-Reviewer

Incrementos conscientemente adiados para depois que a **estrutura base** do
estudo de validação estiver funcionando ponta a ponta (LLM e Qdrant reais,
matriz de confusão completa, regra única).

Isto **não** é lista de pendências de decisão — essas ficam em
[`DECISIONS.md`](DECISIONS.md). São ampliações já planejadas, com origem
rastreada até a decisão que as adiou.

---

## F-001 — Aprofundar o tratamento de variância do LLM

**Origem:** D-005, que fixou apenas o mínimo viável (temperatura `0.0`,
3 repetições, média ± desvio-padrão).

A ampliar depois da base pronta:

- Elevar as repetições para **10+**, permitindo **intervalos de confiança** em
  vez de desvio-padrão simples.
- **Análise de sensibilidade à temperatura** (`0.0` / `0.3` / `0.7`) — mostra
  o quanto a métrica depende do parâmetro, em vez de assumir que `0.0` é
  obviamente o melhor.
- Reportar a **matriz de confusão agregada** das repetições, além da mediana.
- Registrar a **concordância entre execuções**: quantas linhas mudam de
  classificação de uma run para outra. É a medida direta da instabilidade.
- Fixar e versionar o `seed`, caso o provedor passe a expô-lo.

---

## F-002 — Ampliar de 1 regra para N regras

**Origem:** D-002 (piloto de regra única) e a alternativa "par linha × regra"
rejeitada por ora em D-001.

- Migrar a unidade de avaliação de *linha* para **(linha × regra)** — a
  formulação já foi analisada em D-001, então a troca não exige rediscutir
  metodologia.
- Incluir **matriz de confusão entre regras**: mede o caso em que o sistema
  detecta a violação mas cita a norma errada, invisível na matriz binária.
- Reindexar `coding_standards.md` e `architecture_patterns.md`, hoje fora do
  escopo do piloto.

---

## F-003 — Dataset com Pull Requests reais

**Origem:** D-004, que registra o dataset sintético como ameaça à validade
externa.

- Substituir ou complementar os PRs sintéticos por **diffs reais** de
  repositórios open source em Python.
- Rotulação **independente** (não feita pelo autor do sistema), para reduzir
  viés de construção do gabarito.
