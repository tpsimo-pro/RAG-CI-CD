# Dataset de avaliação do piloto — Seção 5 (Comparações)

**Data:** 2026-09-01
**Autor:** Data Analyst (subagente)
**Território:** `evaluation/dataset/` (apenas). Não toquei em `evaluation/metrics.py`,
`evaluation/run_evaluation.py`, `rag_reviewer/`, `indexer/`, `tests/` ou
`docs/style_guides/`.

## O quê

Construí `evaluation/dataset/pilot_secao5.json`: 30 Pull Requests sintéticos em
Python, com **rotulação linha a linha de toda linha adicionada**, para o
piloto de avaliação que mede apenas a regra da Seção 5 do
`guia_python_pep8.md` (comparações booleanas e comparações com `None`), por
D-001/D-002/D-004 em `docs/DECISIONS.md`.

Resultado (saída real do script de verificação, ver seção "Como" abaixo):

| Métrica | Exigido (D-004) | Obtido |
|---|---|---|
| Pull Requests | 30 | **30** |
| PRs de controle (sem violação) | 8 | **8** |
| PRs com ≥1 violação | 22 | **22** |
| Linhas adicionadas (N) | 290–310 | **300** |
| Linhas positivas | 60 | **60** |
| — sub-regra booleano | 30 | **30** |
| — sub-regra nulo | 30 | **30** |
| Linhas negativas | ~240 | **240** |
| — negativos difíceis | 60 | **60** |

Todos os 8 padrões do catálogo mínimo de negativos difíceis aparecem em pelo
menos uma linha `hard_negative: true` (contagem real: 7–8 ocorrências cada,
ver saída do script).

Não repliquei o erro do dataset antigo (PR-009 marcando `if order is not
None:` como violação): verifiquei programaticamente que nenhuma linha
`viola: true` contém `is not None`/`is None` — essas construções, por
definição da regra, nunca são violação.

## Como

### 1. Leitura da fonte de verdade
Li `docs/DECISIONS.md` (D-001 a D-005) e `docs/style_guides/guia_python_pep8.md`
Seção 5 antes de desenhar qualquer linha, e inspecionei
`evaluation/dataset/prs_with_violations.json` para replicar o estilo (patch
como diff de "arquivo novo" `@@ -0,0 +1,N @@`, descrições em português,
identificadores em inglês, UTF-8 sem BOM) e confirmar o bug conhecido em
PR-009.

### 2. Desenho da composição
Distribuí os 60 positivos e as 30 linhas de contexto de PR de forma a bater
as contagens exatas exigidas por D-004 **sem forçar números redondos
artificiais por PR** (ver decisões de composição abaixo). Usei:
- 10 PRs focados em violação booleana (26 positivos: seis com 3, quatro com 2)
- 10 PRs focados em violação de nulo (mesma distribuição, 26 positivos)
- 2 PRs mistos (booleano + nulo no mesmo PR, 4 positivos cada) — fecham a
  soma em exatamente 30/30 e simulam um PR real que mexe em mais de um trecho
  de código com o mesmo problema de estilo.
- 8 PRs de controle, 100% negativos, para medir alarme falso no gate.

Cada um dos 30 PRs recebeu exatamente **2 negativos difíceis**, escolhidos
por rotação cíclica sobre os 8 padrões do catálogo mínimo — isso garante
cobertura de todos os padrões (7–8x cada) sem concentrar um padrão só em
poucos PRs.

### 3. Geração e validação de sintaxe
Escrevi um script gerador de uso único (fora do repositório, em scratchpad —
não é entregável) que:
1. Recebe cada PR como uma lista de tuplas `(linha, viola, sub_regra,
   hard_negative)`.
2. Deriva `added_lines` e o `patch` (unified diff) automaticamente a partir
   dessa lista — elimina o risco de o patch divergir do gabarito, que seria
   um jeito fácil de introduzir inconsistência manual.
