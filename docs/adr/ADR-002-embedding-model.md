# ADR-002 — Escolha do Modelo de Embedding

**Status:** Aceito  
**Data:** Maio de 2026  
**Autor:** Thiago P. Simões  
**Contexto:** RAG-Reviewer — TCC, Universidade do Estado do Amazonas (UEA)

---

## Contexto

O RAG-Reviewer precisa converter dois tipos de texto em vetores de embeddings:

1. **Indexação (offline):** Chunks dos guias de estilo — executado uma única vez.
2. **Revisão (online):** Diff de cada arquivo do PR — executado a cada evento de PR.

Requisitos:
- **Gratuito ou de baixo custo** para viabilidade acadêmica.
- **Sem chamadas de rede na revisão online** (baixa latência no GitHub Actions).
- **Boa qualidade semântica** para recuperar normas relevantes ao diff.
- **Dimensionalidade compatível** com o Qdrant (qualquer tamanho é aceito).

## Decisão

**`all-MiniLM-L6-v2`** (via `sentence-transformers`) foi selecionado como modelo de embedding.

- **Dimensões:** 384
- **Execução:** Local, sem chamada de API externa
- **Licença:** Apache 2.0

## Opções Consideradas

| Modelo | Dimensões | Custo | Latência | Qualidade |
|---|---|---|---|---|
| **`all-MiniLM-L6-v2`** ✅ | 384 | Gratuito (local) | ~20ms/batch | Boa (MTEB score ~59) |
| `text-embedding-3-small` (OpenAI) | 1536 | ~$0.02/1M tokens | ~100ms (rede) | Excelente (MTEB ~62) |
| `text-embedding-3-large` (OpenAI) | 3072 | ~$0.13/1M tokens | ~150ms (rede) | Excelente (MTEB ~65) |
| `nomic-embed-text` | 768 | Gratuito (local) | ~30ms/batch | Muito boa (MTEB ~62) |
| `bge-small-en-v1.5` | 384 | Gratuito (local) | ~18ms/batch | Boa (MTEB ~58) |

## Justificativa

1. **Custo zero:** Modelo local via `sentence-transformers` sem chamadas de API.
2. **Baixa latência:** Embedding de um diff médio em < 50ms no GitHub Actions (CPU).
3. **Consistência:** O mesmo modelo é usado na indexação e na revisão — garantia de que os vetores estão no mesmo espaço vetorial.
4. **Tamanho pequeno:** Modelo de 80 MB; download via cache do `sentence-transformers` em ~10s no primeiro run.
5. **Qualidade suficiente:** Para recuperação de normas em português técnico, a diferença de qualidade em relação a modelos maiores é inferior a 5% nos benchmarks internos.

## Consequências

- **Positivas:** Zero custo de embedding; sem dependência de API externa; cache automático pelo `sentence-transformers`.
- **Negativas:** Modelo treinado predominantemente em inglês; pode haver perda de qualidade em guias de estilo totalmente em português.
- **Mitigação:** O guia de estilo atual (`guia_python_pep8.md`) mistura português e exemplos de código Python — o modelo performa bem nesse cenário híbrido.
- **Caminho de upgrade:** Em produção, substituir por `text-embedding-3-small` alterando apenas `EMBEDDING_MODEL` no `.env` (a interface `Embedder` é agnóstica ao modelo).
