# Log de Decisões — RAG-Reviewer (TCC-2)

Registro das decisões de produto, metodologia e arquitetura acordadas.
Ordem cronológica. Cada decisão traz contexto, alternativas rejeitadas e
consequências, para que o TCC possa justificar o método adotado.

---

## D-001 — Unidade de avaliação: a linha adicionada

**Data:** 2026-09-01
**Status:** Aceita

### Contexto

O `todo-asap.txt` exige **matriz de confusão completa** (com verdadeiros
negativos), além de Precisão, Recall e F1-Score. A implementação anterior em
`evaluation/metrics.py` contabilizava apenas TP, FP e FN, porque a unidade de
avaliação era *"violação detectada em texto livre"* — um espaço aberto em que
"verdadeiro negativo" não tem denominador definível. Sem mudar a unidade, a
matriz de confusão é matematicamente impossível.

### Decisão

A unidade de avaliação passa a ser **cada linha adicionada no diff**
(os itens de `added_lines` de cada PR do dataset). Cada linha é uma instância
de classificação binária: *viola a regra do piloto* ou *não viola*.

| | Sistema sinalizou | Sistema não sinalizou |
|---|---|---|
| **Linha viola** | TP | FN |
| **Linha não viola** | FP | TN |

### Métricas derivadas

- **Primárias:** Precisão, Recall e F1-Score sobre a **classe positiva**
  (linhas que violam) — são as métricas que o TCC reporta e compara com as
  metas de §15.3 do planejamento (P >= 0.70, R >= 0.65, F1 >= 0.67).
- **Secundárias:** matriz de confusão completa e Acurácia. A acurácia é
  reportada por completude metodológica, mas **marcada explicitamente como
  não-representativa**: o conjunto é fortemente desbalanceado (a maioria das
  linhas é negativa), então a acurácia fica artificialmente alta e não
  discrimina desempenho.
- **Complementar (sem custo adicional):** agregação a nível de PR — *"o gate
  de CI/CD tomaria a decisão certa neste PR?"*. Deriva-se das mesmas
  detecções e conecta o resultado ao objetivo de CI/CD do trabalho.

### Alternativas consideradas e rejeitadas

- **Por Pull Request.** Cada PR seria uma instância (TN = PR limpo
  corretamente aprovado). Rejeitada como unidade *primária* por dois motivos:
  N pequeno demais (~30) para significância estatística, e não mede
  localização — acertar 1 de 3 violações de um PR contaria como acerto pleno.
  Mantida como métrica **complementar**, não como unidade primária.
- **Por par (linha × regra).** Formulação que escala para N regras sem trocar
  de metodologia. Rejeitada **por ora** por ser idêntica a "por linha" no
  piloto de regra única, ao custo de um gabarito N vezes maior. A migração
  para esta unidade é o caminho natural quando o estudo for ampliado — a
  implementação deve deixar essa extensão viável, sem implementá-la agora.

### Consequências

- `evaluation/metrics.py` precisa de TN e da matriz de confusão completa.
- O gabarito muda de forma: deixa de ser uma lista de violações e passa a ser
  **rotulação linha a linha** de todas as linhas adicionadas — inclusive as
  negativas, que hoje são implícitas.
- Passa a existir a necessidade de uma **regra de atribuição** explícita:
  como mapear uma violação retornada pelo LLM para uma linha específica do
  diff. O critério atual (substring case-insensitive, em
  `metrics.py::match_violation`) é frouxo demais para um estudo publicável e
  deve ser endurecido. **Resolvido em D-003.**

---

## D-002 — Regra do piloto: comparações com None e booleanos

**Data:** 2026-09-01
**Status:** Aceita

### Contexto

O `todo-asap.txt` determina um piloto imediato validando o pipeline RAG ponta
a ponta com **uma única regra**, para provar viabilidade antes de ampliar. O
dataset atual dispersa 17 violações por 6 regras distintas — 1 a 3 exemplos
por regra, insuficiente para qualquer significância.

### Decisão

A regra do piloto é a **Seção 5 do `guia_python_pep8.md` — Comparações**:

- **Comparações booleanas:** proibido `== True` e `== False`.
- **Comparações de nulos:** obrigatório `is` / `is not` ao comparar com `None`;
  proibido `!= None` e `== None`.

### Delimitação explícita de escopo

A Seção 5 do guia contém **três** sub-regras. O terceiro item — **Early Return
/ aninhamento excessivo** — está **fora do escopo do piloto**.

Motivo: comparação é uma propriedade sintática, local e inequívoca de uma
linha isolada; Early Return é uma propriedade estrutural e subjetiva de um
bloco, e o guia não define limiar para "aninhamento excessivo". Incluí-la
reintroduziria justamente a ambiguidade de rotulação que a escolha da Seção 5
existe para evitar, e violaria o "uma única regra" do todo.

### Justificativa da escolha

1. **Rotulação indiscutível.** O guia lista exemplos *literais* de correto e
   incorreto para ambas as sub-regras. O gabarito não depende de julgamento.
2. **Possui negativos difíceis.** `if x is not None:` (correto) convive com
   `if x != None:` (violação); `if flag:` (correto) com `if flag == True:`
   (violação). Isso garante conteúdo real nas quatro células da matriz de
   confusão — FP e FN podem de fato ocorrer.
3. **Testa compreensão semântica**, não casamento de string: o sistema
   precisa distinguir construções visualmente quase idênticas.
4. **Melhor cobertura no dataset atual** — já aparece em PR-001, PR-002 e
   PR-009, servindo de ponto de partida para a ampliação.

### Alternativas consideradas e rejeitadas

- **Seção 3.2 — `import *`.** Foi a primeira recomendação e foi revertida.
  Rotulação é 100% objetiva, mas *não possui negativos difíceis*: separar
  `from os.path import *` de `from os.path import join` é trivial, então
  FP e FN tendem a zero e a matriz sai **degenerada**, com duas células
  vazias. Prova viabilidade, mas produz resultado sem poder discriminativo.
- **Seção 2 — Nomenclatura.** Mais rica (exige inferir contexto), mas contém
  ambiguidade genuína: distinguir "constante de módulo" (`UPPER_SNAKE_CASE`)
  de "variável de módulo" (`snake_case`) depende da intenção do autor, não do
  código. Erro de rótulo seria contabilizado como erro do modelo.
- **`coding_standards.md` §7.1 — secrets hardcoded.** Severidade CRITICAL,
  alinhada ao texto do todo e com forte apelo prático. Rejeitada porque
  ampliaria o escopo (exige indexar um segundo guia) e porque seus negativos
  são ambíguos (uma fixture de teste com string literal viola ou não?).

### Consequências

- **Corrige o erro de gabarito em PR-009.** O dataset marca hoje
  `if order is not None:` como violação da Seção 5, mas o guia lista essa
  exata construção como **Correto**. Sob D-002 a linha é reclassificada como
  **negativo difícil**, e o aninhamento do PR sai de escopo.
- O dataset precisa ser reconstruído em torno desta regra, com positivos e
  negativos (incluindo negativos difíceis) em proporção documentada.
- ~~A indexação do piloto pode restringir-se ao `guia_python_pep8.md`.~~
  **Revertido por D-007** — o corpus completo é necessário como palheiro.

### Emenda (2026-09-18): segunda regra, Seção 2 restrita

**Status da emenda:** Aceita e implementada em `evaluation/dataset/pilot_dataset.json`.

O piloto passa de uma para **duas regras**: a Seção 5 (inalterada, acima) e
um recorte objetivo da **Seção 2 do `guia_python_pep8.md` - Nomenclatura**.
A Seção 3.2 (`import *`) continua rejeitada pelos motivos acima. A rejeição
da Seção 2 sem restrição tinha um motivo preciso (constante versus variável de
módulo depende da intenção do autor), e o recorte abaixo elimina exatamente
esse motivo.

**Sub-regras da Seção 2 no escopo** (todas decidíveis olhando uma linha):