3. Roda `ast.parse()` em cada snippet **antes** de gravar, garantindo que
   toda linha adicionada de todo PR forma Python sintaticamente válido (todo
   `if` tem corpo, indentação consistente).
4. Grava com `json.dump(..., ensure_ascii=False)` em UTF-8 sem BOM.

Isso resolveu um problema real que encontrei no meio do trabalho: um `if`
sem linha de corpo (ex.: dois negativos difíceis com `if` em sequência sem
corpo entre eles) é Python inválido. Corrigi transformando parte das linhas
de violação/negativo difícil em formas *standalone* (`return x == True`,
`assert x is None`) — realistas e igualmente diagnósticas da regra — sempre
que o orçamento de linhas do PR não permitia dar corpo a todo `if`.

### 4. Script de verificação
Escrevi `evaluation/dataset/validate_pilot_dataset.py`. Ele confere:
- Ausência de BOM e validade do JSON/UTF-8.
- Schema por linha: `sub_regra` não-nulo **apenas quando** `viola=true`;
  `hard_negative=true` **apenas quando** `viola=false`; `line` sem prefixo
  `+`.
- **Consistência semântica com o guia** (checagem que o dataset antigo não
  tinha): toda linha com `sub_regra="booleano"` de fato contém `== True` ou
  `== False`; toda linha com `sub_regra="nulo"` contém `!= None` ou
  `== None`; e nenhuma linha `viola=false` contém essas construções
  proibidas — isto é o que impede a reincidência do erro de PR-009.
- `patch` reconstituído bate exatamente com `added_lines`, e o cabeçalho do
  hunk é válido.
- Cada snippet de `added_lines` é Python válido (`ast.parse`).
- Nenhuma linha ultrapassa 79 colunas (evita ruído da Seção 1.1 nos
  negativos, conforme pedido nas restrições da tarefa).
- Todas as contagens de D-004 e a cobertura do catálogo mínimo de negativos
  difíceis.

**Saída real da execução** (`python evaluation/dataset/validate_pilot_dataset.py`):

```
Todas as verificacoes de schema passaram.

--- Resumo de contagens ---
PRs totais:              30
PRs de controle:         8
PRs com violacao:        22
Linhas adicionadas (N):  300
Linhas positivas:        60 (booleano=30, nulo=30)
Linhas negativas:        240
  dos quais dificeis:    60

Cobertura do catalogo minimo de negativos dificeis:
  is not None (if)             8x
  is None (if)                 8x
  flag simples (if x:)         8x
  not flag (if not x:)         8x
  != sem None                  7x
  == sem bool/None             7x
  assert ... is None           7x
  return ... is not None       7x
```

Saída de sucesso, exit code 0.

## Por quê

### Alternativas de composição consideradas e rejeitadas

- **22 PRs violadores com número fixo de positivos por PR (ex.: sempre 3
  linhas).** Rejeitei porque geraria PRs artificialmente uniformes (mesmo
  "formato" de violação repetido 22 vezes), o que é menos realista e
  facilita o sistema "decorar" um padrão de tamanho de PR em vez de
  identificar a violação em si. Optei por variar 2/3 positivos por PR e
  incluir 2 PRs mistos, o que também é o único jeito de fechar exatamente
  30/30 com 22 PRs sem sobrar ou faltar uma linha.
- **Negativos difíceis concentrados só nos PRs violadores.** O critério de
  D-004 ("60 negativos difíceis, ~25% dos negativos") não exige isso, e
  concentrar neles enfraqueceria a medição de falso-positivo nos PRs de
  controle — que é exatamente o cenário que testa se o revisor "vê
  fantasmas". Distribuí 2 negativos difíceis em **todos** os 30 PRs,
  incluindo os 8 de controle.
- **Todas as violações em forma `if condição: <corpo em linha separada>`.**
  Essa foi minha primeira tentativa e ela não fecha a aritmética de linhas:
  com 3 positivos + 2 negativos difíceis (ambos exigindo corpo) e um teto de
  10 linhas por PR, sobra uma linha a menos do que o necessário para dar
  corpo a todo `if`. Resolvi convertendo o positivo "sobrando" em uma forma
  standalone (`return expr == True`, `assert expr is None`) — construção
  real e igualmente reconhecível como violação da regra, já que o guia
  proíbe a comparação em si, não um tipo específico de statement que a
  contém.
