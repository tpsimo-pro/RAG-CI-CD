# Guia de Estilo de Código — Organização

> **Versão:** 1.0  
> **Status:** Vigente  
> **Aplicável a:** Todos os repositórios da organização

---

## 1. Princípios Gerais

Todo código produzido na organização deve seguir os princípios SOLID e as boas práticas de Clean Code descritas neste guia. O objetivo é garantir legibilidade, manutenibilidade e rastreabilidade do código ao longo do tempo.

### 1.1 Responsabilidade Única

Cada módulo, classe ou função deve ter **uma única responsabilidade**. Se uma função realiza mais de uma tarefa distinta, ela deve ser refatorada em funções menores.

**Exemplo incorreto:**
```python
def process_and_save_user(user_data):
    # processa validação E salva no banco — responsabilidades misturadas
    ...
```

**Exemplo correto:**
```python
def validate_user(user_data): ...
def save_user(user): ...
```

### 1.2 Legibilidade

O código deve ser autoexplicativo. Prefira nomes descritivos a comentários que expliquem o que o código faz.

---

## 2. Nomenclatura

### 2.1 Python — Convenções Obrigatórias

| Elemento | Convenção | Exemplo |
|---|---|---|
| Variáveis e funções | `snake_case` | `get_user_by_id` |
| Classes | `PascalCase` | `UserRepository` |
| Constantes | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT` |
| Módulos | `snake_case` | `user_service.py` |
| Parâmetros privados | prefixo `_` | `_internal_cache` |

### 2.2 Proibições de Nomenclatura

- **Proibido** usar nomes de uma única letra, exceto em loops curtos (`i`, `j`) e lambdas simples.
- **Proibido** abreviações ambíguas: use `maximum` em vez de `mx`, `count` em vez de `cnt`.
- **Proibido** nomes genéricos sem contexto: `data`, `info`, `temp`, `obj`, `result` sem qualificador.

### 2.3 Nomenclatura de Funções Booleanas

Funções que retornam booleano devem começar com `is_`, `has_`, `can_` ou `should_`.

```python
# Correto
def is_active(user) -> bool: ...
def has_permission(user, resource) -> bool: ...

# Incorreto
def active(user): ...
def check_permission(user, resource): ...
```

---

## 3. Estrutura de Funções

### 3.1 Tamanho Máximo

Funções não devem ultrapassar **30 linhas de código efetivo** (excluindo docstrings e comentários). Funções maiores devem ser decompostas.

### 3.2 Parâmetros

- Máximo de **4 parâmetros** por função. Acima disso, agrupe em dataclass ou dict.
- Evite parâmetros booleanos que alteram o comportamento da função (`flag=True`). Prefira funções separadas.

### 3.3 Valor de Retorno

- Toda função pública deve ter **type hints** de retorno explícitos.
- Funções não devem retornar `None` e um valor real ao mesmo tempo. Use `Optional[T]` de forma consistente.

---

## 4. Tratamento de Exceções

### 4.1 Regras Obrigatórias

- **Proibido** capturar `Exception` genérica sem re-raise ou logging.
- Toda exceção capturada deve ser logada com `logger.exception()` ou re-lançada com contexto adicional.
- Use exceções customizadas para erros de negócio: herde de `Exception` com nome descritivo.

```python
# Incorreto — captura genérica silenciosa
try:
    process()
except Exception:
    pass

# Correto — captura específica com logging
try:
    process()
except ValueError as exc:
    logger.exception("Falha ao processar: %s", exc)
    raise ProcessingError("Dados inválidos") from exc
```

### 4.2 Hierarquia de Exceções

Crie uma hierarquia de exceções por domínio:

```
BaseAppError
├── ValidationError
├── NotFoundError
└── ExternalServiceError
    ├── DatabaseError
    └── APIError
```

---

## 5. Documentação

### 5.1 Docstrings Obrigatórias

Todo módulo, classe e função pública **deve** ter docstring no formato Google Style:

```python
def calculate_discount(price: float, rate: float) -> float:
    """Calcula o desconto aplicado a um preço.

    Args:
        price: Preço original em reais (deve ser positivo).
        rate:  Taxa de desconto como decimal (0.0 a 1.0).

    Returns:
        Valor do desconto calculado.

    Raises:
        ValueError: Se price for negativo ou rate estiver fora do intervalo [0, 1].
    """
    ...
```

### 5.2 Comentários Inline

- Comentários devem explicar **por que**, não **o que**.
- Evite comentários óbvios: `# incrementa i` em `i += 1`.
- Comentários `# TODO:` devem incluir o identificador do ticket: `# TODO: PROJ-123 — implementar cache`.

---

## 6. Importações

### 6.1 Ordem de Importações (isort/ruff)

1. Biblioteca padrão do Python
2. Bibliotecas de terceiros
3. Módulos internos do projeto

Cada grupo separado por linha em branco.

```python
# 1. Stdlib
import os
from pathlib import Path

# 2. Terceiros
import requests
from pydantic import BaseModel

# 3. Internos
from myapp.services import UserService
```

### 6.2 Proibições

- **Proibido** `import *` em qualquer circunstância.
- **Proibido** importações circulares. Resolva com injeção de dependência ou reestruturação de módulos.

---

## 7. Configuração e Secrets

### 7.1 Proibições Absolutas

- **CRÍTICO:** Nunca commitar chaves de API, senhas ou tokens no código-fonte.
- **CRÍTICO:** Nunca usar strings hardcoded para URLs de banco de dados ou serviços externos.
- Toda configuração sensível deve ser lida de variáveis de ambiente via `os.environ` ou biblioteca como `python-dotenv`.

```python
# INCORRETO — VIOLA NORMA DE SEGURANÇA CRÍTICA
API_KEY = "sk-1234567890abcdef"
DATABASE_URL = "postgresql://user:password@prod-server/db"

# CORRETO
import os
API_KEY = os.environ["API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]
```

### 7.2 Arquivo .env

- Todo projeto deve ter um `.env.example` com todas as variáveis necessárias (sem valores reais).
- O arquivo `.env` deve estar no `.gitignore`.

---

## 8. Testes

### 8.1 Cobertura Mínima

- **80%** de cobertura de linhas para todos os módulos de negócio.
- **100%** de cobertura para funções que manipulam dados financeiros ou de segurança.

### 8.2 Estrutura de Testes

- Um arquivo de teste por módulo: `test_user_service.py` para `user_service.py`.
- Use `pytest` com fixtures ao invés de `unittest.TestCase`.
- Nomes de testes devem descrever o cenário: `test_calculate_discount_with_zero_rate_returns_zero`.

### 8.3 Testes de Unidade vs Integração

- Testes unitários **não devem** fazer chamadas reais a banco de dados ou APIs. Use mocks (`unittest.mock` ou `pytest-mock`).
- Testes de integração devem estar em diretório separado (`tests/integration/`).

---

## 9. Controle de Versão

### 9.1 Commits

- Formato obrigatório: `tipo(escopo): descrição curta` (Conventional Commits)
- Tipos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- Exemplo: `feat(auth): adiciona suporte a OAuth2`
- Máximo de **72 caracteres** na linha de assunto.

### 9.2 Pull Requests

- Todo PR deve ter título descritivo e descrição do problema resolvido.
- PRs não podem ter mais de **400 linhas alteradas** sem justificativa.
- É obrigatório que pelo menos **1 revisor** aprove antes do merge.
- Branches devem ser deletadas após o merge.
