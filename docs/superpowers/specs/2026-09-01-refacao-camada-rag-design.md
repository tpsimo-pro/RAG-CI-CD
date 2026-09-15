# Refação da Camada de RAG — Design

**Data:** 2026-09-01
**Projeto:** RAG-Reviewer (TCC)
**Status:** Aprovado, pendente de plano de implementação
**Decisões relacionadas:** D-001 a D-007 em [`docs/DECISIONS.md`](../../DECISIONS.md)

---

## 1. Contexto

O RAG-Reviewer recupera trechos de guias de estilo organizacionais e pede a um
LLM que aponte violações no diff de um Pull Request. A avaliação do TCC foi
reconstruída para medir isso de verdade (D-001, D-003, D-005), e a **primeira
execução real** expôs que a camada de recuperação nunca funcionou.

Esta spec descreve a reconstrução dessa camada.

### 1.1 Evidência medida

Todos os números abaixo foram obtidos por execução real contra o Qdrant e a
API da Groq, não estimados.

**Recuperação real para PR-001, que contém 3 violações de comparação booleana:**

```
0.525 | Incorreto                    ← rótulo de exemplo virou "seção"
0.513 | Correto                      ← idem
0.418 | 1.1 Responsabilidade Única   ← norma irrelevante
```

Nenhum chunk da Seção 5. Os três vieram de `coding_standards.md`, que não é o
guia da regra. Para PR-011 voltou um único chunk, a 0.366.

**Consequência observada na detecção:** o LLM passou a acusar
`def can_access_dashboard(user, account):` como violação, citando
`"coding_standards.md | Seção: Correto"`. Contexto ruim não é neutro — ele
fabrica falso positivo.

**Linha de base da detecção** (30 PRs, modelo `openai/gpt-oss-120b`, 1 repetição):

| TP | FP | FN | TN | N | Precisão | Recall | F1 |
|---|---|---|---|---|---|---|---|
| 12 | 10 | 48 | 230 | 300 | 0.5455 | 0.2000 | 0.2927 |

> Estes números foram obtidos com `openai/gpt-oss-120b`, usado apenas porque o
> modelo do ADR-003 havia sido descomissionado. **D-006 escolheu depois
> `qwen/qwen3.8-27b`.** Portanto esta linha serve como evidência de que a
> recuperação está quebrada — não como ponto de comparação para o resultado
> final, que usará outro modelo e 3 repetições (D-005).

### 1.2 Causa raiz: o modelo de embedding não entende o corpus

O `all-MiniLM-L6-v2` do ADR-002 é treinado em inglês. Todo o corpus normativo
está em português.

```
norma PT  <->  norma EN           0.597   ← traduções literais uma da outra
norma PT  <->  linha violadora    0.345
norma EN  <->  linha violadora    0.394   ← a MESMA norma, em inglês, pontua mais
norma PT  <->  linha irrelevante  0.005
```

A primeira linha é o diagnóstico: duas frases semanticamente idênticas deveriam
dar ~0.95. Deram 0.597.

Com o match semântico perfeito valendo apenas 0.345 e o `score_threshold` em
0.35, a norma correta **mal passa do corte**, enquanto chunks curtos e genéricos
a superam por acidente. Não é um problema de ordenação: a escala inteira está
comprimida junto do ruído.

### 1.3 O problema transversal: prosa contra código

Embeddings comparando prosa em português com código Python é a ferramenta
errada para o trabalho. `== True` e `!= None` são padrões **lexicais** — strings
literais. Nenhum modelo semântico deveria ser o responsável por casar uma
string exata.

Manter os exemplos de código dentro do chunk mitiga isso, porque passa a haver
código dos dois lados da comparação. Medido:

| Composição do chunk | Similaridade | Margem sobre distrator |
|---|---|---|
| só prosa | 0.345 | +0.206 |
| **prosa + exemplos** | **0.430** | **+0.292** |
| só código | 0.419 | +0.281 |

