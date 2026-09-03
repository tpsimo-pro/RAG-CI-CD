# ADR-003 — Escolha do Modelo de Linguagem (LLM)

**Status:** Aceito (reescrito — a linhagem anterior foi descomissionada)
**Data original:** Maio de 2026
**Reescrita:** 2026-09-01 — ver D-006 (`docs/DECISIONS.md`)
**Autor:** Thiago P. Simões
**Contexto:** RAG-Reviewer — TCC, Universidade do Estado do Amazonas (UEA)

---

## Por que este ADR foi reescrito, não emendado

`llama-3.3-70b-versatile` (a decisão original) **não existe mais** no
catálogo da Groq — confirmado via `models.list()`. Não há **nenhum** modelo
Llama de propósito geral disponível na plataforma; os únicos `meta-llama/*`
remanescentes são classificadores `prompt-guard` com 512 tokens de
contexto, inúteis para este caso de uso. Toda a justificativa original
(velocidade da LPU especificamente com Llama, qualidade do 70B) deixou de
se aplicar — não é um ajuste de parâmetro, é uma decisão nova.

## Requisitos (inalterados desde a decisão original)

- **Resposta estruturada em JSON** confiável (sem alucinações de formato).
- **Capacidade de análise de código** (Python, especificamente).
- **Custo baixo ou gratuito** para viabilidade acadêmica.
- **Integração com GitHub Actions** sem problemas de rate limiting.
- **Janela de contexto suficiente** para diffs grandes (> 2.000 tokens).

## Decisão

**`qwen/qwen3.8-27b`** (Alibaba Cloud, via Groq) — contexto 131.042 tokens,
saída máxima 16.384 tokens.

## Justificativa

1. **Diversificação da linhagem.** Evita que o resultado do TCC dependa de
   uma única família de modelos (a anterior já foi descontinuada uma vez).
2. **Atende aos cinco critérios originais** deste ADR: custo zero no plano
   Groq, mesma API compatível com OpenAI (sem mudança de integração no
   `LLMClient` nem no workflow do Actions), contexto muito acima do mínimo
   de 2.000 tokens exigido.
3. **Risco real identificado e eliminado por teste**, não assumido: a
   aderência ao schema JSON estrito nunca havia sido exercitada com este
   modelo neste código. Smoke test em 2 PRs do dataset (PR-001, PR-011) —
   ambos parsearam sem erro de formato.

## Alternativas consideradas e rejeitadas

| Modelo | Motivo da rejeição |
|---|---|
| `openai/gpt-oss-120b` | Maior modelo disponível e com execução prévia comprovada no repositório — preterido para não concentrar o trabalho numa única linhagem já testada. |
| `openai/gpt-oss-20b` | Menor capacidade de análise é exatamente a variável sob medição neste TCC; um F1 baixo ficaria ambíguo entre "o RAG não ajuda" e "o modelo é pequeno demais". |
| `groq/compound`, `groq/compound-mini` | **Rejeitados com prejuízo — não usar em nenhuma circunstância, mesmo que o desempenho pareça superior.** São sistemas agênticos com busca web e execução de código embutidas. Num estudo de RAG isso destrói a validade interna: o modelo poderia consultar a PEP-8 na internet e "acertar" sem usar o contexto recuperado do Qdrant, sem que se possa distinguir os dois casos. |
| Comparativo com dois modelos | Enriqueceria a defesa, mas dobra o custo de avaliação (2 × 3 repetições × 30 PRs = 180 execuções) e contraria a exigência de "sem dispersão de escopo" (`todo-asap.txt`). Adiado para `docs/TODO-FUTURO.md` — comparar dois modelos antes de existir um número válido é otimizar na ordem errada. |

## Consequências

- **Positivas:** Zero custo; mesma API compatível com OpenAI usada pelo
  `LLMClient`, nenhuma mudança de integração necessária; contexto amplo
  (131K tokens) folgado para diffs de PR reais.
- **Negativas:** Dependência de um provedor cuja disponibilidade de modelo
  já mudou uma vez neste projeto — a mesma classe de risco que causou esta
  reescrita pode se repetir.
- **Mitigação:** `LLM_MODEL` permanece configurável via `.env`, sem
  acoplamento de código a um modelo específico; `rag_reviewer/config.py`,
  `.env.example` e `.env` locais atualizados para o novo default junto com
  este ADR, fechando a pendência que D-006 deixou registrada.

## Configuração

```bash
# .env
GROQ_API_KEY=gsk_xxxxxxxxxxxx
LLM_MODEL=qwen/qwen3.8-27b
```

A chave é obtida gratuitamente em: https://console.groq.com