| `sub_regra` | Norma | Viola | Não viola |
|---|---|---|---|
| `nome_funcao` | 2 - funções em `snake_case` | `def CalculateTax(...)`, `def calculateTax(...)` | `def calculate_tax(...)`, `def __init__(...)`, `def _helper(...)` |
| `nome_classe` | 2 - classes em `PascalCase` | `class payment_processor:`, `class Payment_Processor:` | `class PaymentProcessor:`, `class InvalidTokenError(Exception):` |
| `nome_proibido` | 2.1 - `l`, `O`, `I` como nome de uma letra | `l = []`, `for O in items:` | `i = 0`, `for j in rows:`, `lower = 1`, `obj.l` |

**Fora do escopo, de propósito:**
- Constantes e variáveis de módulo (`UPPER_SNAKE_CASE` versus `snake_case`):
  depende da intenção do autor, motivo da rejeição original.
- Nomes com sigla (`HTTPClient`, `parseXML`): o guia não define o tratamento.
  Nenhuma linha do dataset pode conter sigla em identificador de `def` ou
  `class`, para não haver rótulo discutível.
- Variáveis de uma letra fora de `l`, `O`, `I` ("evite `x`, `y`"): o guia
  ressalva índices de loop, então a fronteira é subjetiva.
- Exceções com sufixo `Error`, pacotes e módulos: exigem contexto de mais de
  uma linha ou de nome de arquivo.

**Por que este recorte responde às objeções anteriores:**
1. *Negativos difíceis existem.* `def __init__`, `def _helper`, `lower = 1`,
   `obj.l` e o texto `"l = 1"` dentro de string ou comentário são visualmente
   próximos das violações. A matriz não fica degenerada.
2. *Rotulação objetiva.* Cada sub-regra tem exemplos literais de correto e
   incorreto, e a tabela acima é o gabarito.
3. *Deixa de ser puramente lexical.* Decidir se `calculateTax` viola exige
   reconhecer o padrão de capitalização, o que o BM25 não resolve sozinho.
   Isso é o que falta para isolar o valor do embedding multilíngue, hoje uma
   limitação declarada.

**Consequências da emenda:**
- O dataset atual não precisou ser reclassificado: uma verificação por
  expressão regular nas 300 linhas achou **zero** violações de nomenclatura
  (30 linhas de `def` ou `class`, todas corretas).
- **Composição nova, 50 PRs (substitui os números de D-004):** dos 30 PRs
  antigos foram removidos 5 (PR-009, PR-010, PR-019, PR-020 e PR-030), para
  manter as sub-regras da Seção 5 balanceadas (26 booleanas e 26 de nulo), e
  foram somados 25 PRs novos da Seção 2 (PR-031 a PR-055). Resultado: 36 PRs
  com violação e 14 de controle, 474 linhas, 100 positivas (26 booleano, 26
  nulo, 16 por sub-regra da Seção 2) e 100 negativos difíceis. O esquema está
  em `evaluation/dataset/SCHEMA.md`. O arquivo passou a se chamar
  `pilot_dataset.json`.
- **A nomenclatura está em dois guias do corpus.** Além do
  `guia_python_pep8.md` (Seção 2 e 2.1), o `coding_standards.md` (2.1 e 2.2)
  traz as mesmas três sub-regras, de forma consistente. Uma detecção que cite
  qualquer um dos dois é correta, e o gabarito de retrieval aceita chunks de
  ambos. O `coding_standards.md` também tem regras vizinhas (2.3, funções que
  retornam booleano devem começar com `is_`/`has_`; 2.2, nomes genéricos)
  que ficam fora do escopo, e os negativos novos foram escritos para não
  violá-las de forma óbvia.
- Os resultados de detecção e de retrieval publicados (`results.json` e
  `results_L0` a `results_L4`) foram medidos no dataset antigo de 30 PRs e
  precisam ser refeitos para o dataset novo.
- Métricas passam a ser reportadas **por regra** além do total. Implementado
  em `metrics.py` (`RuleMetrics`, `RepetitionResult.per_rule`,
  `per_sub_rule_recall`, `AggregatedEvaluation.per_rule_summary`) e exibido e
  serializado por `run_evaluation.py` (chaves `per_rule` e
  `per_sub_rule_recall` em `results.json`). O recorte de uma regra são as
  linhas cujo campo `regra` é ela — as positivas mais os negativos difíceis
  escritos contra ela. Negativos comuns (`regra: null`) não pertencem a regra
  alguma e só entram na matriz global, então a soma das matrizes por regra é
  menor que N e a precisão por regra não é comparável à global. O recall por
  sub-regra é reportado à parte, porque uma sub-regra não tem negativos
  próprios.