A margem de discriminação sobe **42%**. Nota: prosa+exemplos supera só-código —
a prosa não atrapalha, soma.

Mesmo assim a mitigação é parcial, e é por isso que o design inclui busca
híbrida.

---

## 2. Objetivo e critério de sucesso

Reconstruir indexação, chunking, construção de consulta e recuperação como
engenharia mensurada, com cada decisão justificada por número.

**Critério de sucesso: `recall@5 >= 0.95` nas 60 linhas positivas do dataset.**

O número não é arbitrário. A regra 8 do `system_prompt.txt` manda o LLM ignorar
normas ausentes do contexto — então uma falha de recuperação é um **falso
negativo irrecuperável**, que nenhuma qualidade de modelo compensa. Abaixo dessa
barra, a métrica de detecção continua medindo o encanamento em vez do modelo.

A avaliação de detecção (D-001, D-005) só volta a rodar depois que o critério
for atingido.

---

## 3. Princípios que governam o design

1. **A unidade de recuperação é a linha**, igual à unidade de avaliação de
   D-001. Hoje há um descasamento silencioso: avalia-se linha a linha, mas
   recupera-se uma vez por arquivo, sobre a concatenação das linhas
   adicionadas. Essa média semântica é a causa dos scores comprimidos.

2. **Regras estreitas, corpus completo** (D-007). O conjunto de regras
   avaliadas é fixo e pré-definido; o corpus indexado permanece com os três
   guias, servindo de palheiro. Estreitar o corpus faria `recall@k` dar ~1.0
   por falta de alternativa, e a ablação ficaria sem sinal.

3. **Os resultados nunca são fixos** (D-007). Quais linhas violam é sempre
   decisão do retrieval + LLM.

4. **Nenhuma degradação silenciosa.** Todo fallback altera o que está sendo
   medido sem avisar. É a lição do mock circular que produzia F1 = 1.0.

---

## 4. Arquitetura

### 4.1 Componentes

**Offline — indexação**

| Componente | Situação |
|---|---|
| `indexer/document_loader.py` | **Corrigido** — reconhecimento de blocos cercados (ver §4.1.1) |
| `indexer/chunker.py` | **Reescrito** — preserva a unidade normativa |
| `indexer/index_pipeline.py` | Ajustado — grava vetor denso **e** esparso |

#### 4.1.1 A origem real dos chunks-lixo

Investigação durante o planejamento localizou o defeito **no
`document_loader`, não no chunker**. Em `_load_markdown`:

```python
pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
```

O regex não conhece blocos de código cercados. Dentro de uma cerca
```` ```python ````, comentários como `# Correto` e
`# INCORRETO — VIOLA NORMA DE SEGURANÇA CRÍTICA` são **comentários Python**,
mas são lidos como cabeçalhos Markdown. O `coding_standards.md` produz 39
"seções", das quais 9 são falsas.

**O dano vai além de gerar lixo.** Um cabeçalho falso *encerra a seção
anterior*, então os exemplos de código são arrancados da norma a que
pertencem: `2.3 Nomenclatura de Funções Booleanas` perde seus próprios
exemplos para as seções fantasma `Correto` e `Incorreto`.

Ou seja: a propriedade "norma + exemplos juntos", que §1.3 mediu valer +42% de
margem, é destruída **antes de o chunker rodar**. Corrigir o loader é
pré-requisito de L1 — sem isso, o chunker estrutural não tem o que preservar.

**Online — recuperação**

| Componente | Situação |
|---|---|
| `rag_reviewer/embedder.py` | Troca de modelo; interface preservada |
| `rag_reviewer/sparse_encoder.py` | **Novo** — vetores esparsos BM25 |
| `rag_reviewer/vector_store.py` | Ajustado — busca híbrida com fusão RRF |
| `rag_reviewer/retriever.py` | **Reescrito** — consulta por linha, união por arquivo |

