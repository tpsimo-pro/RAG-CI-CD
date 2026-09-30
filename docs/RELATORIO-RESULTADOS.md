# Relatório de resultados: avaliação oficial de D-008

Rodada de 2026-09-29, branch `feat/dataset-conforme-corpus`. Dataset de
75 PRs e 2.025 linhas conforme o corpus inteiro (D-008), retriever com a
correção de `fb05820`, modelo `qwen/qwen3.8-27b` na Groq, temperatura 0,
1 repetição (D-005). Resultado completo em `evaluation/results.json`.

Como o sistema e as avaliações funcionam: `docs/GUIA-DO-PROJETO.md`.

## 1. Resultado principal

As três metas do TCC foram atingidas.

| Métrica | Antes da correção (`b2eddf4`) | Agora | Meta | Situação |
|---|---|---|---|---|
| Precisão | 0,7944 | **0,8722** | >= 0,70 | atingida |
| Recall | 0,6439 | **0,8788** | >= 0,65 | atingida |
| F1 | 0,7113 | **0,8755** | >= 0,67 | atingida |

Matriz por linha (N = 2.025):

| | Sinalizou | Não sinalizou |
|---|---|---|
| **Linha viola** | TP = 116 (antes 85) | FN = 16 (antes 47) |
| **Linha não viola** | FP = 17 (antes 22) | TN = 1.876 |

- Alucinação de localização: 0 de 133 detecções.
- Precisão de referência normativa (TPs que citam a norma certa): 0,9397
  (antes 0,7412).
- FPs no corpo de `except` violador: 0.

A única mudança entre as duas rodadas foi a correção do retriever: a
união por arquivo passou a guardar o maior score de cada chunk, e a
norma certa deixou de ser cortada antes de chegar ao LLM.

## 2. Por regra

| Regra | TP/FP/FN/TN | Precisão | Recall | F1 | Ref. normativa |
|---|---|---|---|---|---|
| Seção 5 (comparações) | 52/0/0/50 | 1,0000 | 1,0000 | 1,0000 | 1,0000 |
| Seção 2 (nomenclatura) | 46/2/2/48 | 0,9583 | 0,9583 | 0,9583 | 0,8478 |
| cs 4.1 (exceções) | 18/5/14/27 | 0,7826 | 0,5625 | 0,6545 | 1,0000 |

Recall por sub-regra:

| Sub-regra | Positivas | TP | FN | Recall | Antes |
|---|---|---|---|---|---|
| `booleano` | 26 | 26 | 0 | 1,00 | 0,46 |
| `nulo` | 26 | 26 | 0 | 1,00 | 0,69 |
| `nome_classe` | 16 | 16 | 0 | 1,00 | 0,94 |
| `nome_funcao` | 16 | 14 | 2 | 0,88 | 0,88 |
| `nome_proibido` | 16 | 16 | 0 | 1,00 | 1,00 |
| `captura_generica` | 16 | 16 | 0 | 1,00 | 0,56 |
| `captura_silenciosa` | 16 | 2 | 14 | **0,13** | 0,06 |

## 3. O que ainda falha

### 3.1 `captura_silenciosa`: 14 dos 16 FNs

Todos os FNs de exceção são `except <ExceçãoEspecífica>:` com corpo
`pass` ou `continue` (PR-056 a PR-069). Depois da correção, a norma cs
4.1 chega ao LLM em todos esses PRs, então a perda é do modelo, não do
retriever.

Causa provável: o exemplo da cs 4.1 no corpus
(`docs/style_guides/coding_standards.md`) rotula como "Incorreto" só a
captura genérica (`except Exception: pass`) e como "Correto" a "captura
específica com logging". O enunciado ("toda exceção capturada deve ser
logada ou re-lançada") cobre a captura específica silenciosa, mas o
exemplo sugere que exceção específica está liberada. Não foi testado;
mexer no corpus muda a fonte normativa e é uma decisão à parte.

### 3.2 `nome_funcao`: 2 FNs

As duas no mesmo PR (PR-033: `sendConfirmation`, `notifyWarehouse`). Na
ablação, nenhuma linha `def` em camelCase recupera a norma de
nomenclatura; o modelo acerta 14 de 16 mesmo assim.

### 3.3 Os 17 FPs

Nenhum FP em linha em branco ou de docstring (o risco previsto em D-008
não se materializou).

| Grupo | FPs | Norma citada | Leitura |
|---|---|---|---|
| `def` sinalizado por responsabilidade única | 8 | cs 1.1 | Norma subjetiva, fora do piloto; 6 dos 8 são funções `is_`/`has_` |
| `except Exception as exc:` que loga ou re-lança (negativo difícil) | 5 | cs 4.1 | Erro real do modelo: a captura está correta. Espelho do 3.1: o modelo julga pelo tipo da exceção, não pelo corpo |
| Ordem de importação | 2 | cs 6.1 | Um é negativo difícil da Seção 2 (`def _remove_old`, linha citada errada) |
| Docstring | 1 | cs 5.1 | `def show_results` |
| `zone = "I"` (negativo difícil) | 1 | pep8 2.1 | O `I` é texto de uma string, não um nome |

7 dos 17 FPs são negativos difíceis, escritos para parecer violação.

## 4. Nível de PR (gate de CI/CD)

| | Bloqueia | Não bloqueia |
|---|---|---|
| **PR viola** | TP = 54 | FN = 0 |
| **PR limpo** | FP = 11 | TN = 10 |

Todo PR com violação seria bloqueado. Metade dos PRs de controle também
(11 de 21), puxada pelos FPs do item 3.3. Para um gate real, é o número
que mais pesa: um FP por PR já bloqueia o merge.

## 5. Recuperação (sem LLM)

Ablação refeita no dataset atual (`74fb75a`). L4 (produção): recall@5 de
0,84. Seção 5, cs 4.1 e nomes de classe em 1,0; as falhas são nomes de
função (0 de 16) e `l`/`O`/`I` (11 de 16). Com o BM25 ativo, o MiniLM em
inglês chega a 0,89, acima do multilíngue.

Na detecção, os nomes de função ficam em 0,88 mesmo sem a norma no
contexto: o modelo conhece a convenção de nomes do PEP 8.

## 6. Custo

A rodada gastou a cota diária de tokens da Groq: os 4 últimos PRs
esperaram de 1 a 12 minutos cada pela liberação da cota. O contexto do
RAG tem em média 2.525 caracteres por PR, contra 13.203 do corpus
inteiro.

## 7. Limitações

- Dataset sintético, escrito pelo autor (D-004).
- Uma repetição (D-005): com temperatura 0, rodadas anteriores deram
  desvio-padrão 0.
- A calibração do retriever e a avaliação usam o mesmo dataset; não há
  conjunto de teste separado. A correção de `fb05820` foi achada
  analisando os FNs desta avaliação, embora o defeito valesse para
  qualquer diff.
- As violações do dataset são próximas dos exemplos do corpus, o que
  favorece a busca lexical.

## 8. Próximos passos possíveis

- Decidir sobre `captura_silenciosa`: aceitar como limitação do modelo ou
  ajustar o exemplo da cs 4.1 (muda o corpus; exigiria nova rodada).
- Decidir o modelo de embedding (ADR-002): o MiniLM em inglês superou o
  multilíngue na ablação nova.
- Atualizar ADR-002 e ADR-004, que citam os números da ablação antiga.