- A precisão de referência normativa passou a ser **relativa à regra
  violada**: Seção 5 para comparações, Seção 2 (de qualquer um dos dois guias,
  subseção inclusive) para nomenclatura. O campo `cites_section_5` de
  `LineResult` virou `cites_correct_norm`.
- `norm_map.py`, `gold.py` e `validate_pilot_dataset.py` já cobrem as
  sub-regras novas.
- O corpus indexado não muda (D-007): a Seção 2 já está entre os 52 chunks.

### Emenda 2 (2026-09-25): terceira regra, `coding_standards.md` §4.1

> **Nova parte do estudo.** Esta emenda não amplia as regras anteriores:
> abre uma etapa nova do piloto, a primeira regra que **não se decide
> olhando uma linha isolada**. As Seções 5 e 2 continuam valendo como estão,
> e seus resultados devem ser medidos e reportados antes desta parte ser
> implementada, para que a regra nova não contamine a linha de base.

**Status da emenda:** Proposta. Nada implementado em dataset, validador,
`norm_map.py`, `gold.py` ou `metrics.py`.

O piloto passa de duas para **três regras**, somando um recorte objetivo do
**`coding_standards.md` §4.1 - Tratamento de Exceções**:

> Proibido capturar `Exception` genérica sem re-raise ou logging. Toda
> exceção capturada deve ser logada com `logger.exception()` ou re-lançada
> com contexto adicional.

#### Motivação

As Seções 5 e 2 se decidem pela linha, e um linter também as detecta
(pycodestyle E711/E712/E741, pep8-naming N801/N802). Isso deixa em aberto a
pergunta "o que o RAG com LLM faz que o `ruff` não faz?". A §4.1 responde a
essa pergunta sem abrir mão da rotulação objetiva:

1. **Exige contexto de várias linhas.** A linha `except Exception:` viola ou
   não conforme o corpo do bloco. O modelo precisa ler o bloco, não só
   reconhecer um padrão.
2. **Negativos difíceis naturais.** A linha `except` é idêntica nos casos
   correto e incorreto; só o corpo muda. A matriz não fica degenerada (a
   objeção que derrubou a Seção 3.2).
3. **Testa o retrieval entre guias.** A norma existe só no
   `coding_standards.md`, enquanto a Seção 5 existe só no
   `guia_python_pep8.md`. É o primeiro caso em que citar o guia errado é
   necessariamente erro, o que dá peso à precisão de referência normativa e
   ao palheiro de D-007.
4. **Relevância prática.** Engolir exceção em silêncio é defeito de
   manutenção, não só de estilo.

#### Sub-regras no escopo

A linha rotulada é sempre a do `except`. O corpo do bloco decide o rótulo.

| `sub_regra` | Norma | Viola | Não viola |
|---|---|---|---|
| `captura_generica` | 4.1 - `Exception` genérica sem re-raise ou log | `except Exception:` / `except Exception as exc:` com corpo só `pass` ou `continue` | mesmo `except` com `logger.exception(...)` ou `raise` no corpo |
| `captura_silenciosa` | 4.1 - toda exceção capturada é logada ou re-lançada | `except ValueError:` (ou outra exceção específica) com corpo só `pass` ou `continue` | `except ValueError as exc:` com `raise AppError(...) from exc` ou `logger.exception(...)` |

Critério do gabarito: o bloco **não viola** se contém, no primeiro nível de
indentação do corpo, um `raise` (com ou sem `from`) ou uma chamada
`logger.exception(...)`. Caso contrário, viola.

#### Fora do escopo, de propósito

- **`logger.error`, `logger.warning`, `print`.** O guia exige
  `logger.exception`, mas acusar `logger.error` é rótulo discutível.
  Nenhuma linha do dataset usa esses chamados dentro de um `except`.