### 4.2 O chunker estrutural

Produz uma unidade normativa por seção-folha: **título + prosa + todos os blocos
de código daquela seção, juntos**.

Regra dura: **um bloco de código cercado nunca vira chunk próprio** — ele
sempre pertence ao título que o contém. Isso extermina os chunks `"Correto"` e
`"Incorreto"` na origem, em vez de filtrá-los depois.

### 4.3 Fluxo de dados

```
linha adicionada  ─┬─→ embedding denso  ─┐
                   └─→ vetor esparso     ├─→ Qdrant (fusão RRF) ─→ top-k chunks
                                         ┘
       ↓ repetido para cada linha adicionada do arquivo
  união + deduplicação + corte em N chunks
                    ↓
          UMA chamada ao LLM por arquivo
```

**Granularidade de recuperação ≠ granularidade de chamada ao LLM.** Recupera-se
por linha; as chamadas ao LLM continuam sendo uma por arquivo, sobre a união
deduplicada dos chunks. O custo de API não muda. Só os embeddings locais
crescem — 300 em vez de 30 no dataset inteiro — e são baratos e em lote.

**Os dois cortes são parâmetros calibrados, não constantes escolhidas a dedo:**
`k` (chunks recuperados por linha) e `N` (teto de chunks no prompt após a
união). Ambos são fixados contra o gabarito de §6, e o valor adotado com sua
justificativa entra no relatório. `N` existe porque a união de k chunks por
linha, num arquivo de ~10 linhas, pode ultrapassar o que cabe utilmente num
prompt — e porque contexto excedente comprovadamente induz alucinação (§1.1).

### 4.4 O `score_threshold` absoluto é removido

Com fusão RRF o score deixa de ser cosseno e passa a ser posto: 0.35 não
significa mais nada. No lugar entra um `top-k` calibrado contra o gabarito.

---

## 5. As três camadas

| Camada | O que faz | Por que |
|---|---|---|
| **L1 — Chunker estrutural** | Mantém norma + exemplos como unidade | Mata os chunks-lixo; +42% de margem medidos |
| **L2 — Modelo multilíngue** | Substitui o modelo inglês | Ataca a causa raiz (PT↔EN = 0.597) |
| **L3 — Busca híbrida** | Denso + esparso, fundidos por RRF | `== True` casa por token exato, sem depender de o modelo entender PT nem Python |

**Orçamento do modelo (L2):** ~500MB, 384 dimensões — mantém a dimensão atual,
então nada mais no código precisa mudar. Candidatos:
`paraphrase-multilingual-MiniLM-L12-v2` e `intfloat/multilingual-e5-small`.

> Nota de implementação: os modelos da família `e5` exigem os prefixos
> `"query: "` e `"passage: "` nos textos. Omiti-los degrada a qualidade em
> silêncio — se o candidato escolhido for e5, os prefixos são obrigatórios e
> devem ser cobertos por teste.

---

## 6. Gabarito de retrieval e métricas

### 6.1 O gabarito

Para cada uma das **60 linhas positivas** do dataset `pilot_secao5.json`, qual
norma precisa ter chegado ao LLM.

**O gabarito NÃO pode ser um mapa de `chunk_id`.** Os `chunk_id` mudam quando o
chunker muda, e a ablação de §7 compara justamente L0 (chunker cego) contra L1+
(chunker estrutural). Um gabarito ancorado em ids tornaria as configurações
incomparáveis e invalidaria o experimento inteiro.

O gabarito é ancorado em **chaves normativas estáveis**, independentes de
chunking:

```
linha  →  chave normativa exigida
"if user.is_admin == True:"   →  pep8:secao-5:comparacao-booleana
"if result != None:"          →  pep8:secao-5:comparacao-nulo
```

Cada configuração de chunking declara, por chunk, quais chaves normativas ele
carrega:

```
chunk_id  →  {chaves normativas contidas}
```

