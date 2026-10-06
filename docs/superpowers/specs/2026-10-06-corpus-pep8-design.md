# Corpus: PEP 8 completa, fonte unica

Data: 2026-10-06. Branch: `feat/corpus-pep8` (empilhada em `feat/dataset-conforme-corpus`, PR #12).

## Objetivo

O RAG-Reviewer passa a ter como base de analise e comparacao somente a PEP 8,
completa, verbatim e em ingles, sem chunks redundantes. O piloto continua com
6 regras e 75 PRs (54 violadores, 21 de controle) e e reavaliado para comparar
com o resultado anterior (P 0,8722, R 0,8788, F1 0,8755).

Entendimento confirmado com o autor:

- Corpus final: so a PEP 8 (opcao A). Os tres guias de `docs/style_guides/`
  (`guia_python_pep8`, `coding_standards`, `architecture_patterns`) saem.
- Texto oficial em ingles, sem traducao (a ablacao mostrou o MiniLM em ingles
  acima do multilingue, 0,89 contra 0,84).
- Dataset: manter as 75 PRs; reapontar o gabarito para a PEP 8.
- Codigo "conforme" do dataset cumpre so a PEP 8 (sem docstring Google nem
  anotacoes obrigatorias).
- Fora do escopo: escolha do modelo de embedding e formatacao do codigo do
  proprio projeto.

## Fonte

`python/peps`, `peps/pep-0008.rst`, commit
`5514795ade79a5bf6f3c08c562b02689d0a9feb2`. A PEP declara estar em dominio
publico. `scripts/pep8_rst_to_md.py` converte o reST em Markdown sem alterar o
texto (cabecalhos `=`/`-`/`~` viram `##`/`###`/`####`, `code-block` vira cerca
`python`, literais e referencias viram Markdown). Resultado:
`docs/style_guides/pep-0008.md`, 1494 linhas, 77 blocos de codigo. O titulo e o
cabecalho de origem nao entram no arquivo para nao gerar chunk de ruido; a
proveniencia fica em D-009.

## Achado: duas regras do piloto nao sao da PEP 8

A PEP 8 manda "mencionar excecoes especificas sempre que possivel em vez de um
`except:` nu" e, para capturar erros de programa, manda usar
`except Exception:`. Logo:

- `captura_generica` (`except Exception:` com `pass`/`continue`) NAO viola a
  PEP 8; e a forma que ela recomenda.
- `captura_silenciosa` (excecao especifica com `pass`/`continue`) NAO viola a
  PEP 8. As exigencias de log e re-raise vinham do `coding_standards` 4.1.

A PEP 8 so restringe o `except:` nu (equivale a `except BaseException:`),
tolerado em dois casos: o handler registra o traceback, ou faz limpeza e relanca
com `raise`. Decisao: manter o total de 32 linhas positivas e 18 PRs, trocando
a norma por essa:

| sub_regra antiga | sub_regra nova | linha positiva |
|---|---|---|
| `captura_generica` | `except_nu_silencioso` | `except:` com corpo so `pass`/`continue` |
| `captura_silenciosa` | `except_nu_retorno` | `except:` cujo corpo devolve ou atribui um valor sem registrar nem relancar |

`regra` `coding-4.1` passa a `pep8-excecoes`. As formas antigas viram negativos
dificeis legitimos (`except Exception:`, `except ValueError:` com `pass`), e o
`except:` com `logger.exception` ou `raise` tambem, pelos dois casos
tolerados. Mapa das demais `regra`: `secao-5` -> `pep8-recomendacoes`,
`secao-2` -> `pep8-nomes`.

## Mudancas

### 1. Carregador e chunker (necessario para a PEP 8)

O corpus antigo nao exercitava tres limites do pipeline:

- `_clean_text` colapsa espacos em todo o texto, inclusive dentro de cercas.
  Em codigo Python isso apaga a indentacao e o alinhamento que a PEP 8 mostra
  como certo e errado. Passa a preservar o conteudo das cercas.
- O carregador separa so `#`, `##` e `###`; a PEP 8 usa tambem `####`
  (Names to Avoid, Class Names, etc.). Passa a separar ate nivel 4.
- Secao so com titulo (sem corpo) deixa de virar chunk.
- Em secao grande com cercas, cada cerca e prosa viram chunks soltos: a secao
  Programming Recommendations gera 33 chunks, a maioria de 1 a 9 palavras, com
  o exemplo separado da regra. Passa a empacotar prosa e cercas adjacentes ate
  `chunk_size`, mantendo cada cerca atomica.
- Sem redundancia: `chunk_overlap` padrao do pipeline passa de 64 para 0.

Teste novo: nenhum par de chunks compartilha texto (sem duplicata exata nem
trecho repetido) e nenhum chunk, exceto o ultimo de uma secao, e menor que 20
palavras.

### 2. Mapa de normas

`norm_map.py` e `gold.py` trocam as chaves por `pep8:<secao>:<regra>`,
ancoradas em frases do texto oficial:

| chave | frase ancora (PEP 8) |
|---|---|
| `pep8:recomendacoes:comparacao-booleana` | "Don't compare boolean values to True or False using `==`" |
| `pep8:recomendacoes:comparacao-nulo` | "Comparisons to singletons like None should always be done with" |
| `pep8:nomes:funcao` | "Function names should be lowercase, with words separated by underscores" |
| `pep8:nomes:classe` | "Class names should normally use the CapWords convention" |
| `pep8:nomes:proibido` | "Never use the characters 'l'" |
| `pep8:excecoes:except-nu` | "mention specific exceptions whenever possible instead of using a bare" |

As frases exatas sao conferidas contra `pep-0008.md` por teste.

### 3. Dataset

- `validate_pilot_dataset.py` e `SCHEMA.md`: novos valores de `regra` e
  `sub_regra`, novos padroes para `except:` nu, novo catalogo de negativos
  dificeis de excecao.
- `conformity.py`: ruff `E,W,N,I,F403` a 79 colunas (72 em docstring e
  comentario). Saem `D` (Google), `ANN*` e as checagens AST de
  `coding_standards` (prefixo booleano, ate 4 parametros, sem parametro
  booleano, nomes genericos). Mantidas as que a PEP 8 sustenta: `l`/`O`/`I`,
  nome de uma letra, nome de modulo.
- As 18 PRs de captura sao reescritas conforme a tabela acima; as demais so
  mudam os rotulos `regra`. PRs que falharem na conformidade sao corrigidas.

### 4. Prompts

`system_prompt.txt` e `review_template.txt`: "normas organizacionais" vira
PEP 8; a citacao passa a ser a secao da PEP 8.

### 5. Reavaliacao e documentacao

- Ablacao de recuperacao (L0 a L4) e avaliacao oficial no dataset novo. A
  avaliacao consome a cota diaria do Groq.
- D-009 em `DECISIONS.md` (decisao, fonte, achado das excecoes, mudancas no
  pipeline); atualizar `STATUS.md`, `GUIA-DO-PROJETO.md`, `RELATORIO-RESULTADOS.md`,
  `README.md`, `arquitetura.md`, ADR-002 e ADR-004 onde citam o corpus antigo.
- Comparacao antes e depois no relatorio. Se o recall de recuperacao cair,
  investigar o chunking antes de concluir.

## Criterios de sucesso

1. `docs/style_guides/` tem so `pep-0008.md`, texto identico ao reST oficial
   salvo marcacao.
2. `pytest` passa; `ruff check` sem erros nas regras ja configuradas.
3. Teste de redundancia passa sobre o corpus real.
4. `validate_pilot_dataset.py` passa: 75 PRs, 54 violadores, 21 controles.
5. Indexacao no Qdrant e ablacao L0 a L4 executam; avaliacao oficial gera
   P, R, F1 e matriz de confusao no dataset novo.
6. `docs/` reflete o corpus novo, sem referencias aos tres guias removidos.

## Riscos

- Os resultados nao sao comparaveis um a um com os de antes: muda o corpus e
  mudam duas regras. O relatorio deve dizer isso.
- A cota do Groq pode atrasar a avaliacao oficial (rodadas anteriores
  esperaram ate 12 minutos).
- PEP 8 em ingles com prompt em portugues: a ablacao do MiniLM ingles
  cobre o retrieval, mas a citacao da norma no JSON do LLM precisa ser
  verificada.