- **Corpo com valor de fallback** (`return None`, `x = default`). Viola a
  letra do guia, mas é idioma Python comum; o rótulo seria contestável.
  Os corpos violadores do dataset são apenas `pass` ou `continue`.
- **`raise` ou log condicional** (`if ...: raise`) e `try` aninhado dentro do
  `except`: a decisão deixa de ser local ao bloco.
- **`except:` sem tipo e `except BaseException`**: o guia fala em
  `Exception`; a extensão para captura sem tipo não está escrita.
- **Tupla de exceções** (`except (ValueError, Exception):`).
- **§4.2 (hierarquia de exceções)** e **§4.1, terceiro item** (exceções
  customizadas para erro de negócio): exigem contexto de projeto.
- **`except` específico re-lançado sem `from`** (`except ValueError: raise`
  ou `raise AppError(...)` sem `from`). O guia pede "re-lançada com contexto
  adicional"; sem `from` o contexto é discutível. No `except Exception`, o
  primeiro item do guia só exige re-raise, então `raise` puro é aceito.

#### Consequências para a unidade de avaliação

- **D-001 se mantém.** A violação é de bloco, mas o rótulo fica numa linha
  só, a do `except`. As linhas do corpo (`pass`, `continue`, `raise`,
  `logger.exception(...)`) são negativas.
- **Risco de localização.** O LLM pode apontar a linha `pass` em vez da linha
  `except`. Por D-003 isso conta como FP na linha `pass` e FN na linha
  `except`. A regra de atribuição **não** é afrouxada para esta regra; em vez
  disso, o prompt passa a pedir explicitamente a linha do `except`, e o
  diagnóstico de FP separa os que caíram no corpo de um bloco violador
  ("viu, mas localizou errado") dos demais.
- **Linhas repetidas no mesmo PR.** `classify_lines` agrupa linhas de texto
  idêntico, então sinalizar uma sinaliza todas. Dentro de um PR, cada linha
  `except` precisa ter texto único (variar a exceção ou o nome após `as`),
  e nenhum PR pode ter uma linha `except` violadora textualmente igual a uma
  correta.
- **Forma do corpo violador.** O corpo de um bloco violador é um único
  `pass` ou `continue`, na linha logo abaixo do `except`, e seu texto não se
  repete em outra linha do PR. É isso que permite ao diagnóstico de
  localização achar a linha do corpo pela posição.
- **Nomes dos PRs novos** evitam as regras vizinhas do `coding_standards.md`:
  2.2 (nomes genéricos como `data`, `info`, `result`, `obj`, `temp` e
  abreviações como `cnt`) e 2.3 (função que retorna booleano sem `is_`,
  `has_`, `can_`, `should_`).

#### Composição proposta (a confirmar na construção)

- **25 PRs novos** (PR-056 a PR-080), dos quais **7 de controle**, espelhando
  a Seção 2.
- **Positivas:** 16 por sub-regra, 32 no total. Menos que as 48 da Seção 2
  porque cada bloco ocupa ao menos 4 linhas e o limite de 15 linhas por PR
  (D-004) precisa ser mantido. Vários `except` sob o mesmo `try` ajudam a
  caber.
- **Negativos difíceis:** ao menos tantos quanto as positivas. Catálogo
  mínimo, cada padrão em ao menos uma linha:
  `except Exception as exc:` + `logger.exception(...)` ·
  `except Exception:` + `raise` ·
  `except ValueError as exc:` + `raise AppError(...) from exc` ·
  `except KeyError:` + `logger.exception(...)` ·
  comentário com `except Exception: pass` ·
  string com `except Exception: pass`.
- Os números finais vão para `SCHEMA.md` quando o dataset for construído.

#### Pendências de implementação

- Dataset: `regra: "coding-4.1"`, sub-regras acima. As linhas de todas as
  regras continuam sem construção proibida das outras duas.
- `validate_pilot_dataset.py`: verificar o rótulo de cada `except` pelo
  critério do gabarito (via `ast`, não regex, já que depende do corpo) e as
  restrições de escopo e de texto único por PR.
- `norm_map.py` e `gold.py`: chave nova apontando só para chunks do
  `coding_standards.md` §4.1.