`recall@k` passa a perguntar: **algum dos k chunks recuperados carrega a chave
normativa exigida por esta linha?** A pergunta é a mesma em L0, L1, L2 e L3, e
por isso os números são comparáveis entre si.

O mapeamento `chunk → chaves` é construído uma vez por configuração e é
auditável — precisa entrar no relatório junto com as métricas, porque um
mapeamento frouxo inflaria o recall de todas as configurações ao mesmo tempo.

**Só as positivas entram.** Para uma linha negativa como `if x is not None:`,
qual seria o chunk "correto"? A Seção 5 é justamente a norma que declara aquilo
certo — é relevante e ao mesmo tempo não deveria gerar violação. O gabarito
ficaria ambíguo, e métrica sobre ambiguidade não serve. As negativas seguem
cobertas onde já estavam: nos FP e TN da matriz de detecção.

### 6.2 Métricas

| Métrica | O que responde |
|---|---|
| **recall@k** (k = 1, 3, 5) | A norma certa chegou ao LLM? |
| **Precisão de contexto@5** | Que fração do que foi entregue prestava? |

`recall@5` é a principal, porque 5 é o que o LLM efetivamente vê. A segunda não
é decorativa: chunks-lixo comprovadamente induzem alucinação (ver §1.1).

### 6.3 Propriedade valiosa

**A avaliação de retrieval não chama o LLM.** É offline, determinística e de
custo zero de API. Pode rodar quantas vezes for preciso, inclusive em CI, sem
consumir cota nem esbarrar no não-determinismo de D-005. Toda a calibração
acontece aqui; o LLM só entra depois, com a configuração já escolhida.

---

## 7. Protocolo de ablação

Cumulativo, nesta ordem:

| | Configuração |
|---|---|
| **L0** | Linha de base: chunker cego + MiniLM inglês + denso puro + threshold 0.35 |
| **L1** | + chunker estrutural |
| **L2** | + modelo multilíngue |
| **L3** | + busca híbrida |

**A ordem não é arbitrária.** Cada camada remove um defeito que mascararia o
efeito da seguinte. Os chunks-lixo precisam morrer primeiro — senão um modelo
melhor apenas ranqueia lixo com mais confiança. O idioma precisa ser corrigido
antes da híbrida — senão a metade densa continua quebrada e a fusão RRF estaria
medindo quase só a metade esparsa.

**Teste de remoção final:** sobre a configuração completa, retirar L3 e remedir.
Protege contra atribuir à busca híbrida um ganho que L1+L2 já haviam entregue —
o erro clássico da ablação puramente cumulativa.

Cada passo reporta `recall@1/3/5` e precisão de contexto@5 sobre o mesmo
gabarito. A tabela resultante é material direto do TCC.

---

## 8. Tratamento de erros

Princípio único: **nenhuma degradação silenciosa.**

### 8.1 Divergência de modelo (o caso mais perigoso)

Os modelos multilíngues candidatos também têm **384 dimensões** — a mesma de
hoje. Se a collection não for recriada após a troca, o Qdrant **aceita a busca
sem reclamar**: vetores de consulta do modelo novo contra vetores de chunk do
modelo antigo. O resultado seria lixo silencioso, indistinguível de retrieval
ruim.

**Defesa obrigatória:** gravar o nome do modelo de embedding e a versão do
chunker junto da collection, e verificar na recuperação. Divergência derruba a
execução com instrução explícita de rodar `make index-recreate`.

### 8.2 Demais falhas — todas ruidosas

- Download do modelo falhou → erro, sem fallback para outro modelo.
- Qdrant inacessível → erro.
- Encoder esparso indisponível → **erro**. Cair para "só denso" pareceria
  funcionar, mas mudaria em silêncio a configuração sob medição, invalidando a
  ablação.

### 8.3 O que não é erro

