# ADR-001 — Escolha do Banco de Vetores

**Status:** Aceito  
**Data:** Maio de 2026  
**Autor:** Thiago P. Simões  
**Contexto:** RAG-Reviewer — TCC, Universidade do Estado do Amazonas (UEA)

---

## Contexto

O RAG-Reviewer precisa armazenar e consultar embeddings de trechos de guias de estilo (chunks de ~512 tokens) para recuperação semântica em tempo real durante a revisão de Pull Requests. Os requisitos são:

- **Busca por similaridade semântica** com baixa latência (< 500ms por consulta).
- **Auto-hospedável** para garantir privacidade dos dados normativos da organização.
- **SDK Python maduro** para integração direta com o pipeline existente.
- **Filtros de payload** para segmentar chunks por documento fonte.
- **Plano gratuito** adequado para desenvolvimento e pesquisa acadêmica.

## Decisão

**Qdrant** foi selecionado como banco de vetores do projeto.

## Opções Consideradas

| Opção | Prós | Contras |
|---|---|---|
| **Qdrant** ✅ | Gratuito, self-hosted, SDK Python excelente, filtros de payload, HNSW nativo, Qdrant Cloud com 1 GB free | Requer infraestrutura própria ou Qdrant Cloud |
| **Pinecone** | Totalmente gerenciado, sem ops | Pago em produção; dados saem da organização |
| **ChromaDB** | Simples, embedded, sem servidor | Performance e estabilidade insuficientes para produção |
| **Weaviate** | Recursos avançados (GraphQL, módulos de ML) | Maior complexidade de setup; over-engineering para o escopo |
| **pgvector** | Sem infra adicional (usa o PostgreSQL existente) | Performance inferior para busca vetorial pura; extensão experimental |

## Justificativa

O Qdrant oferece a melhor relação custo-benefício para o cenário do TCC:

1. **Qdrant Cloud (Free Tier):** 1 cluster gratuito com 1 GB de armazenamento — suficiente para os guias de estilo do projeto (~5K chunks).
2. **API REST + SDK Python:** Interface nativa com Python sem overhead de adaptadores.
3. **HNSW Index:** Algoritmo de grafos hierárquicos que oferece busca aproximada de vizinhos mais próximos com latência de milissegundos.
4. **Payload Filtering:** Permite filtrar chunks por `source` (documento) sem re-rankeamento manual.
5. **Portabilidade:** O mesmo código funciona com Qdrant local (Docker) em desenvolvimento e Qdrant Cloud em produção.

## Consequências

- **Positivas:** Latência de busca < 50ms para collections de até 100K vetores; zero custo em desenvolvimento; sem lock-in de vendor.
- **Negativas:** Requer manutenção de infra (Docker ou conta Qdrant Cloud); dependência de serviço externo em produção.
- **Mitigação:** `docker-compose` documentado no Makefile (`make docker-qdrant`) para ambiente local de desenvolvimento.