- `metrics.py`: `cites_norm_of` passa a reconhecer a §4.1 do
  `coding_standards.md`; diagnóstico de FP no corpo de bloco violador.
- Prompt do LLM: instrução para reportar a linha do `except`.
- O dataset atual não precisa de reclassificação: nenhuma das 474 linhas
  contém `except` (verificado em 2026-09-25).
- O corpus indexado não muda (D-007): o `coding_standards.md` já está
  indexado.

---

## D-003 — Atribuição detecção→linha: coincidência exata após normalização

**Data:** 2026-09-01
**Status:** Aceita

### Contexto

D-001 tornou a linha a unidade de avaliação, o que exige um critério explícito
para decidir a qual linha do diff pertence cada violação retornada pelo LLM.

### Decisão

Uma violação é atribuída a uma linha adicionada se, e somente se, as duas
**coincidirem exatamente** após normalização:

1. remoção de espaços no início e no fim;
2. colapso de sequências internas de espaço/tab em um único espaço.

A comparação é **sensível a maiúsculas e minúsculas** — o objeto avaliado é
código Python, onde `True` e `true` são coisas distintas.

### Regras derivadas

- **Deduplicação.** Várias detecções apontando para a mesma linha contam como
  uma só: a linha carrega um rótulo binário, sinalizada ou não.
- **Detecção não-atribuível.** Se o `line_content` retornado não coincide com
  nenhuma linha adicionada, o LLM alucinou a localização. Essa detecção é
  **excluída da matriz de confusão** e contabilizada à parte como **taxa de
  alucinação de localização**.
- **Citação da norma não condiciona o TP.** A métrica primária responde "a IA
  identifica o padrão?", que é o que o `todo-asap.txt` pede. O acerto da
  `norm_reference` é reportado como métrica secundária — *precisão de
  referência normativa*, a fração dos TPs que citou a Seção 5 corretamente.

### Justificativa

Excluir as alucinações da matriz preserva a invariante
**TP + FP + FN + TN = N** (total de linhas avaliadas). Se entrassem como FP, a
soma das células ultrapassaria N e o resultado deixaria de ser uma matriz de
confusão. Reportá-las em separado é mais honesto e mais informativo: mede um
modo de falha específico de sistemas RAG que a matriz não captura.

Separar detecção de citação evita fundir dois modos de falha distintos —
*não viu a violação* (falha do LLM) e *viu mas citou a norma errada* (falha do
retrieval). São problemas com causas e correções diferentes.

### Alternativa rejeitada

**Substring case-insensitive** (o critério atual em `match_violation`). Com
negativos difíceis ele colapsa: `if order is not None:` e
`if order.customer.is_active == True:` compartilham o prefixo `if order`, e o
termo `None` aparece tanto na construção correta quanto na incorreta. O
critério frouxo produziria TPs e FPs espúrios exatamente nas células que o
piloto existe para medir.

---

## D-004 — Composição do dataset do piloto

**Data:** 2026-09-01
**Status:** Aceita

### Decisão

Dataset sintético reconstruído em torno da regra de D-002:

| Dimensão | Valor |
|---|---|
| Pull Requests | **30** — 22 com ao menos uma violação, **8 de controle** sem nenhuma |
| Linhas adicionadas (N) | **~300** |
| Linhas positivas | **60 (20%)** — 30 de comparação booleana, 30 de comparação com nulo |
| Linhas negativas | **240 (80%)** — das quais **60 são negativos difíceis** |

### Justificativa de cada número

- **20% de positivos.** Alto o bastante para dar N = 60 na classe positiva,
  o que estabiliza a estimativa de recall; baixo o bastante para que o
  conjunto não fique artificialmente fácil, onde sinalizar tudo pontuaria bem.
- **8 PRs de controle.** Sem PRs limpos não há como medir a taxa de alarme
  falso no nível do gate. Um revisor que comenta em todo PR é inútil na
  prática, e só os PRs de controle expõem esse comportamento.
- **60 negativos difíceis (25% dos negativos).** Garante que os FPs, quando
  ocorrerem, sejam informativos: dizem que o modelo confunde `is not None` com
  `!= None`, não que ele confunde código com comentário.
