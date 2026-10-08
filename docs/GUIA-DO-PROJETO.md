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
`evaluation/dataset/SCHEMA.md`.

- 75 PRs sintéticos, um arquivo cada, com 2.025 linhas no total.
- Cada linha tem rótulo: viola ou não viola, e qual regra.
- 3 regras, 25 PRs cada:

| Regra | Sub-regras | Exemplo de violação |
|---|---|---|
| PEP 8, Programming Recommendations (comparações) | `booleano`, `nulo` | `if x == True:`, `if y != None:` |
| PEP 8, Naming Conventions | `nome_funcao`, `nome_classe`, `nome_proibido` | `def CalculateTax`, `class order_item`, `I = 3` |
| PEP 8, Programming Recommendations (`except:` nu) | `except_nu` | `except:` seguido de `pass` ou `continue` |

- 118 linhas violam (positivas). 146 são "negativos difíceis": parecem
  violação mas não são (ex.: `if x is True:`). O resto é código comum.
- 21 dos 75 PRs são de controle: não têm nenhuma violação.
- D-008: todo o código fora das linhas rotuladas cumpre o corpus inteiro
  (docstrings, tipos, linhas em branco), para o LLM não achar violações
  reais que o gabarito não rotulou.

---

## 6. Os quatro tipos de verificação

Do mais barato ao mais caro:

| # | Verificação | Usa Qdrant? | Usa LLM? | Custo |
|---|---|---|---|---|
| 1 | Testes unitários | não | não | zero |
| 2 | Validação do dataset | não | não | zero |
| 3 | Avaliação de recuperação (L0 a L4) | sim | não | zero de cota |
| 4 | Avaliação de detecção (a oficial) | sim | sim | ~140 mil tokens, 1 cota diária do Groq |

### 6.1 Testes unitários

`python -m pytest tests/unit -q`

Testam cada peça isolada, com dublês no lugar do Qdrant e da Groq.
`test_embedder` falha por um problema antigo e conhecido, sem relação com
o resto.

### 6.2 Validação do dataset

`python -m evaluation.dataset.validate_pilot_dataset`

Não avalia o sistema. Confere se o **gabarito** está correto: formato,
contagens, se cada linha positiva viola mesmo (ruff + AST), se o resto do
código cumpre o corpus inteiro (`conformity.py`, D-008). Rode sempre que o
dataset mudar.

### 6.3 Avaliação de recuperação (ablação L0 a L4)

`python -m evaluation.retrieval.run_retrieval_eval --label X --per-line --hybrid`
e depois `python -m evaluation.retrieval.ablation` para a tabela.

**Pergunta que responde:** "para cada linha que viola, a norma certa
aparece entre os chunks que o Qdrant devolve?" Não chama o LLM.

Para cada uma das 118 linhas positivas, faz a busca e olha se algum dos k
primeiros chunks contém a norma daquela linha (`norm_map.py` sabe
reconhecer o texto de cada norma).

- `recall@5`: fração das 118 linhas em que a norma veio entre os 5
  primeiros.
- `context_precision@5`: dos 5 chunks, quantos carregam a norma certa.

**As configurações L0 a L4** são o sistema montado peça por peça, para
medir quanto cada peça ajuda:

| Config | Como busca | Modelo | recall@5 |
|---|---|---|---|
| L0 | 1 busca com o arquivo inteiro, loader antigo | MiniLM inglês | 0,64 |
| L1 | igual, com o loader e chunker atuais | MiniLM inglês | 0,70 |
| L2 | 1 busca por linha | MiniLM inglês | 0,16 |
| L3 | 1 busca por linha | multilíngue | 0,67 |
| L4 (produção) | 1 busca híbrida por linha | multilíngue | 0,84 |
| L4 com o MiniLM | 1 busca híbrida por linha | MiniLM inglês | 0,89 |

Cuidado: essa avaliação olha cada linha **sozinha**. Ela não passa pela
união e pelo corte em 8 do passo 3, e por isso não viu o bug corrigido em
`fb05820`. O que chega de fato ao LLM só aparece na avaliação 6.4.

### 6.4 Avaliação de detecção (a avaliação oficial)

`python -m evaluation.run_evaluation --repeticoes 1`

**Pergunta que responde:** "o sistema inteiro acha as violações certas?"

Para cada um dos 75 PRs:

1. roda o fluxo da seção 4 de verdade (Qdrant + Groq);
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
| 29/09 | Avaliação oficial com o bug do retriever (`b2eddf4`) | P 0,79 · R 0,64 · F1 0,71. Recall abaixo da meta |
| 29/09 | Bug achado: a norma certa não chegava ao LLM | Corrigido em `fb05820`. Norma no contexto: 25 de 54 PRs violadores -> 47 de 54 |
| 29/09 | Ablação L0 a L4 refeita no dataset atual (`74fb75a`) | L4 com recall@5 de 0,84. Falhas só em nomenclatura |

**Falta, nesta ordem:**

1. Rodar a avaliação de detecção com o retriever corrigido (1 cota
   diária do Groq).
2. Escrever a subseção "Resultado" em D-008, comparando com a rodada de
   `b2eddf4`.
3. Atualizar os números de detecção no README.
4. Enviar a branch e abrir o PR para a `main`.

**Decisão em aberto:** o modelo em inglês superou o multilíngue na
ablação nova (0,89 contra 0,84). Manter o multilíngue ou trocar muda o
ADR-002 e exige reindexar a coleção antes do passo 1.

---

## 8. Onde cada decisão está escrita

| Assunto | Documento |
|---|---|
| Decisões do piloto (D-001 a D-008) | `docs/DECISIONS.md` |
| Por que o RAG básico falhou e como foi refeito | `docs/superpowers/specs/2026-09-01-refacao-camada-rag-design.md` |
| Qdrant, embedding, LLM, busca híbrida | `docs/adr/ADR-001` a `ADR-004` |
| Formato do dataset | `evaluation/dataset/SCHEMA.md` |
| Como rodar tudo | `README.md` |
