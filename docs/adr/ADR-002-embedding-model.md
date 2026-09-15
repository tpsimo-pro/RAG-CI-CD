# ADR-002 — Escolha do Modelo de Embedding

**Status:** Aceito (revisado)
**Data original:** Maio de 2026
**Revisão:** 2026-09-03 — Task 8 da refação da camada de RAG
**Autor:** Thiago P. Simões
**Contexto:** RAG-Reviewer — TCC, Universidade do Estado do Amazonas (UEA)

---

## Por que esta revisão existe

A versão original deste ADR justificava `all-MiniLM-L6-v2` (treinado
predominantemente em inglês) citando "diferença de qualidade inferior a 5%
nos benchmarks internos" para português — **uma afirmação nunca medida**. A
medição real (Task 8, Step 1) mostrou o oposto: entre duas traduções
literais do mesmo enunciado normativo,

```
PT: "Comparações booleanas: Não compare valores booleanos com == True ou == False."
EN: "Boolean comparisons: Do not compare boolean values with == True or == False."
```

`all-MiniLM-L6-v2` dava cosine similarity **PT↔EN = 0.597**, quando o
esperado para um par de traduções idênticas é ~0.95. O corpus normativo do
RAG-Reviewer é integralmente em português; o modelo escolhido originalmente
não conseguia colocar uma norma e sua tradução literal perto uma da outra no
espaço vetorial. Essa era a causa raiz medida por trás de `recall@5` baixo
na linha de base (spec §1.2) — não um problema de chunking ou de
granularidade de consulta, ambos corrigidos antes e sem resolver o gargalo.

## Decisão

**`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`** substitui
`all-MiniLM-L6-v2` como modelo de embedding.

- **Dimensões:** 384 (mesma do modelo anterior — ver "Risco silencioso" abaixo)
- **Execução:** Local, sem chamada de API externa
- **Licença:** Apache 2.0

## Escolha por medição, não por intuição

Comparados dois candidatos multilíngues nos três eixos que importam para
este corpus: similaridade PT↔EN pura, similaridade norma↔violação, e a
**margem** entre essa similaridade e a de um distrator não relacionado — o
sinal que a ablação de retrieval realmente precisa (uma similaridade alta
que também é alta para textos irrelevantes não discrimina nada).

| Modelo | PT↔EN (alvo ~0.95) | norma↔violação | margem sobre distrator |
|---|---|---|---|
| **`paraphrase-multilingual-MiniLM-L12-v2`** ✅ | 0.912 | 0.364 | **0.314** |
| `intfloat/multilingual-e5-small` | **0.954** | 0.876 | 0.045 |

O e5-small vence na similaridade PT↔EN pura, mas colapsa a margem entre
norma/violação e distrator/violação quase ao nível do distrator — ele
aproxima *tudo* do texto de consulta, inclusive o que é irrelevante, o que
o tornaria inútil para discriminar chunks relevantes num índice real. O
`paraphrase-multilingual-MiniLM-L12-v2` venceu por manter mais de 6× a
margem de discriminação, mesmo com PT↔EN pontual mais baixo. Vencedor claro;
sem necessidade dos prefixos `query:`/`passage:` que a família e5 exigiria
(economiza uma classe inteira de bug silencioso: omitir o prefixo em uma
das duas pontas degrada a qualidade sem erro visível).

## Risco silencioso: mesma dimensionalidade do modelo anterior

Ambos os candidatos multilíngues produzem vetores de 384 dimensões — igual
ao `all-MiniLM-L6-v2` anterior. Sem proteção, o Qdrant aceitaria buscar
vetores de consulta do modelo novo contra chunks indexados pelo modelo
antigo **sem erro**, produzindo resultados silenciosamente incorretos
indistinguíveis de retrieval ruim. Mitigado por
`VectorStore.assert_model_matches()` (Task 6): o nome do modelo é gravado no
payload de cada ponto na indexação e conferido contra o modelo configurado
antes de qualquer busca real — divergência levanta `RuntimeError` com
instrução de reindexação, nunca falha em silêncio.

## Resultado medido

`recall@5` na ablação de retrieval (60 linhas positivas do piloto de Seção
5, ver `docs/agent-reports/2026-09-01-ablacao-retrieval.md`):

| Config | recall@5 |
|---|---|
| L2 (consulta por linha, ainda `all-MiniLM-L6-v2`) | 0.0667 |
| **L3 (+ modelo multilíngue)** | **0.7500** |

Maior ganho isolado de toda a ablação (+0.6833) — confirma que o modelo em
inglês era o gargalo dominante do sistema.

## Achado do teste de remoção (não decide a produção sozinho)

Com a busca híbrida densa+esparsa (ADR-004) já em vigor, o teste de remoção
leave-one-out (Task 10) mostrou que, **especificamente no gabarito do
piloto** (violações booleanas e de nulos, ambas padrões lexicais exatos),
`recall@5` fica **idêntico** (1.0000) com ou sem o modelo multilíngue — o
componente esparso BM25 sozinho já encontra a norma certa por casamento de
token. A diferença aparece só em `recall@1`, onde o multilíngue ainda
ajuda a rankear melhor. Isso **não** justifica reverter esta decisão: o
corpus completo tem normas não-lexicais (nomenclatura, tamanho de função,
docstrings) onde a paráfrase semântica multilíngue provavelmente segue
importando. Registrado aqui como dado para decisão futura do autor, não
como mudança de rumo.

## Consequências

- **Positivas:** Corpus em português finalmente bem representado no espaço
  vetorial; guarda de divergência de modelo (Task 6) protege contra o risco
  de dimensionalidade idêntica; decisão auditável por número, não por
  intuição.
- **Negativas:** Modelo maior (~470MB vs ~90MB do MiniLM inglês) — impacto
  direto no tempo de execução do GitHub Actions a cada indexação (mitigado
  por cache do HuggingFace Hub no workflow, ver ADR-004 e Task 12 Step 4).
- **Caminho de upgrade:** Interface `Embedder` permanece agnóstica ao
  modelo — trocar exige apenas `EMBEDDING_MODEL` no `.env` seguido de
  `make index-recreate` (a guarda da Task 6 impede rodar com índice
  desatualizado).