- **Divisão igual entre as duas sub-regras.** Permite reportar desempenho por
  sub-regra e detectar se uma delas está puxando a métrica agregada.

### Catálogo mínimo de negativos difíceis

`if x is not None:` · `if x is None:` · `if flag:` · `if not flag:` ·
`if a != b:` (`!=` sem `None`) · `if x == y:` (`==` sem booleano ou `None`) ·
`assert x is None` · `return x is not None`

### Consequências

- **Limitação a declarar no TCC:** o dataset é sintético e construído pelo
  próprio autor, o que constitui ameaça à validade externa. Deve ser
  explicitado no texto. A substituição por PRs reais está em `TODO-FUTURO.md`.
- O gabarito passa a rotular **todas** as linhas adicionadas, não apenas as
  violações (consequência de D-001).

---

## D-005 — Determinismo do LLM: linha de base

**Data:** 2026-09-01
**Status:** Aceita (escopo mínimo — ampliação planejada)

### Contexto

Uma execução única de um modelo não-determinístico não sustenta as métricas de
um TCC: rodar de novo produz outro número e o resultado não é reprodutível.

### Decisão (estrutura base)

| Parâmetro | Valor |
|---|---|
| **Temperatura** | `0.0` |
| **Repetições por PR** | **1**, inclusive na execução oficial (padrão de `--repeticoes`). `--repeticoes 3` continua disponível |
| **Reporte** | Precisão, Recall e F1 da execução, com a matriz de confusão dela. Com mais de uma repetição, **média ± desvio-padrão** e a matriz da execução de **F1 mediano** |

**Revisão (2026-09-18).** O padrão original era 3 repetições na execução oficial. As 3 repetições já feitas (`evaluation/results.json`) deram desvio-padrão 0 em Precisão, Recall e F1, então repetir com temperatura 0.0 triplicava o gasto de cota sem informação nova, e o padrão passou a 1. Os resultados oficiais citados no README e nos relatórios vêm dessas 3 repetições.

### Nota metodológica

Temperatura `0.0` **reduz mas não elimina** o não-determinismo — inferência em
GPU com batching variável pode alterar o resultado entre chamadas idênticas.
É precisamente por isso que as repetições existem, em vez de se confiar na
temperatura sozinha.

### Escopo deliberadamente mínimo

Este é o tratamento suficiente para a estrutura base funcionar ponta a ponta.
O aprofundamento (mais repetições, intervalos de confiança, análise de
sensibilidade à temperatura) está registrado em **`docs/TODO-FUTURO.md`, F-001**
e será atacado depois que a base estiver rodando.

---

## D-006 — Modelo substituto: `qwen/qwen3.8-27b`

**Data:** 2026-09-01
**Status:** Aceita

### Contexto

O modelo do ADR-003, `llama-3.3-70b-versatile`, **não existe mais** no catálogo
da Groq — confirmado via `models.list()`. Não há **nenhum** Llama de propósito
geral disponível; os únicos `meta-llama/*` são classificadores *prompt-guard*
com 512 tokens de contexto. A linhagem do ADR-003 acabou, então o ADR precisa
de justificativa nova, não de emenda.

### Decisão

**`qwen/qwen3.8-27b`** (Alibaba Cloud, contexto 131.042, saída máx. 16.384).

### Justificativa

Diversifica a linhagem do trabalho, evitando que o resultado do TCC dependa de
uma única família de modelos. Atende aos cinco critérios do ADR-003: custo zero
no plano Groq, mesma API (sem mudança na integração com Actions), e contexto
muito acima do mínimo de 2.000 tokens exigido.

### Verificação executada

O único risco real da escolha era a aderência ao schema JSON estrito, nunca
exercitada neste código. **Eliminado por smoke test** em 2 PRs do dataset
(PR-001 e PR-011): ambos parsearam sem erro de formato.

### Alternativas consideradas e rejeitadas

- **`openai/gpt-oss-120b`.** Maior modelo disponível e o único com execução
  prévia comprovada neste repositório. Preterido para não concentrar o
  trabalho numa única linhagem.
