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

**Status da emenda:** Aceita e implementada em
`evaluation/dataset/pilot_dataset.json`. Medições pendentes.

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
| `captura_generica` | 4.1 - `Exception` genérica sem re-raise ou log | `except Exception:` / `except Exception as exc:` com corpo só `pass` ou `continue` | `except Exception as exc:` com `logger.exception(...)` ou `raise AppError(...) from exc` |
| `captura_silenciosa` | 4.1 - toda exceção capturada é logada ou re-lançada | `except ValueError:` (ou outra exceção específica) com corpo só `pass` ou `continue` | `except ValueError as exc:` com `raise AppError(...) from exc` ou `logger.exception(...)` |

Critério do gabarito: o bloco **não viola** se contém, no primeiro nível de
indentação do corpo, um `raise ... from` ou uma chamada
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
- **Re-raise sem `from`**, em qualquer `except` (`except Exception: raise`,
  `except ValueError: raise` ou `raise AppError(...)` sem `from`). O segundo
  item do guia vale para toda exceção capturada e pede "re-lançada com
  contexto adicional"; `raise` puro não acrescenta contexto, e o rótulo
  "não viola" seria discutível. Um linter também acusa o `raise` puro logo
  após a captura (pylint W0706), o que tornaria o FP defensável.
  (Revisão da branch, 2026-09-25: a primeira versão aceitava `raise` puro em
  `except Exception`; seis negativos difíceis foram reescritos com
  `raise ... from exc`.)

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

#### Composição implementada

- **25 PRs novos** (PR-056 a PR-080), dos quais **7 de controle**, espelhando
  a Seção 2.
- **Positivas:** 16 por sub-regra, 32 no total. Menos que as 48 da Seção 2
  porque cada bloco ocupa ao menos 4 linhas e o limite de 15 linhas por PR
  (D-004) precisa ser mantido. Vários `except` sob o mesmo `try` ajudam a
  caber.
- **Linhas:** 287 nos PRs novos; o dataset passa a 75 PRs e 761 linhas
  (54 PRs com violação, 21 de controle, 132 positivas, 132 negativos
  difíceis).
- **Negativos difíceis:** 32, tantos quanto as positivas. Catálogo
  mínimo, cada padrão em ao menos uma linha:
  `except Exception as exc:` + `logger.exception(...)` ·
  `except Exception as exc:` + `raise AppError(...) from exc` ·
  `except ValueError as exc:` + `raise AppError(...) from exc` ·
  `except KeyError:` + `logger.exception(...)` ·
  comentário com `except Exception: pass` ·
  string com `except Exception: pass`.
- Os números por regra estão em `evaluation/dataset/SCHEMA.md`.

#### Implementação

- Dataset: PR-056 a PR-080 com `regra: "coding-4.1"` e as duas sub-regras.
  As linhas de todas as regras continuam sem construção proibida das
  outras duas.
- `validate_pilot_dataset.py`: `except_labels` rotula cada `except` pelo
  critério do gabarito sobre a AST do PR e rejeita o que está fora do
  escopo; `block_duplicates` impõe o texto único por PR;
  `HARD_NEGATIVE_CATALOG_EXCECAO` confere o catálogo por par de linhas.
- `norm_map.py` e `gold.py`: chave `NORM_EXCECAO`, só com chunks do
  `coding_standards.md` §4.1.
- `metrics.py`: `cites_norm_of` reconhece a §4.1 (`_SECTION_4_1_PATTERN`);
  `RepetitionResult.misplaced_block_fps` conta os FPs no corpo de bloco
  violador, exibido e salvo por `run_evaluation.py`.
- `review_template.txt`: instrução para reportar a linha que abre o bloco.
- O dataset atual não precisa de reclassificação: nenhuma das 474 linhas
  contém `except` (verificado em 2026-09-25).
- O corpus indexado não muda (D-007): o `coding_standards.md` já está
  indexado.
- Os resultados publicados continuam sendo do dataset anterior. A linha de
  base das Seções 5 e 2 é medida na árvore de `0237b3d`, antes do prompt
  novo.

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

## D-008 — Código do dataset conforme o corpus inteiro

**Data:** 2026-09-26
**Status:** Aceita

### Contexto

A primeira rodada no dataset de três regras (75 PRs, 761 linhas) deu
TP 114, FP 61, FN 18, TN 567: precisão 0.648, abaixo da meta de 0.70. O
detalhe por PR (`per_pr_detail`) mostrou que **53 dos 61 FPs não são erros
do modelo**: são violações reais de outras normas do corpus que o código do
dataset comete e o gabarito não rotula. O código dos PRs não tinha docstring
(`coding_standards.md` 5.1, 25 FPs), tipo de retorno (3.3, 13 FPs), linhas
em branco entre definições (`guia_python_pep8.md` 1.3, 6 FPs), além de
funções que o modelo tomou por booleanas sem prefixo (2.3, 6 FPs). O mesmo
efeito bloqueou 20 dos 21 PRs de controle no gate por PR.

