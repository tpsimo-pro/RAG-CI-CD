# Dataset realista: 25 PRs com varias normas da PEP 8 misturadas

Data: 2026-10-08. Branch: `feat/dataset-realista` (a partir da `main` com D-009).
Decisao: D-010.

## Objetivo

O resultado local deve ser um ensaio do que o workflow do GitHub vai produzir
num PR real (`main-completa`: Action no PR, diff pela API, so `added_lines` e o
nome do arquivo ao LLM, uma chamada por arquivo, comentarios inline). Para isso o
dataset deixa de ser 75 PRs de 1 arquivo novo com 6 normas e passa a ser 25 PRs
realistas, com varios arquivos, arquivos novos e modificados, e 23 normas da
PEP 8 misturadas.

Entendimento confirmado com o autor:

- Menos PRs, mais variedade de normas. "Toda a PEP 8" nao cabe: varias regras nao
  se rotulam num diff isolado ("seja consistente", "use bom senso"). Entram as
  normas verificaveis.
- Formato: 25 PRs (o desenho aprovado dizia 30, o autor pediu 25 para folga de
  tokens), a maioria com 1 arquivo, alguns com 2 ou 3. Cerca de 35 chamadas ao LLM
  por rodada, contra o teto diario de cerca de 54.
- Arquivos: 60% novos, 40% modificados, com `patch` de hunks, contexto e linhas
  removidas.
- Catalogo mantido mesmo sabendo que o ruff cobre quase todas as normas: o ruff
  serve de oraculo do rotulo, e o argumento "RAG contra linter" fica para depois.
- Fora do escopo: portar o workflow de `main-completa`, a checagem da
  `suggestion` (aplicar a correcao e rodar o ruff; proximo passo), linha de base
  sem recuperacao, decisao do modelo de embedding.

## Catalogo de normas (fonte unica)

23 normas em 6 familias. A familia e o campo `regra`; a norma e o campo
`sub_regra` (nomes dos campos mantidos para nao mexer em `metrics.py`:
`per_rule` vira o recorte por familia e `per_sub_rule_recall` vira a tabela de
cobertura por norma). Cada norma tem uma frase ancora do texto da PEP 8 (para o
gabarito de recuperacao), os codigos do ruff que a detectam e o padrao de citacao
da familia.

| Familia (`regra`, secao da PEP 8) | Norma (`sub_regra`) | Oraculo |
|---|---|---|
| `pep8-recomendacoes` (Programming Recommendations) | `booleano`, `nulo`, `except_nu` (existentes) | ruff E712, E711, E722 |
| | `not_is` (`not x is y`) | E714 |
| | `tipo_isinstance` (`type(a) == type(b)`) | E721 |
| | `lambda_atribuido` | E731 |
| | `instrucoes_compostas` | E701, E702 |
| `pep8-nomes` (Naming Conventions) | `nome_funcao`, `nome_classe`, `nome_proibido` (existentes) | N802, N801, E741/N806 |
| | `erro_sufixo` (exceção sem `Error`) | N818 |
| | `self_cls` | N804, N805 |
| | `constante_maiuscula` | AST (o ruff nao pega) |
| `pep8-layout` (Code Lay-out) | `linha_longa` (79 colunas) | E501 |
| | `linhas_em_branco` | E301, E302, E303, E305 |
| `pep8-imports` (Imports) | `import_unico`, `import_topo`, `import_estrela`, `import_ordem` | E401, E402, F403, I001 |
| `pep8-espacos` (Whitespace in Expressions and Statements) | `espaco_operador`, `espaco_parenteses`, `espaco_antes_virgula` | E225, E201/E202, E203 |
| `pep8-comentarios` (Comments) | `comentario_inline` | E261, E262, E265 |

Ficaram de fora duas normas que eu havia proposto e a PEP 8 nao tem: `not x in y`
(o texto so manda `is not`) e "espaco depois da virgula" (o texto fala de espaco
antes da virgula). Tres normas dependem de vizinhanca e so aparecem em arquivos
novos: `linhas_em_branco`, `import_topo` e `import_ordem`.

O catalogo mora em um unico modulo (`evaluation/dataset/norms.py`): id, familia,
codigos do ruff, frase ancora, padrao de citacao e a marca "so em arquivo novo".
`norm_map.py`, `gold.py`, `metrics.py`, `conformity.py` e o validador derivam dele,
em vez de repetir 23 normas em cinco arquivos.

## Schema v2

```json
{"pr_id": "PR-001", "description": "...",
 "files": [{"filename": "...", "status": "added|modified", "patch": "...",
            "source_after": "... so em modified ...",
            "added_lines": [{"line": "...", "viola": false, "regra": null,
                             "sub_regra": null, "hard_negative": false}]}]}
```

- `added_lines` das linhas `+` do `patch`, na ordem, como hoje. Cada linha viola no
  maximo uma norma.
- `modified`: o `patch` tem hunks (`@@ -a,b +c,d @@`), contexto e remocoes, e
  `source_after` guarda o arquivo inteiro depois da mudanca. O validador confere que
  o lado novo de cada hunk esta em `source_after` na posicao `c`. O pipeline nunca
  ve `source_after`, so as `added_lines`; ele serve ao oraculo.
- `added`: o `patch` e `@@ -0,0 +1,N @@`, como hoje.
- O dataset de D-009 (75 PRs) sai da arvore e fica no historico do git.

## Validador (oraculo)

