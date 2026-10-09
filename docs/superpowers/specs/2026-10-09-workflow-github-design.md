# Workflow do GitHub: o RAG-Reviewer revisando PRs reais

Data: 2026-10-09. Branch: `feat/workflow-github` (a partir da `main` com D-010).
Decisao: D-011 (a registrar em `docs/DECISIONS.md` ao implementar).

## Objetivo

Levar o RAG-Reviewer para o ambiente real: um GitHub Action que, em cada PR,
coleta o diff pela API, recupera as normas da PEP 8, pede ao LLM as violacoes e
publica comentarios inline no PR, cada um com a norma citada, a severidade e como
corrigir. D-010 montou o ensaio local (dataset realista, 25 PRs); esta etapa
fecha o ciclo e verifica que o ensaio se transfere para o GitHub.

Entendimento confirmado com o autor:

- Pronto significa: codigo portado e testado, **mais** um teste em PR real neste
  repositorio, com o Action rodando e os comentarios conferidos contra o gabarito
  do dataset (opcao c).
- Como a PEP 8 e estilo, o revisor **nunca bloqueia** o PR: toda review sai como
  `COMMENT`. A severidade `CRITICAL` deixa de existir; ficam `HIGH`, `MEDIUM` e
  `LOW`.
- O modelo deve sinalizar ambiguidade da norma (F-004): quando o texto da PEP 8
  nao decide, o comentario diz que pode haver ambiguidade em vez de afirmar a
  violacao.
