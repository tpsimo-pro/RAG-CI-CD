# Relatório de resultados: avaliação oficial de D-010 (dataset realista)

Rodada 1 de 2026-10-08, branch `feat/dataset-realista`. Corpus: a PEP 8 em
inglês (43 chunks, coleção `pep8_chunks`). Dataset de 25 PRs e 35 arquivos
(D-010): 21 arquivos novos e 14 modificados, 23 normas da PEP 8 misturadas,
5 PRs limpos. LLM `qwen/qwen3.8-27b`, temperatura 0.0, 1 repetição, uma chamada
por arquivo. Resultado completo em `evaluation/results_realista.json`.

Esta é a **rodada 1**, com o dataset como foi escrito. Depois dela os erros foram
investigados contra o texto da PEP 8 e 15 deles se mostraram erros de rótulo do
dataset (D-010, "Revisão após a primeira rodada"). O dataset corrigido deve ser
reavaliado na rodada 2, que ainda não foi rodada: a cota diária da Groq estava
esgotada. Os números abaixo **não** valem para o dataset atual; valem para o
dataset da rodada 1. O objetivo do dataset é ensaiar o workflow do GitHub
(seção 8), e os resultados **não são comparáveis** com D-009.

## 1. Resultado principal (rodada 1)

| Métrica | Valor | Meta mínima | Situação |
|---|---|---|---|
| Precisão | 0,8021 | 0,70 | atingida |
| Recall | 0,7857 | 0,65 | atingida |
| F1 | 0,7938 | 0,67 | atingida |

Matriz por linha (796 linhas):

| | Previsto positivo | Previsto negativo |
|---|---|---|
| **Real positivo** | TP = 77 | FN = 21 |
| **Real negativo** | FP = 19 | TN = 679 |

Gate por PR (25 PRs): TP = 19, FP = 5, FN = 1, TN = 0. **Os 5 PRs limpos foram
bloqueados**, então nesta rodada o gate não distingue PR limpo de violador.
Alucinação de localização 0,0. Precisão da referência normativa 0,7792.

## 2. Por família e por norma

| Família | TP/FP/FN/TN | Precisão | Recall | F1 | Citação correta |
|---|---|---|---|---|---|
| `pep8-espacos` | 11/0/1/9 | 1,0000 | 0,9167 | 0,9565 | 1,0000 |
| `pep8-nomes` | 25/3/2/22 | 0,8929 | 0,9259 | 0,9091 | 0,6400 |
| `pep8-imports` | 13/0/4/4 | 1,0000 | 0,7647 | 0,8667 | 1,0000 |
| `pep8-recomendacoes` | 23/5/5/25 | 0,8214 | 0,8214 | 0,8214 | 0,6957 |
| `pep8-layout` | 4/2/4/4 | 0,6667 | 0,5000 | 0,5714 | 0,7500 |
| `pep8-comentarios` | 1/0/5/3 | 1,0000 | 0,1667 | 0,2857 | 1,0000 |

Cobertura por norma (positivas detectadas / positivas), com 4 a 7 positivas por
norma; é indicação, não estatística:

| Recall | Normas |
|---|---|
| 4/4 ou 5/5 | `booleano`, `nulo`, `except_nu`, `espaco_operador`, `espaco_parenteses`, `import_estrela`, `import_topo`, `import_unico`, `instrucoes_compostas`, `nome_classe`, `nome_funcao`, `nome_proibido`, `self_cls` |
| 3/4 | `erro_sufixo`, `espaco_antes_virgula`, `linhas_em_branco`, `not_is`, `tipo_isinstance` |
| 6/7 | `constante_maiuscula` |
| 1/4 | `lambda_atribuido`, `linha_longa` |
| 1/6 | `comentario_inline` |
| 0/4 | `import_ordem` |

## 3. Investigação dos 40 erros

Cada erro foi lido contra o texto da PEP 8 e contra o contexto que o retriever
entregou ao arquivo (`evaluation/retrieval/context_coverage.py`).