O rótulo "não viola" de D-001 é relativo às regras do piloto, mas o sistema
recebe o corpus inteiro (D-007) e a instrução de apontar qualquer violação.
A tarefa medida e a tarefa executada divergiam, e a diferença aparecia como
FP.

### Decisão

O gabarito e a métrica **não mudam**. Muda o **código** dos 75 PRs: toda
linha passa a cumprir todas as normas do corpus aplicáveis a um trecho de
código isolado, exceto a violação que o seu rótulo declara. Assim o rótulo
"não viola" fica verdadeiro para o corpus inteiro, não só para o piloto.

**Normas garantidas pelo validador** (`validate_pilot_dataset.py`):

| Norma | Checagem |
|---|---|
| pep8 1.1 (79 caracteres; 72 em docstring e comentário) | ruff E501, W505 |
| pep8 1.2, 1.3, 4 (indentação, linhas em branco, espaços) | ruff E, W (com `--preview`, para E30x) |
| pep8 2, 2.1 (nomes; exceção com sufixo `Error`) | ruff N; nome de uma letra só `i`, `j` e `_`; `l`, `O` e `I` nunca lidos fora da linha positiva que os atribui |
| pep8 3, cs 6 (imports agrupados e ordenados, sem `*`) | ruff I, F403 |
| cs 2.2 (nomes genéricos e abreviações) | lista proibida: `data`, `info`, `temp`, `obj`, `result`, `cnt`, `mx`, `err`, `val` |
| cs 2.3 (prefixo booleano) | prefixo `is_`/`has_`/`can_`/`should_` se e somente se o retorno anotado é `bool` |
| cs 3.1, 3.2 (até 30 linhas; até 4 parâmetros; sem parâmetro booleano) | AST |
| cs 3.3 (tipo de retorno) | ruff ANN001, ANN201, ANN202, ANN204: toda função com parâmetros e retorno anotados |
| cs 5.1 (docstring Google Style em módulo, classe e função) | ruff D (convenção `google`, `__init__` inclusive; só D105, métodos mágicos, fica de fora); `Args:` se há parâmetro, `Returns:` se o retorno não é `None`, `Raises:` se há `raise` |
| cs 7.1 (segredos e URLs fixas) | nenhum literal com `://`, `sk-` ou `password` |
| Nomes de módulo | atribuição de módulo só em `UPPER_SNAKE_CASE` ou `logger` |

Os achados que correspondem às regras do piloto só são aceitos na linha
positiva da própria regra: E712 (`booleano`), E711 (`nulo`), N802
(`nome_funcao`), N801 (`nome_classe`), e E741, N806, nome de uma letra e
nome de módulo (`nome_proibido`, que é a mesma violação vista por quatro
checagens). Qualquer outro achado, em qualquer linha, reprova o PR. A linha positiva cumpre
o resto: `def CalculateTax(amount: float) -> float:` viola só a
nomenclatura.

**Diretriz de escrita, sem checagem:** responsabilidade única (cs 1.1),
comentários que explicam o porquê (cs 5.2), camadas e N+1
(`architecture_patterns.md`).

**Fora do escopo, residual declarado:**
- cs 4.2 (hierarquia de exceções por domínio). O catálogo de negativos
  difíceis da Seção 2 exige `class XError(Exception):`, e um PR isolado não
  tem hierarquia de domínio a seguir. Um FP citando 4.2 é discutido no texto.
- `assert` "em produção". Não é norma do corpus; se o modelo acusar, é FP.
- cs 8, 9, 7.2 e `architecture_patterns.md` 2 e 3: não se aplicam a um
  trecho de código.

**Rótulos:** as 132 positivas e os 132 negativos difíceis mantêm o rótulo.
O texto delas pode mudar só para cumprir as demais normas (anotações de
tipo, indentação). Linhas novas (docstrings, imports, linhas em branco) são
negativos comuns. Em 11 PRs da Seção 5 o `return` rotulado foi movido para
o fim da função, porque o código antigo tinha instruções inalcançáveis
depois dele; o conjunto de rótulos de cada PR é o mesmo. As positivas
`nome_funcao` não retornam `bool`, para não violarem também a cs 2.3.

### Emenda a D-004

- Cada PR tem **de 6 a 60 linhas** (antes, 6 a 15). Docstrings Google Style
  não cabem em 15, e um PR com quatro funções documentadas passa de 40.
  (O plano previa 40; subiu na reescrita, porque o custo de tokens é
  governado pelo teto de caracteres, não pelo número de linhas.)
- O texto do dataset inteiro tem no máximo **90.000 caracteres** (hoje,
  23.441). Resultado da reescrita: 2.025 linhas e 49.829 caracteres, de 18
  a 52 linhas por PR. São ~8 mil tokens a mais por rodada, dentro da cota
  diária de 200 mil do Groq (D-006). Uma rodada por dia; o checkpoint
  retoma se a cota acabar.

