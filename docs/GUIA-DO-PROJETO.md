# Guia do projeto: o que roda, em que ordem, e o que cada avaliação mede

Estado em 2026-09-29, branch `feat/dataset-conforme-corpus`.

---

## 1. O sistema em uma frase

O RAG-Reviewer lê as linhas que um PR adicionou num arquivo Python, busca
no banco vetorial os trechos do guia de estilo que parecem relevantes, e
pede a um LLM que aponte quais linhas violam esses trechos.

Hoje ele não está ligado ao GitHub (a integração foi removida em
`8bc4bd4`). Quem aciona o sistema é só o script de avaliação, usando PRs
sintéticos de um dataset.

---

## 2. As peças

| Peça | Arquivo | O que faz |
|---|---|---|
| Corpus | `docs/style_guides/pep-0008.md` | A PEP 8 inteira, em inglês e em Markdown. É a "base de conhecimento" (D-009) |
| Loader | `indexer/document_loader.py` | Quebra o guia em seções, uma por cabeçalho (níveis 1 a 4), sem mexer na indentação dos exemplos de código |
| Chunker | `indexer/chunker.py` | Divide seções grandes por item de lista (uma norma e seus exemplos), sem sobreposição. 40 seções viram 43 chunks |
| Embedder | `rag_reviewer/embedder.py` | Transforma texto em vetor denso (modelo multilíngue, 384 dimensões) |
| Sparse encoder | `rag_reviewer/sparse_encoder.py` | Transforma texto em vetor esparso BM25 (peso por palavra) |
| Vector store | `rag_reviewer/vector_store.py` | Fala com o Qdrant Cloud: grava e busca |
| Retriever | `rag_reviewer/retriever.py` | Decide o que perguntar ao Qdrant e quais chunks mandar ao LLM |
| LLM client | `rag_reviewer/llm_client.py` | Monta o prompt, chama a Groq (qwen, temperatura 0) e lê o JSON |
| Prompt | `rag_reviewer/prompts/review_template.txt` | O texto enviado ao LLM |

---

## 3. Fluxo 1: indexação (roda uma vez, offline)

```
docs/style_guides/pep-0008.md
  -> loader: 40 seções
  -> chunker: 43 chunks (Programming Recommendations vira 3 e Designing for Inheritance vira 2; as outras 38 seções, 1 cada)
  -> para cada chunk: vetor denso + vetor esparso BM25
  -> grava os 43 pontos no Qdrant, coleção pep8_chunks
```

Comando: `python -m indexer.index_pipeline --recreate`

Só precisa rodar de novo se o corpus ou o modelo de embedding mudar.

---

## 4. Fluxo 2: revisão de um arquivo (o coração do sistema)

Exemplo concreto. Um PR adiciona este arquivo:

```python
def check(order: Order) -> bool:           # linha 1
    """Confere o pedido."""                # linha 2
                                           # linha 3 (em branco)
    if order.paid == True:                 # linha 4  <- viola a PEP 8 (comparação com True)
        return True                        # linha 5
```

### Passo 1: consulta por linha

"Consulta por linha" quer dizer: **o retriever faz uma busca no Qdrant
para cada linha não vazia, separadamente**, em vez de uma busca só com o
arquivo inteiro.

```
linha 1 "def check(order: Order) -> bool:"  -> busca -> top 5 chunks desta linha
linha 2 '"""Confere o pedido."""'           -> busca -> top 5 chunks desta linha
linha 3 (em branco)                         -> não vira busca
linha 4 "if order.paid == True:"            -> busca -> top 5 chunks desta linha
linha 5 "return True"                       -> busca -> top 5 chunks desta linha
```

Por que por linha: se você junta o arquivo inteiro numa busca só, o vetor
vira uma "média" de docstring, assinatura, if e return, e não parece com
nenhuma norma em particular. Buscando `if order.paid == True:` sozinha, a
norma de comparações booleanas vem em 1º lugar.

### Passo 2: cada busca é híbrida

Cada uma dessas buscas usa dois critérios ao mesmo tempo, e o Qdrant junta
os dois rankings (fusão RRF):

- **Denso (semântico):** "o significado desta linha parece com o
  significado deste chunk?"
- **Esparso (BM25, lexical):** "esta linha tem palavras em comum com este
  chunk?" É o que casa `== True` da linha com `== True` escrito na norma.

### Passo 3: união e corte

As 4 buscas devolvem até 20 chunks, muitos repetidos. O retriever:

1. junta tudo e remove repetidos, guardando para cada chunk **o maior
   score** que ele teve em qualquer linha (a correção de `fb05820`; antes
   guardava o da primeira linha, e a norma certa se perdia);
2. ordena por score;
3. fica com os **8 primeiros**.

### Os três "k" (não confundir)

