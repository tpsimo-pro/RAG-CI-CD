# Esquema do dataset do piloto (três regras da PEP 8)

Arquivo: `pilot_dataset.json`. Validador: `validate_pilot_dataset.py`.
Decisão: D-002 (e emendas) e D-009 em `docs/DECISIONS.md`. O corpus indexado
é só a PEP 8 (`docs/style_guides/pep-0008.md`).

Lista JSON de PRs, UTF-8 sem BOM.

## PR

| Campo | Tipo | Regra |
|---|---|---|
| `pr_id` | string | `PR-NNN`, único |
| `description` | string | Texto livre curto |
| `filename` | string | Caminho `.py` |
| `patch` | string | Unified diff de arquivo novo (`@@ -0,0 +1,N @@`). As linhas com `+` são exatamente `added_lines[].line`, na mesma ordem |
| `added_lines` | lista | 6 a 60 entradas, uma por linha adicionada (linhas em branco inclusive), sem omitir nenhuma (D-004, D-008) |

O conjunto das linhas de um PR precisa formar Python válido (`ast.parse`) e
nenhuma passa de 79 caracteres.

## Linha adicionada

| Campo | Tipo | Regra |
|---|---|---|
| `line` | string | Conteúdo da linha, sem o `+` |
| `viola` | bool | `true` se a linha viola alguma regra no escopo |
| `regra` | string ou null | `"pep8-recomendacoes"`, `"pep8-nomes"` ou `"pep8-excecoes"` em toda linha positiva e em todo negativo difícil (a regra que ele imita). `null` em negativo comum |
| `sub_regra` | string ou null | Um dos valores abaixo se `viola` é true, senão `null` |
| `hard_negative` | bool | `true` só se `viola` é false e a linha imita uma violação |

As três regras são seções da PEP 8: `pep8-recomendacoes` é Programming
Recommendations (comparações), `pep8-nomes` é Naming Conventions e
`pep8-excecoes` é o item de Programming Recommendations sobre `except:` nu.

| `regra` | `sub_regra` | O que o validador exige na linha |
|---|---|---|
| `pep8-recomendacoes` | `booleano` | `== True` ou `== False` |
| `pep8-recomendacoes` | `nulo` | `== None` ou `!= None` |
| `pep8-nomes` | `nome_funcao` | `def` cujo nome não é `snake_case` |
| `pep8-nomes` | `nome_classe` | `class` cujo nome não é `PascalCase` |
| `pep8-nomes` | `nome_proibido` | `l`, `O` ou `I` atribuído ou iterado (`l = ...`, `for O in ...`) |
| `pep8-excecoes` | `except_nu` | linha `except:` (sem tipo) cujo corpo é só `pass` ou `continue` (checagem por AST do PR, não por linha) |

## Invariantes (o validador falha se quebradas)

1. A `sub_regra` rotulada é exatamente a que os padrões detectam na linha.
   Linha com `viola: false` não contém construção proibida de nenhuma das
   três regras.
2. Nenhum identificador de `def` ou `class` com sigla (`HTTPClient`), por
   estar fora do escopo.
3. Todo PR de controle está limpo para as três regras.
4. `patch` consistente com `added_lines`, sem BOM, sem `pr_id` duplicado.
5. Catálogo mínimo de negativos difíceis coberto (D-004 e os catálogos abaixo).
6. Todo `except` está no escopo: corpo com `logger.exception` ou `raise` no
   primeiro nível, ou só `pass`/`continue` na linha seguinte. Nenhum `except`
   nem corpo de bloco violador repete texto no PR.
7. O código cumpre a PEP 8 (D-009): `conformity.py` roda o ruff (`E`, `W`,
   `N`, `I`, `F403`; 79 colunas, 72 em docstring e comentário) e uma checagem
   AST (`l`/`O`/`I` nunca lidos fora da linha que os atribui). O ruff acusa
   todo `except:` nu (E722), mas a PEP 8 tolera os que registram o traceback
   ou relançam com `raise`; esses são descontados. Um achado só é aceito na
   linha positiva da própria sub-regra: E712 (`booleano`), E711 (`nulo`),
   N802 (`nome_funcao`), N801 (`nome_classe`), E741 e N806 (`nome_proibido`),
   E722 (`except_nu`). Docstring, anotações de tipo, prefixo booleano, número
   de parâmetros e nomes genéricos não são exigidos: não são da PEP 8. O texto
   do dataset tem no máximo 90.000 caracteres.

## Composição atual

| | Recomendações | Nomes | Exceções | Total |
|---|---|---|---|---|
| PRs | 25 (PR-001 a PR-030, sem 009, 010, 019, 020, 030) | 25 (PR-031 a PR-055) | 25 (PR-056 a PR-080) | 75 |
| PRs de controle | 7 | 7 | 7 | 21 |
| Linhas | 567 | 823 | 635 | 2025 |
| Positivas | 52 (26 `booleano`, 26 `nulo`) | 48 (16 por sub-regra) | 18 (`except_nu`) | 118 |
| Negativos difíceis | 50 | 50 | 46 | 146 |

Há no máximo um `except:` nu por PR: com dois, o texto repetido tornaria o
rótulo da linha indistinguível (D-003), e o Python só admite um `except:` nu
por `try`, no último handler.

Catálogo de negativos difíceis de Nomes, cada padrão em ao menos uma linha:
`def __init__` · `def _privado` · `def snake_case` · `class PascalCase` ·
`class ...Error(Exception)` · `lower = ...` · `for i in ...` · `for j in ...` ·
atributo `.l` · comentário com `l = 1` · string com `l = 1`.

Catálogo de negativos difíceis de Exceções. Os padrões de bloco casam a
linha `except` (a marcada `hard_negative`) e a linha logo abaixo dela. A PEP 8
manda usar `except Exception:` para erros de programa e só restringe o
`except:` nu, então as formas com tipo nunca violam:
`except Exception` + `logger.exception(...)` · `except Exception` +
`raise ... from` · `except` específico + `raise ... from` · `except`
específico + `logger.exception(...)` · `except Exception` + `pass` ·
`except` específico + `pass`/`continue` · `except:` + `logger.exception(...)`
(tolerado) · `except:` + `raise` (tolerado) · comentário com
`except Exception: pass` · string com `except Exception: pass`.

## Como as métricas leem o dataset

- **Matriz por linha, Precisão, Recall, F1:** o rótulo é `viola`. A detecção
  numa linha conta pelo rótulo da linha, seja qual for a norma citada (D-003).
- **Por regra:** as mesmas métricas filtradas por `regra`, além do total.
- **Gabarito de retrieval** (`evaluation/retrieval/gold.py`): cada positiva
  aponta uma chave de `norm_map.py`, e cada chave é um enunciado da PEP 8
  presente em exatamente um chunk do corpus.
- **Localização em bloco:** `misplaced_block_fps` conta os FPs na linha
  logo abaixo de um `except` violador (o corpo), para separar "viu, mas
  apontou a linha errada" de FP genuíno.
- **Diagnóstico sugerido:** contar os FPs pela norma citada (Programming
  Recommendations, Naming Conventions ou outra seção da PEP 8), para separar
  "confundiu construção parecida" de "acusou por regra fora do escopo".