### Mudança no retriever

Linhas em branco (ou só com espaços) deixam de ser **consultas** de
recuperação: não carregam conteúdo normativo, geram vetor esparso vazio e
um vetor denso arbitrário que só polui a união dos chunks. Continuam
chegando ao LLM e continuam sendo linhas avaliadas (D-001). Um diff real
tem linhas em branco, então a mudança é de robustez do sistema, não um
ajuste ao dataset.

### Correção na união do retriever (2026-09-29, `fb05820`)

A primeira rodada oficial sobre o dataset conforme (`b2eddf4`) deu
Precisão 0,7944, Recall 0,6439 e F1 0,7113 (TP 85, FP 22, FN 47, TN 1.871),
abaixo da meta de recall. Os FNs se concentravam em `captura_silenciosa`
(1 de 16) e `booleano` (12 de 26). A causa estava no retriever, não no
modelo.

Isolada, cada linha violadora recupera a própria norma em 1º lugar (score
1,0). A união por arquivo, porém, guardava o chunk repetido com o score
da **primeira** linha que o trouxe, não com o maior. Com as docstrings e
anotações de D-008, as linhas anteriores à violação passaram a trazer a
Seção 5 e a cs 4.1 em posições baixas (0,33 no PR-002, 0,36 no PR-056), e
o corte em 8 chunks as eliminava. É o risco de diluição previsto abaixo,
agravado por um defeito: a regra de deduplicação estava errada para
qualquer diff, não só para este dataset.

A correção mantém o maior score de cada chunk entre as linhas. PRs
violadores com todas as normas necessárias no contexto entregue ao LLM:
25 de 54 antes, 47 de 54 depois. Os 7 que ainda perdem a norma são de
nomenclatura (PR-031 a 035, 037, 038), a regra com maior recall.

O `recall@k` da ablação (L0 a L4) não enxergava o defeito: ele mede cada
linha isolada, antes da união e do corte. A rodada de `b2eddf4` fica como
o "antes"; a rodada oficial de D-008 passa a ser a do sistema corrigido.

### Ablação de recuperação refeita (2026-09-29)

`results_L0` a `results_L4` foram refeitos no dataset atual (132 linhas
positivas, antes 60 só da Seção 5), cumprindo a pendência da Emenda de
D-002. L0 a L2 e `L4_sem_multilingue` foram medidos em coleções
temporárias do Qdrant com o modelo em inglês (L0 com o loader e o chunker
de `1e21350`), apagadas depois; a coleção de produção não mudou.

recall@5: L0 0,64 · L1 0,70 · L2 0,16 · L3 0,67 · L4 0,84 ·
L4 com o modelo em inglês 0,89. O critério (>= 0,95) deixa de ser
atingido. Em L4 a Seção 5, a cs 4.1 e os nomes de classe ficam em 1,0; as
falhas são nomes de função (0 de 16) e `l`/`O`/`I` (11 de 16), violações
sem texto em comum com a norma. Duas conclusões da ablação antiga não se
mantêm: a consulta por arquivo deixou de ser a pior configuração, e o
modelo multilíngue não supera o inglês com o BM25 ativo (ADR-002 e
ADR-004 citam os números antigos).

### Medição

- A rodada oficial é uma só: sistema atual contra o dataset conforme.
  `evaluation/results.json` é sobrescrito; `results_dev.json` e
  `results_dev_3regras.json` são removidos (o "antes" fica no histórico do
  git, commit anterior a esta decisão).
- **A linha de base das Seções 5 e 2 em `0237b3d` (Emenda 2 de D-002) é
  abandonada.** Com o código do dataset reescrito, aquela árvore mede outro
  material. A instrução do prompt sobre a linha que abre o bloco passa a ser
  parte do sistema avaliado.
- Critério de sucesso: os FPs que citam normas fora do piloto (docstring,
  tipo de retorno, prefixo booleano, linhas em branco) somem ou viram casos
  isolados. O que sobrar é erro do modelo e vai para a discussão.

### Resultado (2026-09-29)

Rodada oficial com o retriever corrigido: Precisão 0,8722, Recall 0,8788,
F1 0,8755 (TP 116, FP 17, FN 16, TN 1.876). As três metas foram atingidas;
na rodada de `b2eddf4` o recall ficava abaixo da meta. Relatório completo
em `docs/RELATORIO-RESULTADOS.md`.

- Seção 5: F1 1,0. Seção 2: F1 0,96. cs 4.1: F1 0,65.
- `captura_silenciosa` concentra 14 dos 16 FNs (recall 0,13). A norma
  chega ao LLM em todos esses PRs; a perda é do modelo. Causa provável: o
  exemplo da cs 4.1 mostra a "captura específica" como o jeito correto.