| Origem | FPs | FNs | Exemplos |
|---|---|---|---|
| Erro de rótulo do dataset | 11 | 4 | 8 funções públicas sem docstring (a PEP 8 exige), `if x is True:` como negativo (a PEP 8 o lista como Wrong), 2 literais globais em minúsculas (ambíguo), `import_ordem` definida como ordem alfabética (a PEP 8 só exige grupos) |
| Norma ausente do contexto de 8 chunks | 0 | 15 | `comentario_inline` (5), `linha_longa` (3), `lambda_atribuido` (3), `not_is`, `tipo_isinstance`, `linhas_em_branco`, `constante_maiuscula` |
| Falha do modelo | 6 | 2 | `except Exception as exc:` com log (2) e `except:` tolerado com `logger.exception` ou `raise` (2) tratados como violação; linhas de 79 e 76 colunas acusadas como longas (2); `class StockShortage(Exception)` e `print(date , text)` não acusados |
| Acusação dupla benigna | 2 | 0 | `def subtotal(this)` e o corpo `return this.price` |

Observações:

- No dataset já corrigido, a norma está no contexto entregue ao LLM em 53 das
  98 positivas (54%). Mesmo sem a norma no contexto, parte das linhas foi detectada, o que sugere que o modelo acerta
  também por conhecimento prévio da PEP 8. Essa parte será medida na rodada 2,
  juntando `context_coverage` com as detecções.
- O modelo não conta colunas de forma confiável: acusou linhas de 76 e 79
  colunas e deixou passar linhas longas de verdade (`linha_longa` 1/4).
- O ruff acusa todo `except:` nu, e a PEP 8 tolera os que registram o traceback ou
  relançam. O modelo não distingue os dois casos (mesmo problema de D-009).
- Se os 11 FPs e os 4 FNs de rótulo fossem eliminados mantendo o resto, a
  precisão ficaria perto de 0,91; é estimativa, não medição.

## 4. Recuperação (sem LLM)

`recall@k` por linha positiva (98 linhas), consulta por linha, `top_k` 5.

| Config | recall@1 | recall@3 | recall@5 | context_precision@5 |
|---|---|---|---|---|
| Só denso, multilíngue | 0,1327 | 0,1939 | 0,1939 | 0,0827 |
| Híbrido denso + BM25, multilíngue (produção) | 0,3367 | 0,5816 | 0,6837 | 0,1367 |
| Híbrido, MiniLM em inglês | 0,3469 | 0,5714 | 0,6327 | 0,1265 |

Critério do plano (`recall@5 >= 0,95`): não atingido. Recall@5 por norma no
híbrido multilíngue: 1,00 para `nulo`, `except_nu`, `not_is`, `tipo_isinstance`,
`erro_sufixo` e as quatro normas de imports; 0,00 para `nome_funcao`,
`comentario_inline` e `linhas_em_branco`. Esses números são da recuperação por
linha; o contexto que o LLM de fato recebe por arquivo é outra medida
(`context_coverage`, a seguir).

Chunks menores, testados no caminho de produção (contexto de 8 chunks por
arquivo): a norma chega ao contexto em 54% das linhas com 512 palavras, 38% com
256 e 29% com 128, e o contexto cai de 1.835 para 1.102 e 710 palavras por
arquivo. Os chunks menores perdem mais cobertura do que economizam; o
`chunk_size` fica em 512 (D-010).

## 5. Custo

A rodada fez 35 chamadas ao LLM, estimadas em cerca de 130 mil tokens, contra o
teto diário de 200 mil. O processo foi encerrado uma vez pelo sistema por memória baixa
(durante uma chamada ao LLM) e retomado do checkpoint, sem perda de PR.

## 6. Limitações

- Os números são da rodada 1; o dataset foi corrigido depois (seção 3). A rodada 2
  é necessária para ter o número do dataset atual.
- Cerca de 4 positivas por norma: a cobertura por norma é indicação.
- Uma repetição, dataset sintético escrito pelo autor (D-004).
- A recuperação é o principal limite do recall: em 45 das 98 positivas a norma
  não chega ao LLM.
- A PEP 8 é conhecida pelo LLM; sem uma linha de base sem recuperação não se
  separa a contribuição do RAG da do conhecimento prévio.