Nenhum chunk recuperado para uma linha é resultado legítimo: a linha não recebe
contexto. Se o arquivo inteiro ficar sem chunks, não há chamada ao LLM e todas
as suas linhas contam como não sinalizadas. É o comportamento atual, está
correto, e deve ser preservado.

---

## 9. Testes

O chunker é a reescrita de maior risco e concentra a cobertura:

- um bloco de código cercado **nunca** vira chunk próprio;
- título + prosa + todos os seus blocos formam exatamente um chunk;
- **teste de regressão nomeado:** nenhum chunk pode ter seção igual a um rótulo
  de exemplo (`Correto`, `Incorreto`, `CORRETO`). É o bug que originou tudo —
  merece um teste que falhe com nome próprio se voltar.

Demais alvos:

- `retriever`: construção por linha, união e deduplicação por arquivo, corte em N;
- `vector_store`: a trava de divergência de modelo dispara;
- métricas: `recall@k` sobre fixtures sintéticas;
- se o modelo escolhido for da família e5: os prefixos `query:`/`passage:` são
  aplicados.

Tudo offline e determinístico — a suíte roda rápido e sem API.

**Pendência herdada:** `evaluation/` continua sem cobertura nenhuma, e é o
módulo que produz os números do TCC. Entra no mesmo esforço.

---

## 10. Impacto em produção

### 10.1 GitHub Actions

O modelo salta de ~90MB para ~470MB, baixado a cada execução. Sem cache do
diretório de modelos, isso entra em rota de colisão com o `timeout-minutes: 10`
do workflow. O cache de `pip` já existe; falta um para o cache do HuggingFace
(`HF_HOME` / `~/.cache/huggingface`).

`requirements.txt` ganha a dependência de codificação esparsa.

### 10.2 ADRs

| ADR | Ação |
|---|---|
| ADR-002 — modelo de embedding | **Reescrito** (multilíngue) |
| ADR-003 — escolha do LLM | **Reescrito** (D-006: o modelo antigo não existe mais) |
| ADR-004 — recuperação híbrida | **Novo** |

### 10.3 Acoplamento a vigiar

O chunker estrutural muda os nomes das seções, e o `_SECTION_5_PATTERN` de
`evaluation/metrics.py` casa contra esses nomes. Os dois precisam ser
corrigidos em conjunto, ou a métrica de citação continua mentindo — por um
motivo novo.

---

## 11. Fora de escopo

Intocados: `llm_client.py`, os prompts, `github_publisher.py` e
`diff_parser.py`. A refação está confinada ao caminho de recuperação.

As métricas de detecção de D-001, D-003 e D-005 permanecem como foram
construídas — apenas o regex de §10.3 é corrigido.

Adiado para [`TODO-FUTURO.md`](../../TODO-FUTURO.md): ampliação para N regras
(F-002), PRs reais (F-003), aprofundamento da variância do LLM (F-001).

**Pergunta ainda aberta, não resolvida por esta spec:** adicionar linhas de
contexto pré-existentes ao dataset, para permitir testar a regra 4 do system
prompt ("não comentar linhas não modificadas"). Hoje os 30 patches são todos de
arquivo novo, e essa regra não tem como ser exercitada. Decisão pendente do
autor.

---

## 12. Riscos

| # | Risco | Mitigação |
|---|---|---|
| R1 | `recall@5 >= 0.95` não é atingido nem com as três camadas | A barra é revisável **com justificativa escrita**; o que não se admite é baixá-la escondendo distratores (D-007) |
| R2 | Cache do modelo no Actions não resolve e o workflow estoura 10 min | Elevar o timeout; em último caso, pré-baixar o modelo numa imagem |
| R3 | Ablação cumulativa atribui ganho à camada errada | Teste de remoção de L3 sobre a configuração completa (§7) |
| R4 | Corpus completo torna o retrieval difícil demais e a ablação inconclusiva | É o risco aceito conscientemente em D-007; um número difícil e verdadeiro vale mais que um fácil e vazio |