- O ponto de partida e a branch `main-completa`, que saiu da `main` no PR #9 e
  tem uma implementacao antiga do workflow (corpus e prompts de "normas
  organizacionais"). Aproveita-se o que serve, adaptado ao estado atual.

Fora do escopo: medir a qualidade da `suggestion` (aplicar a correcao e rodar o
ruff), comparar com o ruff como detector (F-005), tratar o `except:` tolerado no
prompt, trocar o modelo de embedding, mudar o corte de 8 chunks.

## Abordagem

Portar para a `main` atual os modulos do workflow da `main-completa`, adaptados.
Nao mesclar a `main-completa` (conflitos em todo lugar e traz o corpus e os
prompts antigos) e nao reescrever (o essencial ja existe).

Nao se porta o que a `main-completa` declara e nao usa: `PyGithub`, `tiktoken` e
`max_diff_tokens`, alem das dependencias de PDF e DOCX. Entra `requests` (usado
pelo coletor e pelo publisher).

## Componentes

| Arquivo | Responsabilidade | Origem |
|---|---|---|
| `rag_reviewer/diff_parser.py` | `PullRequestDiff` e `DiffCollector`: lista os arquivos do PR pela API (paginacao), descarta deletados, binarios, sem patch e nao `.py`, e monta cada `FileDiff` (`filename`, `patch`, `status`, `additions`, `deletions`, `added_lines`). O `FileDiff` atual da `main` nao muda | porta |
| `rag_reviewer/retriever.py` | `retrieve_for_diff(pr_diff)`: aplica `retrieve_for_file` (busca por linha, uniao com o maior score, corte em 8) a cada arquivo com linhas adicionadas | adapta |
| `rag_reviewer/llm_client.py` | Fica como esta (`max_tokens` 900, `_recover_truncated`). `Violation` ganha `ambiguous: bool` (padrao `False`); `_VALID_SEVERITIES` perde `CRITICAL` | adapta |
| `rag_reviewer/github_publisher.py` | Uma review `COMMENT` por execucao, com um comentario inline por violacao e um sumario | porta com correcoes |
| `rag_reviewer/reviewer.py` | Orquestrador: diff, recuperacao, LLM por arquivo, publicacao | porta, sem `request_changes` |
| `rag_reviewer/main.py` | Ponto de entrada do Action; sem `show_locals=True` (vaza segredos no log) | porta |
| `.github/workflows/rag_reviewer.yml` | Gatilho `pull_request` (opened, synchronize, reopened) em `**/*.py`, permissoes `contents: read` e `pull-requests: write`, Python 3.11, cache do modelo | porta |
| `rag_reviewer/config.py` | Acrescenta `pr_base_sha` se o coletor precisar; remove `block_on_critical` | adapta |

`PR_BASE_SHA`, que o workflow antigo exporta, so se mantem se algum modulo o usar;
caso contrario sai do workflow.

## Fluxo de execucao

1. `DiffCollector.collect()`: `GET /repos/{repo}/pulls/{n}/files`, todas as
   paginas. Sem arquivos `.py` revisaveis, publica um aviso curto e termina.
2. `Retriever.retrieve_for_diff`: um `RetrievedContext` por arquivo com linhas
   adicionadas e contexto acima do limiar. Arquivo sem contexto nao vai ao LLM.
3. LLM: uma chamada por arquivo, como na avaliacao. Falha numa chamada
   (JSON invalido, 429 persistente, erro de rede) **nao derruba a execucao**: o
   arquivo entra no sumario como "nao revisado" e os demais seguem. O Action tem
   `timeout-minutes: 10`; esperas longas de rate limit nao cabem nele, entao no
   Action nao ha o backoff de minutos da avaliacao (uma nova tentativa curta, no
   maximo).
4. Publicacao: uma unica `POST /pulls/{n}/reviews` com `event: COMMENT`, `commit_id`
   igual ao `head_sha` e os comentarios inline; o corpo e o sumario com a tabela
   por severidade e a lista de arquivos nao revisados.
5. Sem violacoes, um comentario curto de aprovacao (`issues/{n}/comments`).

Todo o fluxo roda como `python -m rag_reviewer.main` dentro do Action. O codigo
nao tem caminho de execucao local contra um PR; o teste local usa mocks (abaixo).

## Comentario publicado

Cada comentario inline traz: severidade, descricao da violacao, a norma citada (a
secao da PEP 8) e a sugestao de correcao. Se `ambiguous` for `true`, o texto
abre com o aviso de possivel ambiguidade e nao afirma a violacao (a severidade
fica `LOW`). O sumario usa a tabela por severidade (`HIGH`, `MEDIUM`, `LOW`) e,
no rodape, o nome do modelo.

O texto dos comentarios nao menciona "normas organizacionais"; a fonte e a PEP 8.

## Correcoes no publisher

Problemas vistos ao ler `github_publisher.py` da `main-completa`:

1. **Posicao da linha.** `_find_diff_position` devolve a primeira linha adicionada
   que contem o trecho. Linhas repetidas no arquivo (ou trecho curto) caem na linha
   errada. Passa a preferir igualdade exata (apos `strip`) a substring e a consumir
   cada ocorrencia uma vez, para duas violacoes de texto igual irem a duas linhas
   diferentes. Linha em branco nunca e candidata.
2. **Rejeicao da review inteira.** Uma posicao invalida pode fazer a API recusar a
   review toda (422). Violacao sem posicao localizavel vai so ao sumario; se mesmo
   assim a API recusar, tenta-se de novo sem comentarios inline (so o sumario) e o
   erro e registrado.
3. **Repeticao a cada push.** Em `synchronize` o Action roda de novo. Antes de
   publicar, le os comentarios existentes (`GET /pulls/{n}/comments`) e pula o
   comentario cujo `path` e corpo ja existem. Sem comentario novo e sem aviso novo,
   nao publica nada.
4. **Emojis e `show_locals`.** O codigo antigo usa emojis nos comentarios; os
   comentarios passam a ser texto simples (severidade entre colchetes), seguindo o
   estilo do projeto. Trocar de volta e uma linha, se o autor preferir.
   `show_locals` fica desligado no `main.py`.

## Severidade e bloqueio

- `CRITICAL` sai de: `_VALID_SEVERITIES`, dos quatro prompts (`system_prompt*.txt`
  e `review_template*.txt`, inclusive os `*_sem_rag` quando existirem na `main`),
  da `Violation`, do publisher, do `config.py` (`block_on_critical`) e do
  `arquitetura.md`. `request_changes` deixa de existir.
- Os testes de `CRITICAL` e `request_changes` mudam ou saem.
- O modelo escolhe `HIGH`, `MEDIUM` ou `LOW`. A severidade nao e medida (D-010);
  o spec nao a trata como resultado.

## Ambiguidade (F-004)

O schema de saida ganha `"ambiguous": true | false` por violacao. O prompt explica
quando usar: o texto da PEP 8 nao decide o caso (por exemplo, um literal global em
minusculas, que pode ou nao ser uma constante). `Violation.ambiguous` le o campo
com padrao `False` (resposta sem o campo continua valida). A avaliacao ja reporta
quantas linhas ambiguas o modelo sinalizou; passa a poder contar tambem as que ele
marcou como ambiguas.

## Consistencia entre producao e avaliacao

O prompt de producao e o da avaliacao sao o mesmo arquivo. Retirar `CRITICAL` e
acrescentar `ambiguous` muda o prompt, e os numeros da rodada 2 de D-010 (P 0,8556,
R 0,7857, F1 0,8191) deixam de valer para ele. Como verificacao, roda-se a avaliacao
oficial de novo (**rodada 3**, uma repeticao, cerca de 130 mil tokens da Groq) e
compara-se com a rodada 2. O criterio e nao haver queda relevante de F1; uma queda
fica registrada e investigada, nao escondida. A rodada 3 so roda quando o autor
pedir, com a cota livre (a cota diaria e uma janela deslizante, nao zera as 20:00
locais).

A branch `feat/baseline-sem-recuperacao` (PR #15) tem prompts `*_sem_rag` com
`CRITICAL`. Se o PR #15 for mesclado antes, esses dois arquivos entram nesta
mudanca; se for depois, o PR #15 e atualizado para nao reintroduzir `CRITICAL`.

## Teste em PR real

O workflow so e testado de verdade num PR do GitHub. Sequencia:

1. Implementar nesta branch (`feat/workflow-github`) e abrir o PR; o autor mescla
   na `main`. O workflow passa a existir na `main`.
2. Montar uma base descartavel a partir da `main` com o estado "antes" dos arquivos
   de 3 PRs do dataset (ao menos um com arquivo modificado e um limpo). O estado
   "antes" de um arquivo modificado sai de desfazer o patch sobre o `source_after`.
3. Abrir os 3 PRs de teste: cada um adiciona ou modifica os arquivos do PR do
   dataset. O Action roda neles. Os arquivos ficam em caminhos proprios (por
   exemplo `app/...`), sem tocar o codigo do projeto.
4. Ler as reviews pela API e conferir cada comentario inline contra o gabarito do
   PR: linhas sinalizadas contra `viola`, norma citada contra a familia, ambiguas
   a parte. Resultado: matriz por linha dos 3 PRs e comparacao com o que a
   avaliacao local deu para os mesmos PRs.
5. Fechar os PRs de teste e apagar a base descartavel. Registrar tudo em
   `docs/RELATORIO-RESULTADOS.md` e `docs/DECISIONS.md`.

Custo estimado do passo 3 e 4: cerca de 10 a 15 chamadas ao LLM (30 a 50 mil
tokens). Abrir os PRs de teste e publica-los no repositorio, entao o autor
confirma cada abertura.

Verificacoes que o teste real precisa fechar:

- O secret `QDRANT_URL` do GitHub aponta para o cluster que tem a `pep8_chunks`
  (43 chunks, modelo multilingue). Hoje so se sabe que o `.env` local aponta.
- O tempo do job cabe em 10 minutos: instalar `torch` e `sentence-transformers` e
  baixar o modelo de cerca de 470 MB. Se estourar, usar o `torch` CPU e o cache do
  Hugging Face; se ainda estourar, subir o timeout ou registrar a limitacao.
- O Action roda em PR cuja base e uma branch descartavel (e nao so `main`): o
  gatilho `pull_request` sem filtro de branch base cobre isso.
- O formato `position` da API de review (usado pelo publisher antigo) funciona; a
  alternativa e `line` mais `side: RIGHT`. Confere-se na documentacao da API e no
  teste real antes de fixar.

## Testes automatizados

- `diff_parser`: paginacao, filtros (deletado, binario, sem patch, nao `.py`),
  `added_lines` de arquivo modificado com hunks, variaveis de ambiente ausentes.
- `retriever`: `retrieve_for_diff` ignora arquivo sem linhas adicionadas e sem
  contexto; mantem o comportamento por linha.
- `github_publisher` (HTTP simulado): posicao com linhas repetidas, trecho sem
  posicao vai ao sumario, re-tentativa sem inline apos 422, nao repete comentario
  existente, formato do comentario normal e ambiguo, corpo do sumario.
- `reviewer`: falha numa chamada do LLM nao derruba a execucao, sem
  `request_changes` mesmo com severidade `HIGH`.
- `llm_client`: `ambiguous` presente e ausente, `CRITICAL` rejeitado.
- Prompts: nenhum dos prompts cita `CRITICAL` nem "normas organizacionais".
- Nenhum teste chama a API real do GitHub, do Qdrant ou da Groq.

## Documentacao

`docs/DECISIONS.md` (D-011), `docs/STATUS.md`, `docs/GUIA-DO-PROJETO.md`,
`README.md`, `arquitetura.md` (retira `CRITICAL` e `BLOCK_ON_CRITICAL`),
`docs/TODO-FUTURO.md` (F-004 passa a implementado), memoria do projeto.

## Riscos e limitacoes

- Uma repeticao e 3 PRs de teste: o teste real e uma verificacao de transferencia,
  nao uma estatistica.
- A severidade e a `suggestion` continuam sem medicao.
- Se a recuperacao do GitHub (rede, rate limit da API) falhar, o Action falha com
  mensagem clara; nao ha fallback para dados simulados.
- O Action e executado com os secrets do repositorio. PRs de fork nao recebem
  secrets e o job nao tem como rodar neles; isso e aceito e documentado, fora do
  escopo desta etapa.