## 7. Como ler a comparação com D-009

Muda o dataset (25 PRs de vários arquivos contra 75 de um arquivo), mudam as
normas (23 contra 6, com `except:` nu mantido) e o gabarito. A queda de F1 de
0,97 para 0,79 reflete principalmente um teste mais difícil e mais amplo, mais os
erros de rótulo da rodada 1, e não uma piora do sistema.

## 8. Equivalência com o workflow do GitHub (`main-completa`)

O dataset ensaia o Action de `main-completa`. O que há em comum e o que não é
exercitado:

| Etapa do workflow | Na avaliação |
|---|---|
| Gatilho: `pull_request` (opened, synchronize, reopened) em arquivos `*.py` | Não exercitado |
| `DiffCollector`: lista os arquivos do PR pela API (com paginação) e monta `FileDiff` com `filename`, `patch`, `status`, `additions`, `deletions`, `added_lines` | O dataset entrega o `FileDiff` pronto, com `status` e `patch` reais (inclusive de arquivos modificados). A coleta pela API não é testada |
| Recuperação: `retriever` consulta por linha adicionada, une, corta em 8 chunks | Exercitado, com o `retriever` desta branch (difere em detalhes do de `main-completa`: `retriever.py` e `llm_client.py` têm diferenças) |
| LLM: uma chamada por arquivo, resposta em JSON com `line_content`, `violation_description`, `norm_reference`, `severity`, `suggestion` | Exercitado. Mede-se a linha e a norma citada |
| `GitHubPublisher`: comentário inline na posição do patch, review consolidada, tabela de severidades | Não exercitado |
| `request_changes` só com violação `CRITICAL` e `block_on_critical` | O gate da avaliação conta qualquer sinalização como bloqueio |

Não medidos nesta rodada: a qualidade da `suggestion`, a `severity`, a
localização do comentário no diff e o tempo de um job (o Action tem
`timeout-minutes: 10`). A medida do gate (5 de 5 PRs limpos bloqueados) é a
mais pessimista possível frente ao workflow real.

## 9. Próximos passos

- Rodar a rodada 2, com o dataset corrigido, quando a cota da Groq renovar
  (cerca de 130 mil tokens).
- Medir a contribuição do RAG: cruzar `context_coverage` com as detecções
  (a norma no contexto contra a norma ausente).
- Ajustar o prompt ou o corpus para `except:` tolerado e `except Exception:`.
- No workflow, fazer o modelo sinalizar ambiguidade (`docs/TODO-FUTURO.md`, F-004).
- Medir a `suggestion` aplicando a correção e rodando o ruff (fora do escopo
  desta rodada).

---

# Anexo A: relatório de D-009 (PEP 8, 75 PRs)

Rodada de 2026-10-07, branch `feat/corpus-pep8`. Corpus: a PEP 8 completa, em
inglês (`docs/style_guides/pep-0008.md`, 43 chunks, coleção Qdrant
`pep8_chunks`). Dataset de 75 PRs e 2.025 linhas (D-008, reapontado para a
PEP 8 em D-009). LLM `qwen/qwen3.8-27b`, temperatura 0.0, 1 repetição.
Resultado completo em `evaluation/results_pep8.json`. O relatório da rodada
anterior (D-008, corpus de três guias) está no anexo, ao fim.

Esta rodada **não é comparável um a um** com a de D-008: mudaram o corpus, duas
das três regras (as de exceção) e o prompt. A seção 7 diz o que a comparação
permite concluir.

## 1. Resultado principal

| Métrica | D-009 (PEP 8) | D-008 (3 guias) | Meta mínima |
|---|---|---|---|
| Precisão | 0,9583 | 0,8722 | 0,70 |
| Recall | 0,9746 | 0,8788 | 0,65 |
| F1 | 0,9664 | 0,8755 | 0,67 |

As três metas do TCC foram atingidas. Matriz por linha (2.025 linhas):

| | Previsto positivo | Previsto negativo |
|---|---|---|
| **Real positivo** | TP = 115 | FN = 3 |
| **Real negativo** | FP = 5 | TN = 1902 |