- Critério de sucesso atendido: dos 17 FPs, nenhum é linha em branco ou
  de docstring. Os FPs fora do piloto viraram casos isolados (8 citam a
  cs 1.1, 2 a cs 6.1, 1 a cs 5.1); 7 são negativos difíceis, 5 deles
  `except Exception as exc:` que loga ou re-lança.
- Gate por PR: TP 54, FN 0, FP 11, TN 10.

### Riscos

- **Recall por diluição do retrieval.** As linhas de docstring também são
  consultas e podem levar o chunk da cs 5.1 a ocupar uma das 8 vagas que
  antes eram da Seção 5 ou da cs 4.1. É um efeito real (código de verdade
  tem docstring) e será reportado se aparecer.
- **Texto repetido multiplica FP.** D-003 agrupa linhas de texto igual:
  sinalizar uma sinaliza todas. O dataset novo tem até 17 linhas em branco
  por PR e linhas de docstring repetidas (`"""`, `Args:`, `Returns:`).
  Uma detecção com `line_content` vazio, que antes era alucinação, agora
  marca todas as linhas em branco do PR como FP. A regra de atribuição não
  muda (a métrica fica como está); a análise da rodada reporta à parte os
  FPs em linha em branco ou de docstring.
- A acurácia sobe artificialmente com o N maior (a proporção de positivas
  cai de 17% para ~7%). Precisão, recall e F1 não usam TN e continuam
  comparáveis.

### Alternativas rejeitadas

- **Estender o gabarito às normas objetivas (cs 5.1, 3.3, pep8 1.3).** As
  positivas passariam de 132 para mais de 250, sem negativos difíceis para
  as regras novas; o desenho do piloto (poucas regras, rótulo indiscutível)
  deixaria de valer, e parte dos rótulos seria discutível (cs 2.3 sem tipo
  anotado, cs 1.1).
- **Reportar uma "precisão no escopo" que desconta os FPs fora do piloto.**
  Mudaria a métrica depois de ver o resultado.
- **Restringir o prompt às regras do piloto.** Contradiz D-007.

---

## D-009 — Corpus: a PEP 8 completa como fonte única

**Data:** 2026-10-06
**Status:** Aceita
**Spec:** `docs/superpowers/specs/2026-10-06-corpus-pep8-design.md`

### Contexto

A orientação do TCC é que o RAG-Reviewer tenha como base de análise e
comparação a PEP 8, completa e sem redundância. O corpus de D-007 eram três
guias internos (`guia_python_pep8.md`, `coding_standards.md`,
`architecture_patterns.md`): a PEP 8 estava resumida em 5 seções, e a
nomenclatura e os imports apareciam em dois guias, de modo que o mesmo trecho
era recuperado duas vezes.

### Decisão

1. O corpus indexado é só `docs/style_guides/pep-0008.md`: o texto oficial em
   inglês, sem tradução, convertido do reST de `python/peps`
   (`peps/pep-0008.rst`, commit `5514795ade79a5bf6f3c08c562b02689d0a9feb2`;
   a PEP está em domínio público) por `scripts/pep8_rst_to_md.py`. Os três
   guias saem do índice. A PEP 8 inteira vira 40 seções e 43 chunks.
2. Sem redundância: o corpus tem uma fonte; o chunker não usa sobreposição
   (`chunk_overlap` padrão 0) e há teste de que o chunking não repete trecho
   algum do corpus. Cada norma do piloto está em exatamente um chunk.
3. As seis normas do piloto passam a ser enunciados da PEP 8
   (`norm_map.py`), e o código "conforme" do dataset cumpre só a PEP 8
   (`conformity.py`: ruff `E,W,N,I,F403`, 79 colunas, 72 em comentário).
   Docstring, anotações, prefixo booleano e limite de parâmetros eram
   exigências dos guias antigos e deixam de valer.
4. O texto continua em inglês e o prompt em português. A decisão sobre o
   modelo de embedding segue aberta.

### Achado: duas regras do piloto não eram da PEP 8

A PEP 8 manda usar `except Exception:` para capturar erros de programa e só
restringe o `except:` nu (equivalente a `except BaseException:`), tolerado em
dois casos: o handler registra o traceback ou faz limpeza e relança com
`raise`. Logo `captura_generica` (`except Exception:` com `pass`) e
`captura_silenciosa` (exceção específica com `pass`) **não violam** a PEP 8;
log e re-raise vinham do `coding_standards.md` 4.1.

A regra de exceções passa a ser o `except:` nu (`regra` `pep8-excecoes`,
`sub_regra` `except_nu`). As formas antigas viram negativos difíceis, e o
`except:` com `logger.exception` ou `raise` também (os dois casos tolerados).
Um `except:` nu só pode ser o último handler de um `try` e o texto não pode se
repetir no PR (D-003), então há no máximo um por PR: das 32 positivas antigas
ficaram 18 (uma por PR violador, nos mesmos 18 PRs) e 14 viraram negativos
difíceis com tipo.