- **`openai/gpt-oss-20b`.** Menor capacidade de análise é exatamente a
  variável sob medição — um F1 baixo ficaria ambíguo entre "o RAG não ajuda"
  e "o modelo é pequeno demais".
- **`groq/compound` e `groq/compound-mini`. REJEITADOS COM PREJUÍZO.** São
  sistemas agênticos com busca web e execução de código embutidas. Num estudo
  de RAG isso destrói a validade interna: o modelo poderia consultar a PEP-8
  na internet e "acertar" sem usar o contexto recuperado do Qdrant, sem que
  se possa distinguir os dois casos. **Não usar em nenhuma circunstância**,
  mesmo que o desempenho pareça superior.
- **Comparativo com dois modelos.** Enriqueceria a defesa, mas dobra o custo
  (2 × 3 repetições × 30 PRs = 180 execuções) e contraria o "sem dispersão de
  escopo" do `todo-asap.txt`. Adiado para `TODO-FUTURO.md` — comparar dois
  modelos antes de existir **um** número válido é otimizar na ordem errada.

### Consequências

- **ADR-003 precisa ser reescrito**, não corrigido: a justificativa inteira
  (velocidade da LPU com Llama, qualidade do 70B) deixou de se aplicar.
- O default `llm_model` em `rag_reviewer/config.py` ainda aponta para o modelo
  morto — quem rodar sem `.env` recebe 404. Precisa ser atualizado, junto com
  `.env.example` e o `.env` local.

---

## D-007 — Escopo: regras fixas, corpus completo

**Data:** 2026-09-01
**Status:** Aceita

### Contexto

O TCC deixa de defender que o sistema lida com alta variação de regras por
arquivo. Generalidade documental exigiria esforço incompatível com o prazo e o
porte de um trabalho de conclusão de curso.

### Decisão

1. O conjunto de **regras** verificadas é **fixo e pré-definido** no projeto.
2. O **corpus indexado permanece completo** (os três guias de
   `docs/style_guides/`), servindo de palheiro para a recuperação.
3. Os **resultados** das regras **nunca** são fixos: quais linhas violam é
   sempre decisão do retrieval + LLM, jamais tabelada.

O item 3 é a linha que não se cruza. É a mesma lição do mock circular que
produzia F1 = 1.0 lendo o gabarito: no instante em que o resultado deixa de ser
produzido pelo sistema, a medição inteira perde o sentido.

### Justificativa

A decisão separa duas coisas que estavam sendo confundidas: **quais regras** se
avalia e **qual corpus** se pesquisa.

Estreitar as regras torna o trabalho tratável. Estreitar o corpus esvaziaria o
RAG — com poucos chunks, a recuperação acertaria por falta de alternativa,
`recall@k` daria ~1.0 trivialmente e a ablação das três camadas ficaria sem
sinal para detectar. O sistema degeneraria em "um LLM com um prompt bom", e o
"RAG" do título ficaria difícil de sustentar numa defesa.

### Alternativas rejeitadas

- **Corpus estreito (só o guia do piloto).** Mais simples, mas destrói a
  capacidade de medir recuperação e desperdiça o gabarito de retrieval.
- **Registro curado de regras substituindo o markdown.** Se as regras são
  curadas *e* poucas, um matcher por expressão regular faria o mesmo trabalho
  sem LLM nenhum — é a pergunta óbvia de uma banca, e não há boa resposta.
  Também descartaria o chunker estrutural, cujo ganho foi medido em +42% de
  margem de discriminação.

### Consequências

- **Reverte** a consequência de D-002 que autorizava restringir a indexação ao
  `guia_python_pep8.md`.
- O chunker estrutural torna-se ainda mais necessário: o corpus completo só é
  um bom palheiro se os chunks forem íntegros. Chunks-lixo como `"Correto"` e
  `"Incorreto"` transformam distratores legítimos em ruído que vence por acidente.

---

## Pendências (decisões ainda não tomadas)

- **P-004 — Remoção da avaliação humana do planejamento.** Retirar §15.4
  (questionário Likert Q1–Q5) e a métrica de lead time em §15.3 do
  `RAG-Reviewer_Planejamento.md`, além de "questionário aplicado" na Sprint 5.
