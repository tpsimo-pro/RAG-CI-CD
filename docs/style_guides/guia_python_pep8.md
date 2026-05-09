# Guia de Estilo Python Corporativo (Baseado na PEP-8)

> **Versão:** 1.0  
> **Status:** Vigente  
> **Objetivo:** Estabelecer um padrão único e rigoroso para todo o código Python da empresa, baseado na PEP-8, garantindo consistência, legibilidade e facilidade de manutenção.

---

## 1. Layout do Código

### 1.1 Tamanho Máximo de Linha
- O limite estrito de comprimento para todas as linhas de código é de **79 caracteres**.
- Para blocos de texto longo (docstrings ou comentários), o limite é de **72 caracteres**.
- **Justificativa:** Linhas curtas facilitam a revisão de código lado a lado em telas divididas (como no GitHub PR diff).

### 1.2 Indentação
- Use **exclusivamente 4 espaços** por nível de indentação.
- **Proibido:** O uso de *Tabs* (\t) é estritamente proibido. Não misture tabs e espaços.
- Em quebras de linha de parâmetros de funções, alinhe verticalmente com o parêntese de abertura ou use indentação suspensa (hanging indent) com 4 espaços extras.

**Correto (Hanging Indent):**
```python
def my_complex_function(
        parameter_one, parameter_two,
        parameter_three, parameter_four):
    print(parameter_one)
```

### 1.3 Linhas em Branco
- Cerque definições de classes e funções de nível superior (top-level) com **duas linhas em branco**.
- Cerque definições de métodos dentro de uma classe com **uma linha em branco**.
- Linhas em branco extras podem ser usadas (esparsamente) para separar grupos de funções relacionadas.

---

## 2. Nomenclatura e Convenções (Naming)

A nomenclatura deve revelar a intenção e o contexto da variável.

| Tipo | Regra | Exemplo |
|---|---|---|
| Pacotes e Módulos | `snake_case` curto | `user_manager.py` |
| Classes | `PascalCase` | `PaymentProcessor` |
| Exceções | `PascalCase` com sufixo `Error` | `InvalidTokenError` |
| Funções e Variáveis | `snake_case` | `calculate_total_tax` |
| Constantes | `UPPER_SNAKE_CASE` | `MAX_OVERFLOW_LIMIT` |
| Variáveis Privadas | Prefixo com underscore `_` | `_internal_cache` |

### 2.1 Regras de Nomenclatura Restritas
- **Nomes de 1 caractere:** Nunca use os caracteres `l` (L minúsculo), `O` (O maiúsculo) ou `I` (i maiúsculo) como variáveis de uma única letra, pois são confusos.
- Evite variáveis de uma letra (ex: `x`, `y`, `val`) a menos que sejam índices de loop curtos (`i`, `j`).

---

## 3. Importações

As importações devem sempre ficar no topo do arquivo, logo após os comentários/docstrings do módulo.

### 3.1 Agrupamento
As importações devem ser agrupadas em blocos separados por uma linha em branco na seguinte ordem:
1. Bibliotecas padrão do Python (ex: `os`, `sys`, `json`).
2. Bibliotecas de terceiros (ex: `requests`, `sqlalchemy`).
3. Importações locais da própria aplicação (ex: `from app.models import User`).

### 3.2 Regras de Importação
- **Proibido:** Importações com asterisco (`from module import *`) são completamente proibidas, pois poluem o namespace e dificultam a rastreabilidade.
- Importações devem ser preferencialmente em linhas separadas.

**Correto:**
```python
import os
import sys
from subprocess import Popen, PIPE
```

---

## 4. Uso de Espaços em Branco em Expressões

- **Evite espaços extras imediatamente dentro de parênteses, chaves ou colchetes.**
  - Correto: `spam(ham[1], {eggs: 2})`
  - Incorreto: `spam( ham[ 1 ], { eggs: 2 } )`
- **Sempre cerque operadores matemáticos, de comparação e de atribuição com um único espaço de cada lado.**
  - Correto: `x = 1`
  - Incorreto: `x=1` ou `x   = 1`
- **Não use espaços ao redor do sinal `=` para indicar um argumento nomeado ou um valor padrão de parâmetro.**
  - Correto: `def complex(real, imag=0.0):`
  - Incorreto: `def complex(real, imag = 0.0):`

---

## 5. Práticas de Código e Idiomas Pythonicos

- **Comparações booleanas:** Não compare valores booleanos com `== True` ou `== False`.
  - Correto: `if is_valid:`
  - Incorreto: `if is_valid == True:`
- **Comparações de nulos:** Sempre use `is` ou `is not` ao comparar com `None`.
  - Correto: `if value is not None:`
  - Incorreto: `if value != None:`
- **Retorno antecipado (Early Return):** Para evitar aninhamento excessivo, use a técnica de retorno antecipado.

**Correto:**
```python
def process_data(data):
    if not data:
        return False
    
    # Processamento complexo
    return True
```