Demais renomeações de `regra`: `secao-5` -> `pep8-recomendacoes`, `secao-2` ->
`pep8-nomes`. Dataset: 75 PRs, 54 violadores, 21 de controle; 118 linhas
positivas (antes 132) e 146 negativos difíceis (antes 132).

### Mudanças no pipeline que a PEP 8 exigiu

- `_clean_text` do carregador colapsava espaços dentro dos blocos de código,
  apagando a indentação e o alinhamento que a PEP 8 mostra como certo e
  errado. Blocos cercados passam a ficar intactos.
- O carregador separava só cabeçalhos até o nível 3; a PEP 8 usa o nível 4
  (Names to Avoid, Class Names, Function and Variable Names). Seção só com
  título deixa de virar chunk.
- Em seção grande com cercas, cada cerca e cada trecho de prosa viravam
  chunks soltos (a seção Programming Recommendations dava 33, a maioria de 1 a
  9 palavras, com o exemplo separado da regra). O chunker passa a dividir em
  itens de lista de topo (uma norma e seus exemplos) e a empacotar até
  `chunk_size`.
- `chunk_size` 512 foi mantido: com busca híbrida por linha, o recall@5 foi de
  0,74 (512), 0,68 (256), 0,67 (128) e 0,49 (64).

### Consequências

- **Os resultados não são comparáveis um a um com os de D-008.** Muda o
  corpus (e com ele o que o retrieval pode achar), mudam duas regras e muda a
  fonte da citação (`norm_reference` passa a citar seções da PEP 8). O
  relatório compara os números, mas diz isso.
- Reverte a parte de D-007 que fixava os três guias como palheiro; a lógica de
  D-007 (corpus completo, não estreitado) vale: a PEP 8 tem 43 chunks, contra
  52 antes.
- Os resultados de D-008 (coleção `style_guide_chunks`, 52 pontos) continuam
  no Qdrant. A coleção da PEP 8 é `pep8_chunks`.

### Alternativas rejeitadas

- **PEP 8 completa mais os guias (corpus B).** Menos disruptivo, mas deixa o
  piloto menos "PEP 8 pura" e mantém a nomenclatura em duas fontes.
- **Tradução da PEP 8 para português.** Não há versão oficial, uma tradução
  própria pode desviar do texto, e reabriria a escolha do modelo de embedding
  (o MiniLM em inglês superou o multilíngue na ablação de D-008).
- **Manter `captura_generica` e `captura_silenciosa`.** Seriam rótulos que a
  PEP 8 contradiz: o gabarito exigiria do sistema o oposto do que o corpus diz.

---

## D-010 — Dataset realista: 25 PRs, vários arquivos e 23 normas da PEP 8

**Data:** 2026-10-08
**Status:** Aceita
**Spec:** `docs/superpowers/specs/2026-10-08-dataset-realista-design.md`

### Contexto

O dataset de D-008/D-009 tinha 75 PRs de um arquivo novo cada e 6 normas.
O objetivo agora é que o resultado local seja um ensaio do que o workflow do
GitHub (`main-completa`) vai produzir num PR real: o Action coleta o diff pela
API, o retriever consulta por linha adicionada, o LLM recebe um arquivo por
chamada e o publisher comenta por linha. Num PR real há vários arquivos,
a maioria modificada, e violações de várias normas misturadas.

Cobrir "toda a PEP 8" não cabe: várias regras não se rotulam num diff isolado
("seja consistente", "use bom senso"), e com cerca de 30 a 40 regras
verificáveis em 25 PRs sobra 1 a 2 PRs por regra, sem poder estatístico por
regra.

### Decisão

1. **Formato realista, em vez de uma norma por PR.** 25 PRs (20 violadores,
   5 limpos), 35 arquivos (21 novos, 14 modificados com `patch` de hunks,
   contexto e remoções), cada PR violador com 2 a 5 normas misturadas. A
   chamada ao LLM é por arquivo, então a cota diária da Groq (200 mil tokens,
   cerca de 3.700 por chamada) comporta cerca de 54 arquivos; 35 cabem com
   folga.
2. **23 normas da PEP 8 em 6 famílias**, num catálogo único
   (`evaluation/dataset/norms.py`): id, família, códigos do ruff, frase âncora
   do texto da PEP 8, padrões de negativo difícil. O validador, a conformidade,
   o gabarito de recuperação e a citação derivam dele. A família é o campo
   `regra` e a norma é o `sub_regra` (nomes mantidos para não mexer em
   `metrics.py`): `per_rule` recorta por família e `per_sub_rule_recall` vira a
   tabela de cobertura por norma. Ficaram de fora duas normas que não estão no
   texto da PEP 8 (`not x in y` e espaço depois da vírgula).