Em D-008: TP 116, FP 17, FN 16, TN 1876. Alucinação de localização 0,0. Precisão
da referência normativa 0,9478 (D-008: 0,9397). Acurácia 0,996, secundária e
não representativa (80% das linhas são negativas).

## 2. Por regra

| Regra | TP/FP/FN/TN | Precisão | Recall | F1 | Citação correta |
|---|---|---|---|---|---|
| `pep8-recomendacoes` | 52/0/0/50 | 1,0000 | 1,0000 | 1,0000 | 0,9423 |
| `pep8-nomes` | 47/1/1/49 | 0,9792 | 0,9792 | 0,9792 | 0,9362 |
| `pep8-excecoes` | 16/4/2/42 | 0,8000 | 0,8889 | 0,8421 | 1,0000 |

Recall por sub-regra:

| Sub-regra | Positivas | TP | FN | Recall |
|---|---|---|---|---|
| `booleano` | 26 | 26 | 0 | 1,00 |
| `nulo` | 26 | 26 | 0 | 1,00 |
| `nome_funcao` | 16 | 15 | 1 | 0,94 |
| `nome_classe` | 16 | 16 | 0 | 1,00 |
| `nome_proibido` | 16 | 16 | 0 | 1,00 |
| `except_nu` | 18 | 16 | 2 | 0,89 |

## 3. O que ainda falha

São 8 erros por linha: 3 FNs e 5 FPs. A causa dos FNs não foi investigada.

| Tipo | PR | Linha | Leitura |
|---|---|---|---|
| FN | PR-033 | `def notifyWarehouse(order: Order) -> None:` | `nome_funcao` não sinalizado |
| FN | PR-066 | `        except:` | `except_nu` com `pass`/`continue` não sinalizado |
| FN | PR-072 | `        except:` | idem |
| FP | PR-062 | `    except Exception:` | A PEP 8 recomenda esta forma. O modelo cita Programming Recommendations e diz "exceção genérica sem tratamento" |
| FP | PR-074 | `    except Exception as exc:` | Mesmo padrão: "catching broad Exception instead of specific exceptions" |
| FP | PR-079 | `    except:` | `except:` tolerado pela PEP 8 (o corpo registra com `logger.exception`). O modelo acusou "cláusula nua" |
| FP | PR-080 | `    except:` | `except:` tolerado pela PEP 8 (o corpo faz `raise`). Mesmo erro |
| FP | PR-047 | `    limit = count.l` | Acesso ao atributo `.l`, que não é nome de variável. O modelo citou Names to Avoid |

Quatro dos cinco FPs estão em exceções. Os dois últimos de exceção são os
casos que a PEP 8 tolera (handler que registra o traceback ou relança), e o
modelo não os distinguiu do `except:` nu que viola.

## 4. Nível de PR (gate de CI/CD)

| | Sistema bloqueia | Sistema não bloqueia |
|---|---|---|
| **PR viola** | TP = 52 | FN = 2 |
| **PR limpo** | FP = 3 | TN = 18 |

Em D-008: TP 54, FP 11, FN 0, TN 10. Os 3 PRs de controle bloqueados são
PR-074, PR-079 e PR-080, todos com `except`. Os 2 PRs violadores liberados são
PR-066 e PR-072.

## 5. Recuperação (sem LLM)

`recall@k` sobre as 118 linhas positivas, consulta por linha, `top_k` 5.
`context_precision@5` é a fração dos chunks recuperados que carregam a norma.

| Config | recall@1 | recall@3 | recall@5 | context_precision@5 |
|---|---|---|---|---|
| Consulta por arquivo, multilíngue, só denso | 0,0169 | 0,0169 | 0,0169 | 0,0169 |
| Consulta por linha, multilíngue, só denso | 0,0424 | 0,0763 | 0,0763 | 0,0458 |
| Híbrido denso + BM25 com RRF, multilíngue (produção) | 0,2966 | 0,6186 | 0,7373 | 0,1475 |
| Híbrido, MiniLM em inglês | 0,4322 | 0,6610 | 0,7288 | 0,1458 |
| Consulta por linha, MiniLM em inglês, só denso | 0,0508 | 0,0593 | 0,0593 | 0,0537 |
| Consulta por arquivo, MiniLM em inglês, só denso | 0,0254 | 0,0254 | 0,0254 | 0,0254 |

