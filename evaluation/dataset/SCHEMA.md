# Esquema do dataset do piloto (23 normas da PEP 8, schema v2)

Arquivo: `pilot_dataset.json`. Validador: `validate_pilot_dataset.py`.
Catálogo de normas: `norms.py`. Decisão: D-010 em `docs/DECISIONS.md`
(spec em `docs/superpowers/specs/2026-10-08-dataset-realista-design.md`).
O corpus indexado é só a PEP 8 (`docs/style_guides/pep-0008.md`).

Lista JSON de PRs, UTF-8 sem BOM. O dataset é um ensaio do workflow real: cada
PR tem um ou mais arquivos, novos ou modificados, e o sistema revisa um arquivo
por chamada ao LLM, vendo só as linhas adicionadas.

## PR

| Campo | Tipo | Regra |
|---|---|---|
| `pr_id` | string | `PR-NNN`, único |
| `description` | string | Texto livre curto |
| `files` | lista | 1 a 3 arquivos, `filename` único no PR |

## Arquivo

| Campo | Tipo | Regra |
|---|---|---|
| `filename` | string | Caminho `.py` |
| `status` | string | `added` ou `modified` |
| `patch` | string | Unified diff. `added`: `@@ -0,0 +1,N @@`. `modified`: hunks (`@@ -a,b +c,d @@`) com contexto, remoções e adições. As linhas `+` são exatamente `added_lines[].line`, na mesma ordem |
| `source_after` | string | Só em `modified`: o arquivo inteiro depois da mudança. Serve ao oráculo (ruff); o pipeline nunca o vê |
| `added_lines` | lista | 8 a 60 entradas, uma por linha adicionada (linhas em branco inclusive) |

Para `modified`, o validador confere que o lado novo de cada hunk (contexto e
adições) está em `source_after`, na posição indicada pelo cabeçalho, e que os
contadores do hunk batem. `status` e as remoções do patch chegam ao `FileDiff`
como no `DiffCollector` do workflow.

## Linha adicionada

| Campo | Tipo | Regra |
|---|---|---|
| `line` | string | Conteúdo da linha, sem o `+` |
| `viola` | bool | `true` se a linha viola uma norma do catálogo |
| `regra` | string ou null | A família da norma, em toda positiva e em todo negativo difícil (a norma que ele imita). `null` em negativo comum |
| `sub_regra` | string ou null | O id da norma se `viola` é true, senão `null` |
| `hard_negative` | bool | `true` só se `viola` é false e a linha imita uma violação |

Uma linha viola no máximo uma norma. Um texto não pode ser positivo e negativo ao
mesmo tempo dentro do mesmo arquivo (D-003 agrupa linhas de texto igual).

## Catálogo (23 normas, 6 famílias)

`regra` é a família e `sub_regra` é a norma. A citação correta de uma detecção é
a seção da PEP 8 da família.

| Família (`regra`) | Seção da PEP 8 | Normas (`sub_regra`) |
|---|---|---|
| `pep8-recomendacoes` | Programming Recommendations | `booleano`, `nulo`, `except_nu`, `not_is`, `tipo_isinstance`, `lambda_atribuido`, `instrucoes_compostas` |
| `pep8-nomes` | Naming Conventions | `nome_funcao`, `nome_classe`, `nome_proibido`, `erro_sufixo`, `self_cls`, `constante_maiuscula` |
| `pep8-layout` | Code Lay-out | `linha_longa`, `linhas_em_branco` |
| `pep8-imports` | Imports | `import_unico`, `import_topo`, `import_estrela`, `import_ordem` |
| `pep8-espacos` | Whitespace in Expressions and Statements | `espaco_operador`, `espaco_parenteses`, `espaco_antes_virgula` |
| `pep8-comentarios` | Comments | `comentario_inline` |

Os ids, os códigos do ruff, as frases âncora do texto da PEP 8 e os padrões de
negativo difícil de cada norma estão em `norms.py`, fonte única do validador, da
conformidade, do gabarito de recuperação e da citação. `linhas_em_branco`,
`import_topo` e `import_ordem` dependem da vizinhança e só aparecem em arquivos
`added`.

## Invariantes (o validador falha se quebradas)

1. **Oráculo, sentido 1.** O ruff roda no arquivo inteiro (`added`: as
   `added_lines`; `modified`: `source_after`) com `E,W,N,I,F403`, 79 colunas, 72
   em comentário e `--preview`, mais uma checagem AST (constantes). Todo achado
   numa linha adicionada precisa casar com a norma rotulada nela; achado sem
   rótulo reprova (licão de D-008). Achados em linhas de contexto são ignorados.
2. **Oráculo, sentido 2.** Toda linha positiva dispara um dos códigos da própria
   norma. Linha negativa não dispara nenhum.
3. O `except:` nu que registra o traceback (`logger.exception`) ou relança
   (`raise`) é tolerado pela PEP 8 e não é violação, embora o ruff o acuse
   (E722). `except Exception:` nunca viola. `except_nu` positivo exige `except:`
   nu com corpo só `pass`/`continue`. Todo `except` está no escopo; o texto de um
   `except` não se repete no arquivo.
4. O arquivo é Python válido (`ast.parse`). `patch` consistente com
   `added_lines` e `source_after`, sem BOM, `pr_id` único, sem sigla em
   `def`/`class`.
5. Norma de vizinhança só em arquivo novo.
6. Cada PR violador mistura de 2 a 5 normas distintas.

## Composição

| | |
|---|---|
| PRs | 25 (20 violadores, 5 limpos) |
| Arquivos | 35 (21 novos, 14 modificados) |
| PRs por nº de arquivos | 16 com 1, 8 com 2, 1 com 3 |
| Linhas adicionadas | 796 |
| Positivas | 98, no mínimo 4 por norma, cada norma em pelo menos 2 PRs |
| Negativos difíceis | 77, no mínimo 2 por norma |

Catálogo do `except`, cada padrão em pelo menos um par (linha `except`, linha
seguinte): `except Exception` + `logger.exception(...)` · `except Exception` +
`raise ... from` · `except` específico + `raise ... from` · `except` específico +
`logger.exception(...)` · `except Exception` + `pass` · `except` específico +
`pass`/`continue` · `except:` + `logger.exception(...)` (tolerado) · `except:` +
`raise` (tolerado) · comentário com `except Exception: pass` · string com
`except Exception: pass`.

## Como as métricas leem o dataset

- **Matriz por linha, Precisão, Recall, F1:** o rótulo é `viola`. A detecção
  numa linha conta pelo rótulo da linha, seja qual for a norma citada (D-003). A
  classificação roda por arquivo e os resultados somam sob o `pr_id`.
- **Gate por PR:** o PR bloqueia se ao menos uma linha de algum arquivo for
  sinalizada.
- **Por família e por norma:** `per_rule` recorta por família (positivas mais
  negativos difíceis da família) e `per_sub_rule_recall` dá o recall de cada
  norma (a tabela de cobertura). Com cerca de 4 positivas por norma é indicação,
  não estatística.
- **Gabarito de recuperação** (`evaluation/retrieval/gold.py`): cada positiva
  aponta o id da norma, e cada id é um enunciado da PEP 8 presente em exatamente
  um chunk do corpus.
- **Localização em bloco:** `misplaced_block_fps` conta os FPs na linha logo
  abaixo de um `except:` nu violador (o corpo), para separar "viu, mas apontou a
  linha errada" de FP genuíno.
- **Não medido:** a `suggestion` e a `severity` das detecções.