3. **O ruff como oráculo do rótulo.** Todo achado numa linha adicionada precisa
   casar com a norma rotulada nela, e toda positiva precisa disparar a própria
   norma. Achados em linhas de contexto de arquivos modificados (código
   pré-existente) são ignorados. Constantes em MAIÚSCULAS, que o ruff só pega em
   `mixedCase`, têm checagem AST.
4. **Normas de vizinhança só em arquivos novos.** `linhas_em_branco`,
   `import_topo` e `import_ordem` dependem de linhas que o LLM não vê num arquivo
   modificado, porque o workflow entrega só as `added_lines`.
5. **Fora do escopo desta rodada:** portar o workflow de `main-completa`, medir
   a `suggestion` (aplicar a correção e rodar o ruff) e a `severity`, a linha de
   base sem recuperação e a decisão do modelo de embedding.

### Consequências

- Os resultados **não são comparáveis** com os de D-009: mudam o dataset, as
  normas e o gabarito. Com cerca de 4 positivas por norma, a cobertura por norma
  é indicação, não estatística; o número que vale é o agregado (P, R, F1 sobre 98
  linhas positivas).
- O dataset de D-008/D-009 (75 PRs) sai da árvore e fica no histórico do git.
- O `norm_map.py` e o `gold.py` passam a usar o id da norma como chave
  (23 chaves); o gabarito de recuperação ganha o `filename`.
- O checkpoint da avaliação sobe para o schema 4 (PRs de vários arquivos).

### Alternativas rejeitadas

- **Manter 75 PRs de um arquivo.** Não ensaia o fluxo real e custa 75 chamadas,
  mais que a cota de um dia.
- **Uma norma por PR, com 4 a 5 PRs por norma.** Melhor estatística por regra,
  mas distante de um PR real, que mistura normas.
- **Trocar parte das normas mecânicas por regras de interpretação** (nomes
  descritivos, conteúdo de comentário). Reforçaria o argumento "RAG contra
  linter", mas o rótulo deixaria de ser automático e passaria a depender de
  julgamento.

### Revisão após a primeira rodada (2026-10-08)

A primeira avaliação oficial do dataset (`evaluation/results_realista.json`,
mantido no repositório como registro) deu P 0,8021, R 0,7857, F1 0,7938
(TP 77, FP 19, FN 21, TN 679, 796 linhas; gate por PR TP 19, FP 5, FN 1,
TN 0). Os 40 erros por linha foram investigados um a um contra o texto da
PEP 8 e contra o contexto que o retriever entregou a cada arquivo. O resultado:

| Origem | FPs | FNs |
|---|---|---|
| Erro de rótulo do dataset | 11 | 4 |
| Norma ausente do contexto (recuperação) | 0 | 15 |
| Falha do modelo | 6 | 2 |
| Acusação dupla benigna (def e corpo que usa `this`) | 2 | 0 |

Os 15 erros de rótulo foram corrigidos, e a decisão de cada um está abaixo.
Como os erros só foram achados depois de ver o resultado, há risco de correção
seletiva. Para mitigar: (a) toda correção cita o texto da PEP 8, (b) os rótulos
de **todas** as 23 normas foram auditados contra o texto, inclusive os que
favoreciam o modelo (a auditoria achou um erro a mais, que não aparecia nos
resultados), (c) a primeira rodada continua registrada, e o relatório mostra as
duas lado a lado.

1. **Docstring pública (8 FPs).** A PEP 8 manda: "Write docstrings for all
   public modules, functions, classes, and methods". O código das PRs novas não
   tinha, o modelo acusou (certo) e o gabarito dizia "não viola". Decisão:
   cobrar docstring no oráculo (`docstring_findings` em `conformity.py`; público
   é o nome sem `_` inicial, mais `__init__`, como na PEP 257; funções aninhadas
   e membros de classe não pública ficam de fora) e escrever as 108 docstrings
   de uma linha que faltavam. Não vira a 24ª norma: quase toda função seria
   positiva e o dataset perderia o equilíbrio. O ruff com `E,W,N,I` não cobra
   isso; o oráculo passa a ter essa checagem.
2. **`if x is True:` como negativo difícil (1 FP).** A PEP 8 lista
   `if greeting is True:` como **Wrong**. O rótulo estava errado; o negativo foi
   trocado por `if x:` e o padrão saiu do catálogo.
3. **Literal global em minúsculas (`retry_limit = 3`, 2 FPs, mais `retries = 3`).**
   A PEP 8 diz que constantes são "geralmente" em MAIÚSCULAS, mas não diz se um
   literal global é uma constante. O texto não decide o rótulo. Decisão
   (autor): tratar como **ambiguidade**. As 3 linhas ganham `ambiguo: true`,
   saem da matriz de confusão e são reportadas à parte (total e quantas o modelo
   sinalizou). Para o workflow real fica registrado como requisito: nesse tipo de
   caso o modelo deve dizer que pode haver ambiguidade, em vez de afirmar a
   violação (ver `docs/TODO-FUTURO.md`). Isso torna o conjunto de negativos
   difíceis de constante menos adversarial; fica declarado.
