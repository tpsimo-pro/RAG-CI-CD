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
- Reintroduzir normas além da PEP 8 (os guias internos `coding_standards.md` e
  `architecture_patterns.md` saíram do repositório em D-009; estão no
  histórico do git, antes de `339e75a`).

---

## F-003 — Dataset com Pull Requests reais

**Origem:** D-004, que registra o dataset sintético como ameaça à validade
externa.

- Substituir ou complementar os PRs sintéticos por **diffs reais** de
  repositórios open source em Python.
- Rotulação **independente** (não feita pelo autor do sistema), para reduzir
  viés de construção do gabarito.

---

## F-004 — Workflow: sinalizar ambiguidade da norma

Em D-010 três linhas do dataset ficaram como ambíguas (literal global em
minúsculas, como `retry_limit = 3`): o texto da PEP 8 não diz se é uma
constante, então não há rótulo certo. No workflow real o revisor não deve
afirmar a violação nesses casos. A resposta do LLM precisa de um campo (ou um
texto na `violation_description`) que diga que pode haver ambiguidade, e o
comentário publicado no PR deve trazer isso ao desenvolvedor. A avaliação já
reporta quantas linhas ambíguas o modelo sinalizou (`published.ambiguous`).

**Implementado em D-011:** a resposta do LLM ganhou o campo `ambiguous`, que força
severidade `LOW`, e o comentário publicado avisa da possível ambiguidade.

---

## F-005 — Ruff como detector e como alternativa ao workflow

Registrado em 2026-10-09, não medido nem implementado.

**O que o Ruff faz sozinho num PR do GitHub.** Detecta violações e, com
`--output-format github`, cria anotações inline nas linhas do diff; mostra o código
da regra (por exemplo `E501`), uma mensagem curta e o link da documentação, e
corrige o que tem correção automática (`--fix`).

**O que ele não entrega, e o workflow do RAG-Reviewer entrega.** A seção da PEP 8
citada (o Ruff traz o código da regra, não a seção), a severidade
`HIGH/MEDIUM/LOW` (a review é sempre `COMMENT`, nunca bloqueia), uma sugestão específica
da linha, o comentário de revisão em thread (as anotações do Ruff não são uma
review; isso exigiria outra ferramenta, como o reviewdog) e o julgamento de casos
fora das regras do Ruff (docstring pública, `except:` tolerado, ambiguidade de
constantes em minúsculas; na avaliação esses três precisaram de checagem própria
ou de tratamento à parte).

**Lacuna na avaliação.** O Ruff é o oráculo dos rótulos do dataset (D-010), então
acerta quase 100% por construção. O Ruff nunca foi medido como detector no mesmo
dataset, e por isso não existe comparação justa entre Ruff e RAG-Reviewer. A
comparação custaria zero de cota da Groq. Enquanto não for feita, o argumento
sustentável é posicionar o RAG-Reviewer como complemento do Ruff (norma citada,
severidade, sugestão e casos de julgamento), não como substituto.