- **Descrições sem acentuação.** Na primeira geração eu escrevi as
  descrições em português sem diacríticos (erro de execução, não de
  design). Corrigi antes de entregar porque o dataset antigo usa acentuação
  completa e a tarefa pede consistência de estilo; o arquivo é UTF-8 sem BOM
  e suporta os caracteres sem qualquer restrição.

### Decisões de composição que tomei por conta própria (não especificadas em D-004)

1. **Rotação cíclica dos 8 padrões do catálogo de negativos difíceis**, 2 por
   PR. D-004 pede cobertura mínima de 1x cada; escolhi uma distribuição quase
   uniforme (7–8x) em vez de, por exemplo, concentrar cada padrão em um
   único PR "canônico" — isso dá ao futuro cálculo de métricas por-padrão
   mais amostras por categoria de negativo difícil, caso o TCC queira
   quebrar a análise de FP por padrão sintático.
2. **2 PRs mistos** (booleano + nulo). Não exigido, mas realista — PRs reais
   frequentemente tocam mais de um trecho com o mesmo problema de estilo — e
   foi a peça que fechou 30/30 sem sobra.
3. **30 domínios de negócio distintos, sem repetição de arquivo**, cobrindo
   além dos sugeridos (auth, pagamentos, cache, relatórios, pedidos) mais
   ~25 outros (rate limiting, feature flags, auditoria, geolocalização,
   assinaturas, cupons, moderação de reviews, etc.) para reduzir qualquer
   viés de vocabulário que o LLM sob teste pudesse explorar.
4. **Checagem semântica automática linha-a-linha contra o guia** no script
   de validação (regex que confere que `sub_regra` bate com a construção
   textual da linha), além das invariantes de schema pedidas — fiz isso
   porque foi exatamente a ausência desse tipo de checagem que permitiu o
   erro de PR-009 passar despercebido no dataset antigo.

### Limitações e o que investigaria a seguir

- **Dataset sintético, autoria única** — ameaça à validade externa, já
  registrada como consequência de D-004 e a ser explicitada no texto do
  TCC; a substituição por PRs reais está em `TODO-FUTURO.md` (fora do meu
  escopo).
- Algumas linhas de violação/negativo difícil usam formas `return expr ==
  True` fora do `if` mostrado no exemplo do guia. Isso é uma decisão
  defensável (a regra proíbe a comparação, não o tipo de statement), mas
  vale documentar explicitamente no texto do TCC caso um avaliador humano
  estranhe a variação de forma.
- Não validei que o RAG efetivamente recupera a Seção 5 para cada tipo de
  violação — isso é comportamento do sistema sob teste, não do dataset, e
  cabe a `evaluation/run_evaluation.py` (fora do meu território).
- O script gerador (não versionado — ficou em scratchpad por instrução da
  tarefa) não é reprodutível a partir do repositório; se o time quiser
  regenerar ou auditar a proveniência exata do dataset, recomendo que
  alguém decida se vale a pena versioná-lo (por exemplo em
  `evaluation/dataset/scripts/`) num commit futuro — não fiz isso aqui para
  não expandir meu território além do pedido.

## Arquivos

- `c:\Users\Thiago-PC\Desktop\TCC\RAG-CI-CD\evaluation\dataset\pilot_secao5.json` — dataset final (30 PRs, novo arquivo).
- `c:\Users\Thiago-PC\Desktop\TCC\RAG-CI-CD\evaluation\dataset\validate_pilot_dataset.py` — script de verificação (schema + contagens + consistência semântica).
- `c:\Users\Thiago-PC\Desktop\TCC\RAG-CI-CD\docs\agent-reports\2026-09-01-data-analyst-dataset-piloto-secao5.md` — este relatório.