4. **`import_ordem` como ordem alfabética (4 FNs).** A PEP 8 só exige **grupos**
   (biblioteca padrão, terceiros, locais) e linha em branco entre eles; não exige
   ordem alfabética. A norma passa a ser grupo fora de ordem (terceiros antes da
   biblioteca padrão, que o ruff também acusa como I001), e os 4 positivos foram
   reescritos.
5. **`type(first) is type(second)` como negativo difícil (achado na auditoria).**
   A PEP 8 lista `if type(obj) is type(1):` como **Wrong**. Trocado por
   `isinstance(first, type(second))`.

Resultado dos ajustes no dataset: 908 linhas adicionadas, 98 positivas, 74
negativos difíceis, 3 ambíguas, as mesmas 25 PRs e 35 arquivos.

Fora do dataset, sem alteração e como limitação registrada: (a) 6 FPs e 2 FNs
são falhas do modelo (aceita `except Exception:` e o `except:` tolerado como
violação, não conta colunas de forma confiável); (b) 15 FNs são falta da norma no
contexto de 8 chunks. Aumentar o corte de 8 chunks foi descartado porque
estoura a cota diária da Groq. Em seu lugar, um teste sem LLM de chunks menores
(exploratório, porque ajusta o sistema no mesmo dataset em que depois se avalia)
mediu, no caminho de produção, em quantas das 98 linhas positivas a norma chega
ao contexto de 8 chunks e quantas palavras de contexto cada arquivo carrega
(`evaluation/retrieval/context_coverage.py`):

| `chunk_size` | Linhas com a norma no contexto | Palavras de contexto por arquivo |
|---|---|---|
| 512 (atual) | 53 de 98 (54%) | 1.835 |
| 256 | 37 de 98 (38%) | 1.102 |
| 128 | 28 de 98 (29%) | 710 |

Chunks menores gastam menos tokens, mas perdem mais cobertura do que economizam.
O `chunk_size` fica em 512 e a recuperação segue como limitação registrada. Das
45 linhas positivas sem a norma no contexto (com 512), só uma parte vira FN, o
que sugere que o modelo também acerta por conhecimento prévio da PEP 8; a
rodada 2 mediu isso: com a norma no contexto o recall foi 0,87 (46 de 53),
sem ela 0,69 (31 de 45).

### Rodada 2 (2026-10-09)

Dataset corrigido (25 PRs, 35 arquivos, 98 positivas, 74 negativos difíceis, 3
ambíguas), mesmo pipeline, mesmo modelo, 1 repetição. Resultado em
`evaluation/results_realista_r2.json`, relatório na seção 0 de
`docs/RELATORIO-RESULTADOS.md`.

- **Números.** P 0,8556, R 0,7857, F1 0,8191 (rodada 1: 0,8021, 0,7857,
  0,7938). Metas atingidas. Matriz: TP 77, FP 13, FN 21, TN 794. Gate por PR:
  TP 19, FP 4, FN 1, TN 1. Precisão da referência normativa 0,7403.
- **Ambíguas.** 3 linhas, fora da matriz; o modelo sinalizou 2 (`retry_limit`,
  `default_name`). A decisão de tratá-las como ambiguidade se mantém.
- **Dependência do contexto.** Com a norma entre os 8 chunks entregues, o recall
  foi 0,868 (46 de 53); sem ela, 0,689 (31 de 45). O RAG ajuda, mas o modelo
  detecta a maioria das positivas mesmo sem a norma no contexto. Sem uma linha de
  base sem recuperação não se separa a contribuição do corpus do conhecimento
  prévio do modelo; segue em aberto. Dados em
  `evaluation/retrieval/context_coverage_d010.json`.
- **Pontos fracos.** `pep8-layout` (recall 0,375), `import_ordem` 0/4,
  `lambda_atribuido` 1/4, `linha_longa` 1/4, `linhas_em_branco` 2/4,
  `comentario_inline` 3/6. Os 13 FPs incluem 2 corpos de método, 3 strings
  longas, 2 `except Exception`, 2 `except:` tolerados e 4 linhas isoladas; as 4
  isoladas e as 3 longas não foram investigadas.
- **Correção do parser.** A primeira execução caiu no PR-011: o modelo emitiu uma
  vírgula sobrando antes de `}` numa resposta cortada em `max_tokens` (900), e
  `LLMClient._recover_truncated` rejeitava o JSON. A função agora remove a
  vírgula sobrando antes de `}` ou `]` em outra linha (nunca dentro de string
  JSON), com teste. A mudança só atua onde a execução antes falhava, então os 10
  PRs já avaliados são equivalentes. O corte em 900 tokens segue valendo; uma
  resposta com muitas violações ainda perde as últimas (comportamento herdado de
  D-009, não alterado).
