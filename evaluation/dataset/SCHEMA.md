# Esquema do dataset do piloto (três regras)

Arquivo: `pilot_dataset.json`. Validador: `validate_pilot_dataset.py`.
Decisão: emendas 1 e 2 de D-002 em `docs/DECISIONS.md`.

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
| `regra` | string ou null | `"secao-5"`, `"secao-2"` ou `"coding-4.1"` em toda linha positiva e em todo negativo difícil (a regra que ele imita). `null` em negativo comum |
| `sub_regra` | string ou null | Um dos valores abaixo se `viola` é true, senão `null` |
| `hard_negative` | bool | `true` só se `viola` é false e a linha imita uma violação |

| `regra` | `sub_regra` | O que o validador exige na linha |
|---|---|---|
| `secao-5` | `booleano` | `== True` ou `== False` |
| `secao-5` | `nulo` | `== None` ou `!= None` |
| `secao-2` | `nome_funcao` | `def` cujo nome não é `snake_case` |
| `secao-2` | `nome_classe` | `class` cujo nome não é `PascalCase` |
| `secao-2` | `nome_proibido` | `l`, `O` ou `I` atribuído ou iterado (`l = ...`, `for O in ...`) |
| `coding-4.1` | `captura_generica` | linha `except Exception` cujo corpo é só `pass` ou `continue` (checagem por AST do PR, não por linha) |
| `coding-4.1` | `captura_silenciosa` | linha `except` de exceção específica cujo corpo é só `pass` ou `continue` |

## Invariantes (o validador falha se quebradas)

1. A `sub_regra` rotulada é exatamente a que os padrões do guia detectam na
   linha. Linha com `viola: false` não contém construção proibida de nenhuma
   das três regras.
2. Nenhum identificador de `def` ou `class` com sigla (`HTTPClient`), por
   estar fora do escopo.
3. Todo PR de controle está limpo para as três regras.
4. `patch` consistente com `added_lines`, sem BOM, sem `pr_id` duplicado.
5. Catálogo mínimo de negativos difíceis coberto (Seção 5 de D-004 e Seção 2
   abaixo).
6. Todo `except` está no escopo da emenda 2 (tipo `Exception` ou
   específico; corpo com `raise ... from` ou `logger.exception` no primeiro
   nível, ou só `pass`/`continue` na linha seguinte). Nenhum `except` nem corpo de bloco violador repete texto
   no PR.
7. O código cumpre o corpus inteiro (D-008): `conformity.py` roda o ruff
   (E, W, N, D google, ANN001/201/202/204, I, F403; 79 colunas, 72 em
   docstring e comentário; só D105 ignorado) e checagens AST (prefixo
   booleano, até 4 parâmetros, sem parâmetro booleano, nomes genéricos,
   nomes de uma letra, `l`/`O`/`I` nunca lidos, nomes de módulo, seções
   `Args`/`Returns`/`Raises`, segredos). Um achado só é aceito na linha
   positiva da própria sub-regra: E712 (`booleano`), E711 (`nulo`), N802
   (`nome_funcao`), N801 (`nome_classe`), E741, N806, uma letra e nome de
   módulo (`nome_proibido`). O texto do dataset tem no máximo 90.000 caracteres.

## Composição atual

| | Seção 5 | Seção 2 | coding 4.1 | Total |
|---|---|---|---|---|
| PRs | 25 (PR-001 a PR-030, sem 009, 010, 019, 020, 030) | 25 (PR-031 a PR-055) | 25 (PR-056 a PR-080) | 75 |
| PRs de controle | 7 | 7 | 7 | 21 |
| Linhas | 567 | 823 | 635 | 2025 |
| Positivas | 52 (26 `booleano`, 26 `nulo`) | 48 (16 por sub-regra) | 32 (16 por sub-regra) | 132 |
| Negativos difíceis | 50 | 50 | 32 | 132 |

Catálogo de negativos difíceis da Seção 2, cada padrão em ao menos uma linha:
`def __init__` · `def _privado` · `def snake_case` · `class PascalCase` ·
`class ...Error(Exception)` · `lower = ...` · `for i in ...` · `for j in ...` ·
atributo `.l` · comentário com `l = 1` · string com `l = 1`.

Catálogo de negativos difíceis da coding 4.1. Os padrões de bloco casam a
linha `except` (a marcada `hard_negative`) e a linha logo abaixo dela:
`except Exception` + `logger.exception(...)` · `except Exception` + `raise ... from` ·
`except` específico + `raise ... from` · `except` específico +
`logger.exception(...)` · comentário com `except Exception: pass` · string
com `except Exception: pass`.

## Como as métricas leem o dataset

- **Matriz por linha, Precisão, Recall, F1:** o rótulo é `viola`. A detecção
  numa linha conta pelo rótulo da linha, seja qual for a norma citada (D-003).
- **Por regra:** as mesmas métricas filtradas por `regra`, além do total
  (ainda não implementado em `metrics.py`).
- **Gabarito de retrieval** (`evaluation/retrieval/gold.py`): cada positiva
  aponta uma chave de `norm_map.py`. As de nomenclatura aceitam chunks do
  `guia_python_pep8.md` ou do `coding_standards.md`, que trazem as mesmas
  sub-regras. As de exceção apontam `NORM_EXCECAO`, só com chunks do
  `coding_standards.md` (4.1).
- **Localização em bloco:** `misplaced_block_fps` conta os FPs na linha
  logo abaixo de um `except` violador (o corpo), para separar "viu, mas
  apontou a linha errada" de FP genuíno.
- **Diagnóstico sugerido:** contar os FPs pela norma citada (Seção 5,
  nomenclatura ou outra norma do corpus), para separar "confundiu construção
  parecida" de "acusou por regra fora do escopo".