Em D-008, o híbrido multilíngue deu 0,6667 / 0,8182 / 0,8409 / 0,1894.
Critério do plano (`recall@5 >= 0,95`): não atingido, como antes.

Recall@5 por norma no híbrido multilíngue, medido com um script avulso
(não versionado):

| Norma | Linhas | recall@5 |
|---|---|---|
| comparação com booleano | 26 | 1,00 |
| `except:` nu | 18 | 1,00 |
| `None` com `==`/`!=` | 26 | 0,77 |
| nome `l`/`O`/`I` | 16 | 0,75 |
| nome de classe | 16 | 0,69 |
| nome de função | 16 | 0,00 |

A norma de nome de função é prosa ("Function names should be lowercase...") e
a consulta é a linha `def CalculateTax(...)`, sem palavra em comum. O mesmo
ponto fraco já aparecia em D-008.

Tamanho do chunk, híbrido por linha: recall@5 de 0,7373 (512, padrão), 0,6780
(256), 0,6695 (128) e 0,4915 (64). Mantido 512.

## 6. Custo

Cada chamada ao LLM pede entre 3.700 e 5.000 tokens (o `max_tokens` de 900 da
resposta conta na reserva da Groq). O limite é de 200.000 tokens por dia, então
75 PRs (cerca de 277 mil) não cabem em um dia. A rodada levou três execuções
com checkpoint (`evaluation/.eval_checkpoint.json`), e duas delas foram
encerradas pelo sistema por memória baixa durante a espera da cota. O contexto
da PEP 8 é maior que o de D-008 porque os chunks de Programming
Recommendations têm cerca de 450 palavras cada.

## 7. Como ler a comparação com D-008

- Parte dos FPs de D-008 vinha de normas fora do piloto que estavam no corpus
  (cs 1.1 e outras): 11 dos 21 PRs de controle eram bloqueados. Com o corpus
  restrito à PEP 8, essas normas deixam de existir para o modelo. A melhora de
  precisão não mede só o sistema; mede também um corpus mais estreito.
- O pior resultado de D-008, `captura_silenciosa` (recall 0,13), vinha de um
  exemplo do `coding_standards.md`. A sub-regra saiu, então esse resultado
  não tem equivalente aqui.
- A regra de exceção é outra (`except:` nu, 18 positivas), com 4 FPs. É o
  ponto mais fraco desta rodada.
- A PEP 8 é um texto amplamente conhecido pelos LLMs. O recall de detecção
  (0,97) é bem maior que o recall@5 de recuperação (0,74), e o modelo pode
  estar acertando por conhecimento prévio, sem depender do contexto
  recuperado. Sem uma linha de base sem recuperação, não é possível separar a
  contribuição do RAG da do conhecimento do modelo. Essa linha de base não foi
  medida.
- Uma repetição, dataset sintético escrito pelo autor (D-004) e 18 positivas
  em `except_nu` limitam a generalização.

## 8. Próximos passos possíveis

- Medir uma linha de base sem recuperação (o mesmo prompt, sem os chunks),
  para quantificar o que o RAG contribui sobre a PEP 8.
- Ajustar o prompt ou o corpus para os dois casos tolerados do `except:` nu e
  para `except Exception:`, causa de 4 dos 5 FPs.
- Ao ampliar o dataset com outras normas da PEP 8, limitar cada rodada a cerca
  de 50 PRs ou reduzir os tokens por chamada, para caber na cota diária.
- Decidir o modelo de embedding: o MiniLM em inglês dá recall@1 de 0,43
  contra 0,30 do multilíngue, com recall@5 igual (0,73 e 0,74).

---

# Anexo B: relatório de D-008 (corpus de três guias)

Resultados da rodada anterior, mantidos como registro. O corpus daquela rodada
(`guia_python_pep8.md`, `coding_standards.md`, `architecture_patterns.md`) saiu
do repositório em D-009 e está no histórico do git, antes do commit `339e75a`.


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
