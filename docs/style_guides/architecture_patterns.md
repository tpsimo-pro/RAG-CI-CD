# Padrões Arquiteturais — Organização

> **Versão:** 1.0  
> **Aplicável a:** Projetos de backend e microsserviços

---

## 1. Arquitetura em Camadas

### 1.1 Separação de Camadas Obrigatória

Todo projeto backend deve respeitar a separação em camadas:

| Camada | Responsabilidade | Exemplo |
|---|---|---|
| **API (Controllers/Routers)** | Recebe requisições, valida entrada, delega para services | `routers/user_router.py` |
| **Service (Negócio)** | Contém a lógica de negócio pura | `services/user_service.py` |
| **Repository** | Acesso ao banco de dados | `repositories/user_repo.py` |
| **Models** | Entidades de domínio | `models/user.py` |

**Proibido:** A camada de API nunca deve acessar diretamente o banco de dados. Toda query deve passar pela camada Repository.

### 1.2 Dependências Entre Camadas

As dependências fluem sempre em uma direção:

```
API → Service → Repository → Database
```

Inversão de dependência deve ser feita via interfaces (protocolos Python).

---

## 2. APIs REST

### 2.1 Versionamento Obrigatório

Toda API pública deve ser versionada na URL:

```
/api/v1/users
/api/v2/users
```

**Proibido** alterar a interface de uma versão já publicada sem criar uma nova versão.

### 2.2 Códigos de Status HTTP

| Situação | Código |
|---|---|
| Recurso criado | 201 Created |
| Operação sem retorno | 204 No Content |
| Recurso não encontrado | 404 Not Found |
| Validação falhou | 422 Unprocessable Entity |
| Erro interno | 500 Internal Server Error |

**Proibido** retornar 200 para operações que falharam.

---

## 3. Banco de Dados

### 3.1 Migrações

- Toda alteração de schema deve ser feita via migration (Alembic para SQLAlchemy).
- **Proibido** alterar schema diretamente em produção via SQL manual.
- Migrações devem ser reversíveis (`upgrade` e `downgrade`).

### 3.2 Queries

- **Proibido** queries N+1. Use eager loading (`joinedload`) ou batch queries.
- Toda query que pode retornar muitos registros deve ter paginação.
- Índices devem ser criados para todos os campos usados em filtros frequentes.