- **Cota da Groq.** Eu afirmei que a cota diária zerava às 00:00 UTC (20:00
  local) sem verificar. Não zerou: o erro 429 dizia "tente de novo em 21 min"
  com 199.106 de 200.000 tokens usados, o que indica janela deslizante. A rodada
  terminou no dia seguinte, retomada do checkpoint (a invalidação do checkpoint
  depende do hash do dataset e dos prompts, não do código do cliente).

---

## D-011 — Workflow do GitHub: o RAG-Reviewer revisando PRs reais

Spec: `docs/superpowers/specs/2026-10-09-workflow-github-design.md`. Plano:
`docs/superpowers/plans/2026-10-09-workflow-github.md`. Branch
`feat/workflow-github`. O PR nunca é bloqueado (a PEP 8 é estilo): toda review sai
como `COMMENT` e `CRITICAL` deixou de existir. O modelo marca `ambiguous` quando o
texto da PEP 8 não decide o caso (F-004). Da `main-completa` entrou só o que é
workflow (coleta do diff, publisher, orquestrador, entrada do Action e o YAML); o
corpus, os prompts e o retriever são os da `main`.

### Registro da implementação

| Arquivo | Função / elemento | Para que serve |
|---|---|---|
| `rag_reviewer/llm_client.py` | `_VALID_SEVERITIES`, `Violation.ambiguous`, `_parse_single_violation` | Severidade só HIGH/MEDIUM/LOW; o campo `ambiguous` (só o booleano `true` vale) força LOW |
| `rag_reviewer/prompts/system_prompt.txt`, `review_template.txt` | regra 6, schema, parágrafo da Tarefa | Sem CRITICAL; o modelo marca a ambiguidade |
| `rag_reviewer/config.py` | remoção de `block_on_critical` | O Action nunca bloqueia |
| `rag_reviewer/config.py` | `extra="ignore"` em `Settings` | Um `.env` com `BLOCK_ON_CRITICAL` (já removida) não derruba a configuração |
| `rag_reviewer/diff_parser.py` | `PullRequestDiff`, `DiffCollector.collect/_paginate/_parse_files` | Lista os arquivos do PR pela API (com paginação), descarta deletados, binários, sem patch e não `.py`, e monta cada `FileDiff` |
| `requirements.txt` | `requests` | Cliente HTTP da API do GitHub |
| `rag_reviewer/retriever.py` | `Retriever.retrieve_for_diff` | Aplica a recuperação por arquivo a todos os arquivos do PR e descarta os sem linhas adicionadas ou sem contexto |
| `rag_reviewer/github_publisher.py` | `GitHubPublisher.publish`, `_create_review` | Uma review `COMMENT` com comentários inline; se a API devolver 422, refaz só com o sumário |
| `rag_reviewer/github_publisher.py` | `_find_diff_position(..., usadas)` | Posição exata da linha no diff; linhas repetidas vão a posições diferentes; igualdade vence substring |
| `rag_reviewer/github_publisher.py` | `_existing_comments`, `_build_review_comments` | Não repete comentário já publicado (o Action roda a cada push); sem posição vai ao sumário |
| `rag_reviewer/github_publisher.py` | `_format_inline_comment`, `_build_summary_body` | Texto do comentário (severidade, norma, como corrigir, ambiguidade) e sumário por severidade, sem emojis |
| `rag_reviewer/reviewer.py` | `RAGReviewer.run`, `_review_all_contexts`, `_review_with_retry` | Orquestra diff, recuperação, LLM por arquivo e publicação; falha num arquivo vira "não revisado"; uma nova tentativa curta em 429; falha em todos faz o job falhar |
| `rag_reviewer/main.py` | `main` | Entrada do Action (`python -m rag_reviewer.main`), sem `show_locals` para não vazar segredos |
| `tests/integration/test_rag_pipeline.py`, `Makefile` | `test-integration` | Fluxo ponta a ponta com GitHub, Qdrant e Groq simulados |
| `arquitetura.md`, `README.md`, `docs/` | `CRITICAL`, `BLOCK_ON_CRITICAL` e `request_changes` removidos; seção do workflow | A documentação descreve a review `COMMENT`, sem bloqueio, e o fluxo do Action |
| `.github/workflows/rag_reviewer.yml` | job `review` | Roda o revisor no `pull_request` (opened, synchronize, reopened) em `.py`; torch só CPU, cache do modelo, cancela a execução anterior do mesmo PR; `QDRANT_COLLECTION=pep8_chunks` |

---

## Pendências (decisões ainda não tomadas)

- **P-004 — Remoção da avaliação humana do planejamento.** Retirar §15.4
  (questionário Likert Q1–Q5) e a métrica de lead time em §15.3 do
  `RAG-Reviewer_Planejamento.md`, além de "questionário aplicado" na Sprint 5.
