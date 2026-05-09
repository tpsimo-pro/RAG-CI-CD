# ADR-003 — Escolha do Modelo de Linguagem (LLM)

**Status:** Aceito  
**Data:** Maio de 2026  
**Autor:** Thiago P. Simões  
**Contexto:** RAG-Reviewer — TCC, Universidade do Estado do Amazonas (UEA)

---

## Contexto

O RAG-Reviewer usa um LLM para analisar o diff de um PR em conjunto com os trechos normativos recuperados do Qdrant e identificar violações em formato JSON estruturado.

Requisitos:
- **Resposta estruturada em JSON** confiável (sem alucinações de formato).
- **Capacidade de análise de código** (Python, especificamente).
- **Custo baixo ou gratuito** para viabilidade acadêmica.
- **Integração com GitHub Actions** sem problemas de rate limiting.
- **Janela de contexto suficiente** para diffs grandes (> 2000 tokens).

## Histórico de Decisão

O projeto passou por uma mudança de LLM durante o desenvolvimento:

1. **Google Gemini API** — descartado por atingir quota gratuita durante os testes de integração.
2. **Groq + Llama 3.3 70B** ✅ — adotado definitivamente pela alta velocidade de inferência e plano gratuito generoso.

## Decisão

**Groq API com modelo `llama-3.3-70b-versatile`** foi selecionado como LLM do projeto.

## Opções Consideradas

| Modelo | Custo | Velocidade | Qualidade JSON | Contexto |
|---|---|---|---|---|
| **Groq + Llama 3.3 70B** ✅ | Gratuito (rate limit generoso) | ~500 tokens/s | Excelente | 128K tokens |
| Google Gemini 1.5 Flash | Gratuito (quota baixa) | ~200 tokens/s | Boa | 1M tokens |
| OpenAI GPT-4o | ~$5/1M tokens | ~100 tokens/s | Excelente | 128K tokens |
| Anthropic Claude Sonnet 4.5 | ~$3/1M tokens | ~150 tokens/s | Excelente | 200K tokens |
| Ollama + CodeLlama (local) | Gratuito | ~20 tokens/s (CPU) | Boa | 16K tokens |

## Justificativa

1. **Custo zero:** Groq oferece acesso gratuito com rate limits suficientes para desenvolvimento e avaliação acadêmica (~14.400 requests/dia no plano free).
2. **Velocidade extrema:** A plataforma Groq usa hardware proprietário (LPU) que executa Llama 3.3 a ~500 tokens/segundo — a revisão de um PR completo leva < 5 segundos.
3. **Qualidade do Llama 3.3:** O modelo 70B demonstrou excelente capacidade de seguir instruções JSON estritas e analisar código Python com precisão.
4. **Janela de contexto:** 128K tokens — suficiente para diffs com dezenas de arquivos modificados.
5. **Compatibilidade OpenAI:** A API da Groq é compatível com o protocolo OpenAI (`chat.completions.create`), facilitando eventual migração.

## Consequências

- **Positivas:** Zero custo; inferência em segundos; JSON estruturado confiável; fácil substituição por outro modelo via `LLM_MODEL` no `.env`.
- **Negativas:** Dependência de serviço externo; rate limiting em casos de alto volume de PRs simultâneos.
- **Mitigação:** Retry com backoff exponencial implementado via exception handling no `LLMClient`; em produção corporativa, substituir pela OpenAI API ou Claude para SLA garantido.

## Configuração

```bash
# .env
GROQ_API_KEY=gsk_xxxxxxxxxxxx
LLM_MODEL=llama-3.3-70b-versatile
```

A chave é obtida gratuitamente em: https://console.groq.com