| Parâmetro | Valor | Onde se aplica | Onde está |
|---|---|---|---|
| `top_k` | 5 | **por linha**: cada busca devolve os 5 melhores chunks daquela linha | `TOP_K_CHUNKS=5` no `.env`, lido em `rag_reviewer/config.py` |
| `max_chunks` | 8 | **por arquivo**: depois da união, ficam os 8 melhores, que vão ao LLM | fixo em `rag_reviewer/retriever.py` (`__init__`) |
| k do `recall@k` | 1, 3, 5 | só na métrica da avaliação de recuperação (seção 6.3): a norma apareceu entre os k primeiros chunks **daquela linha**? | `evaluation/retrieval/run_retrieval_eval.py` |

No exemplo acima:

```
4 linhas não vazias x top_k=5  ->  até 20 chunks
remove repetidos               ->  por exemplo, 11 chunks distintos
corte em max_chunks=8          ->  8 chunks vão ao LLM
```

O `recall@5` usa os mesmos 5 do `top_k`. Nenhuma métrica de recuperação
olha o corte em 8.

### Passo 4: uma chamada ao LLM por arquivo

O prompt leva o arquivo inteiro (todas as linhas, inclusive as em branco)
e os 8 chunks. O LLM devolve um JSON com uma lista de violações. Cada uma
tem: a linha (`line_content`), a descrição, a norma citada, a severidade e
a sugestão.

```
arquivo do PR ─┬─> retriever (1 busca híbrida por linha -> união -> 8 chunks) ─┐
               └──────────────────────────────────────────────────────────────┴─> LLM -> violações
```

---

## 5. O dataset

Arquivo: `evaluation/dataset/pilot_dataset.json`. Esquema:
`evaluation/dataset/SCHEMA.md`. Catálogo das normas:
`evaluation/dataset/norms.py`.

O dataset é um ensaio do workflow real do GitHub: PRs com vários arquivos,
novos e modificados, e violações de várias normas misturadas.

- 25 PRs sintéticos (20 violadores e 5 limpos), 35 arquivos (21 novos e 14
  modificados, estes com `patch` de hunks, contexto e remoções), 796 linhas
  adicionadas no total.
- Cada linha tem rótulo: viola ou não viola, e qual norma.
- 23 normas da PEP 8 em 6 famílias (`regra` é a família, `sub_regra` é a norma):

| Família | Normas (exemplo de violação) |
|---|---|
| Programming Recommendations | `booleano` (`== True`), `nulo` (`!= None`), `except_nu` (`except:` + `pass`), `not_is` (`not x is None`), `tipo_isinstance` (`type(a) == type(b)`), `lambda_atribuido`, `instrucoes_compostas` (`a = 1; b = 2`) |
| Naming Conventions | `nome_funcao`, `nome_classe`, `nome_proibido` (`l`, `O`, `I`), `erro_sufixo`, `self_cls`, `constante_maiuscula` |
| Code Lay-out | `linha_longa` (79 colunas), `linhas_em_branco` |
| Imports | `import_unico`, `import_topo`, `import_estrela`, `import_ordem` |
| Whitespace | `espaco_operador`, `espaco_parenteses`, `espaco_antes_virgula` |
| Comments | `comentario_inline` |

- 98 linhas violam (positivas), no mínimo 4 por norma. 77 são "negativos
  difíceis": parecem violação mas não são (ex.: `if x is True:`,
  `except Exception:`). O resto é código comum.
- O ruff é o oráculo do rótulo: toda violação numa linha adicionada tem de
  estar rotulada, e todo rótulo positivo tem de disparar a própria norma. Assim
  o LLM não acha violações reais que o gabarito esqueceu (lição de D-008).
- Três normas dependem da vizinhança (`linhas_em_branco`, `import_topo`,
  `import_ordem`) e só aparecem em arquivos novos, porque o workflow entrega ao
  LLM só as linhas adicionadas.

---

## 6. Os quatro tipos de verificação

Do mais barato ao mais caro:

| # | Verificação | Usa Qdrant? | Usa LLM? | Custo |
|---|---|---|---|---|
| 1 | Testes unitários | não | não | zero |
| 2 | Validação do dataset | não | não | zero |
| 3 | Avaliação de recuperação | sim | não | zero de cota |
| 4 | Avaliação de detecção (a oficial) | sim | sim | ~130 mil tokens (35 arquivos), 1 cota diária do Groq |

### 6.1 Testes unitários

`python -m pytest tests/unit -q`

Testam cada peça isolada, com dublês no lugar do Qdrant e da Groq.
`test_embedder` falha por um problema antigo e conhecido, sem relação com
o resto.

### 6.2 Validação do dataset

`python -m evaluation.dataset.validate_pilot_dataset`

Não avalia o sistema. Confere se o **gabarito** está correto: formato,
composição, se cada linha positiva dispara a própria norma e se nenhuma
violação ficou sem rótulo (ruff + AST, `conformity.py`). Rode sempre que o
dataset mudar.