- O ruff roda no arquivo inteiro (`added`: as `added_lines`; `modified`:
  `source_after`). Todo achado numa linha **adicionada** precisa casar com a norma
  rotulada nela; achado sem rotulo faz o validador falhar (licao de D-008:
  violacao real sem rotulo vira falso positivo). Achados em linhas de contexto
  sao ignorados: codigo pre-existente.
- Um teste parametrizado confere, para cada norma, que uma linha-exemplo gera
  exatamente os codigos declarados no catalogo, com o ruff instalado. Assim o
  catalogo nao diverge da versao do ruff.
- `constante_maiuscula` usa AST. O `except:` nu tolerado pela PEP 8 (corpo com
  `logger.exception` ou `raise`) continua descontado, como em D-009.
- Conformidade: ruff `E,W,N,I,F403` a 79 colunas, 72 em comentario, `--preview`.
- Composicao exigida: 25 PRs (20 violadores, 5 limpos), 35 arquivos (21 novos,
  14 modificados; 16 PRs com 1 arquivo, 8 com 2, 1 com 3), 8 a 60 linhas adicionadas
  por arquivo, cada PR violador com 2 a 5 normas distintas, cada norma com pelo
  menos 4 linhas positivas em pelo menos 2 PRs e pelo menos 2 negativos dificeis
  (`x is not None`, `isinstance(a, B)`, `MAX_SIZE = 1`, `def snake_case`...).
- Invariantes antigas mantidas: Python valido, 79 colunas, `patch` consistente com
  `added_lines`, sem BOM, `pr_id` unico, sem sigla em `def`/`class`, um `except:`
  nu por PR e texto de `except` nao repetido.

## Harness

- `run_evaluation`: `_load_dataset`, `_build_gold_lines` e `_build_file_diff`
  passam a iterar `files`. A classificacao (D-003) roda por arquivo, para linhas de
  texto igual em arquivos diferentes nao colidirem; os resultados sao agregados
  sob o `pr_id`, e o gate por PR continua "ha alguma sinalizacao no PR".
  `FileDiff.status` recebe o status real do arquivo. O checkpoint continua por PR
  (schema 4).
- `gold.py`: `GoldLine` ganha `filename`; 23 chaves de norma em `norm_map.py`,
  cada uma ancorada no texto da PEP 8 e presente em exatamente um chunk do corpus
  (teste existente, estendido).
- `run_retrieval_eval`: itera `files`; a consulta por arquivo usa (PR, arquivo).
- `metrics.py`: os padroes de citacao passam a ser 6, um por familia, derivados do
  catalogo (por exemplo, `pep8-espacos` aceita "Whitespace", "Pet Peeves" e "Other
  Recommendations").
- `validate_pilot_dataset.py`: reescrito para o schema v2 e o catalogo.

## Custo

Cerca de 35 chamadas a 3.700 tokens, cerca de 130 mil tokens, contra o teto diario
de 200 mil. A rodada cabe em um dia, com folga de cerca de 70 mil.

## Equivalencia com o workflow real

O relatorio ganha uma secao que compara a avaliacao com o Action de
`main-completa`: o diff vem da API (`FileDiff` com `status`, `patch`,
`added_lines`), o retriever consulta por linha adicionada, o LLM recebe um arquivo
por chamada e responde `violations` com `norm_reference` e `suggestion`, e o
publisher comenta por linha. A avaliacao mede detecao por linha e a norma citada.
Nao mede a `suggestion` nem a `severity`, e o gate conta qualquer sinalizacao como
bloqueio, enquanto o workflow so pede mudancas com `CRITICAL`.

## Criterios de sucesso

1. `validate_pilot_dataset.py` passa: 25 PRs, 35 arquivos, composicao acima.
2. `pytest` passa, exceto o teste de embedder que ja falhava; teste por norma contra
   o ruff instalado.
3. Ablacao de recuperacao (L4 hibrido) e avaliacao oficial rodam; o resultado sai
   em `evaluation/results_realista.json`, com a tabela de cobertura por norma.
4. D-010, SCHEMA, README, GUIA, STATUS e RELATORIO refletem o dataset novo.

## Riscos

- Resultados nao comparaveis com D-009: mudam o dataset, as normas e o gabarito.
- Cerca de 4 positivas por norma: a cobertura por norma e indicacao, nao
  estatistica. O agregado (P, R, F1 sobre cerca de 100 linhas positivas) e o que
  vale como numero.
- Fragmentos de arquivos modificados: o LLM ve `added_lines` sem contexto, entao
  linhas dentro de blocos perdem a indentacao relativa. Nenhuma norma de contexto
  entra em arquivo modificado.
- O ruff do `.venv` e o 0.4.9; o autor tem uma alteracao local pedindo 0.16.10. Os
  codigos do catalogo sao verificados contra o ruff instalado (teste por norma).
- Escrever cerca de 35 arquivos realistas e o maior custo da tarefa.

## Plano de execucao

1. Spec e branch (este documento).
2. `evaluation/dataset/norms.py` com o catalogo e os testes por norma contra o ruff.
3. Conformidade/oraculo (`conformity.py`) e validador v2, com testes.
4. Harness: `run_evaluation`, `gold.py`, `run_retrieval_eval`, `metrics.py`,
   `norm_map.py`, com testes.
5. Dataset: escrever os 25 PRs, gerar o JSON, validar.
6. Ablacao de recuperacao e avaliacao oficial.
7. Documentacao e memoria.