### 6.3 Avaliação de recuperação

`python -m evaluation.retrieval.run_retrieval_eval --label X --per-line --hybrid`
e depois `python -m evaluation.retrieval.ablation` para a tabela.

**Pergunta que responde:** "para cada linha que viola, a norma certa
aparece entre os chunks que o Qdrant devolve?" Não chama o LLM.

Para cada uma das 98 linhas positivas, faz a busca e olha se algum dos k
primeiros chunks contém a norma daquela linha (`norm_map.py` sabe
reconhecer o texto de cada norma).

- `recall@5`: fração das 98 linhas em que a norma veio entre os 5
  primeiros.
- `context_precision@5`: dos 5 chunks, quantos carregam a norma certa.

**As configurações** montam o sistema peça por peça (rótulos `d010_*` nos
resultados):

| Config | Como busca | Modelo | recall@5 |
|---|---|---|---|
| `d010_L3` | 1 busca por linha, só denso | multilíngue | 0,19 |
| `d010_L4` (produção) | 1 busca híbrida por linha | multilíngue | 0,68 |
| `d010_L4_minilm` | 1 busca híbrida por linha | MiniLM inglês | 0,63 |

A consulta por arquivo inteiro (L0/L1 de rodadas anteriores) não foi refeita:
no corpus da PEP 8 ela já dava recall@5 abaixo de 0,03 em D-009.

Cuidado: essa avaliação olha cada linha **sozinha**. Ela não passa pela
união e pelo corte em 8 do passo 3, e por isso não viu o bug corrigido em
`fb05820`. O que chega de fato ao LLM só aparece na avaliação 6.4.

### 6.4 Avaliação de detecção (a avaliação oficial)

`python -m evaluation.run_evaluation --repeticoes 1`

**Pergunta que responde:** "o sistema inteiro acha as violações certas?"

Para cada um dos 25 PRs:

1. roda o fluxo da seção 4 de verdade (Qdrant + Groq), um arquivo por
   chamada ao LLM;
2. compara as violações que o LLM devolveu com o gabarito, **linha a
   linha**.

A comparação (D-003): o texto de `line_content` de cada violação é
normalizado e procurado entre as linhas do PR. Se bate, aquela linha
conta como "sinalizada". Se não bate com nenhuma, é **alucinação de
localização** e fica fora da matriz, contada à parte.

Cada linha cai numa das 4 células:

| | LLM sinalizou | LLM não sinalizou |
|---|---|---|
| **Linha viola** | TP (acerto) | FN (deixou passar) |
| **Linha não viola** | FP (alarme falso) | TN (acerto) |

Métricas:

- **Precisão** = TP / (TP + FP): quando acusa, acerta?
- **Recall** = TP / (TP + FN): das violações reais, quantas acha?
- **F1**: média harmônica das duas.
- **Precisão de referência normativa**: dos TPs, quantos citam a norma
  certa.
- **Gate por PR**: o PR seria bloqueado se ao menos uma linha fosse
  sinalizada. Compara com "o PR tem violação?".
- Tudo isso também **por regra** e **por sub-regra**.

Grava `evaluation/results.json`. Se a cota do Groq acabar no meio, o
progresso fica em `evaluation/.eval_checkpoint.json` e a próxima execução
continua de onde parou.

Metas do TCC: Precisão >= 0,70, Recall >= 0,65, F1 >= 0,67.

---

## 7. Onde estamos

| Quando | O quê | Resultado |
|---|---|---|
| 07/10 | Avaliação oficial de D-009 (corpus da PEP 8, 75 PRs) | P 0,96 · R 0,97 · F1 0,97 |
| 08/10 | Dataset realista (D-010): 25 PRs, 35 arquivos, 23 normas. Rodada 1 | P 0,80 · R 0,79 · F1 0,79 |
| 08/10 | 40 erros investigados contra o texto da PEP 8 | 15 erros de rótulo do dataset, corrigidos |

**Falta, nesta ordem:**

1. Rodar a rodada 2 da avaliação de detecção com o dataset corrigido (1 cota
   diária do Groq, que zera às 00:00 UTC).
2. Cruzar a cobertura do contexto com as detecções, para medir quanto o modelo
   depende do que o retriever entrega.
3. Acrescentar a rodada 2 ao relatório e abrir o PR.

## 8. Onde cada decisão está escrita

| Assunto | Documento |
|---|---|
| Decisões do piloto (D-001 a D-010) | `docs/DECISIONS.md` |
| Por que o RAG básico falhou e como foi refeito | `docs/superpowers/specs/2026-09-01-refacao-camada-rag-design.md` |
| Qdrant, embedding, LLM, busca híbrida | `docs/adr/ADR-001` a `ADR-004` |
| Formato do dataset | `evaluation/dataset/SCHEMA.md` |
| Como rodar tudo | `README.md` |
