# ADR-002: Arquitetura e Escopo do Synesis LSP para VSCode

**Status:** Aceito
**Data:** 03-01-2026
**Contexto:** Implementação do suporte a ferramentas de edição para a linguagem Synesis v1.1.

## 1. Contexto e Problema

Precisamos fornecer feedback em tempo real (diagnósticos, erros, warnings) para pesquisadores utilizando a linguagem Synesis. Atualmente, o feedback ocorre apenas via CLI após a execução do comando de compilação. Existe o risco de duplicar a lógica de validação no cliente (VSCode editor), criando inconsistências semânticas e carga de manutenção dupla.

## 2. Decisão Arquitetural

O Synesis LSP será implementado estritamente como um **Adaptador de Protocolo (Protocol Adapter)**, não como um analisador independente.

### Princípios Normativos:

1. **Fonte Única de Verdade:** O Compilador (`synesis.compiler`) é a única autoridade. O LSP não re-implementa regras de gramática ou validação.
2. **Estado Efêmero:** O LSP não mantém estado persistente (não escreve arquivos, não gera bancos de dados).
3. **Fluxo Unidirecional:** Editor → LSP → Compilador (Memória) → Diagnósticos → Editor.
4. **Fronteira de Responsabilidade:**
* **Compilador:** Análise sintática (Lark), validação semântica, geração de mensagens pedagógicas.
* **LSP:** Gerenciamento de ciclo de vida do documento (`textDocument/didChange`), mapeamento de objetos de erro do compilador para objetos de diagnóstico do protocolo LSP (`Diagnostic`).



## 3. Detalhes Técnicos da Decisão

### 3.1 Integração com Compilador v1.1

O LSP invocará o pipeline de compilação existente, mas interromperá o processo antes da etapa de **Exportação**.

* **Entrada:** String crua do documento aberto no editor.
* **Processamento:** Parser Lark (LALR) + Validação Semântica.
* **Saída:** Instâncias de `ValidationResult` (conforme definido em `ast/results.py`).

### 3.2 Tratamento de Erros

O LSP consumirá diretamente o `SynesisErrorHandler`.

* As mensagens "pedagógicas" definidas no compilador serão o corpo da mensagem do Diagnóstico LSP.
* A severidade (`ERROR`, `WARNING`, `INFO`) do compilador será mapeada 1:1 para `DiagnosticSeverity` do LSP.

### 3.3 Resolução de Dependências e Contexto

O LSP opera em modo de **validação isolada de arquivo único**, mas precisa resolver dependências externas para manter consistência com o compilador completo.

**Estratégia de Resolução:**

1. **Templates (`.synt`)**:
   - Resolução via arquivo de projeto (`.synp`) na raiz do workspace
   - O template valido e o definido no `PROJECT` (ex: `TEMPLATE "bibliometrics.synt"`)
   - Se `.synp` não existir: validação parcial (apenas sintaxe + palavras-chave)

2. **Bibliografia (`.bib`)**:
   - Resolvida via `INCLUDE BIBLIOGRAPHY` no `.synp`
   - Se não encontrado: bibrefs geram WARNING em vez de ERROR

3. **Ontologias (`.syno`)**:
   - Códigos não definidos sempre geram WARNING (comportamento atual do compilador)
   - Não requer carregamento de ontologias externas nesta fase

4. **Arquivos INCLUDE**:
   - LSP **não** resolve includes (apenas valida o arquivo individual)
   - Inconsistências serão detectadas apenas na compilação completa via CLI

**Garantia de Consistência:**
- Erros sintáticos: sempre reportados (independem de contexto)
- Erros semânticos: reportados quando há contexto suficiente
- Avisos: indicam validação parcial por falta de contexto

### 3.4 Interface Contratual Compilador ↔ LSP

O compilador expõe uma função específica para validação de arquivo único:

```python
# synesis/lsp_adapter.py (A SER CRIADO)

@dataclass
class ValidationContext:
    """Contexto opcional para validação enriquecida."""
    template: Optional[TemplateNode] = None
    bibliography: Optional[Dict[str, BibEntry]] = None
    ontology_index: Optional[Dict[str, OntologyNode]] = None

def validate_single_file(
    source: str,
    file_uri: str,
    context: Optional[ValidationContext] = None
) -> ValidationResult:
    """
    Valida texto Synesis em memória sem persistência.

    Args:
        source: Conteúdo do arquivo como string
        file_uri: URI do arquivo (para rastreabilidade de erros)
        context: Contexto opcional com template/bibliografia/ontologia

    Returns:
        ValidationResult com erros, warnings e info

    Comportamento:
        - Sempre valida sintaxe (parser Lark)
        - Valida semântica se context.template fornecido
        - Bibrefs validados se context.bibliography fornecido
        - Códigos sempre geram WARNING se não em ontology_index
    """
```

### 3.5 Tratamento de Result Types

O compilador usa `Result[T, E]` types. O LSP deve desembrulhar corretamente:

```python
# Padrão de uso no LSP
from synesis.ast.results import ValidationResult

result = validate_single_file(source, uri, context)

# ValidationResult não usa Result wrapper - retorna direto
diagnostics = []
for error in result.errors + result.warnings + result.info:
    diagnostics.append(_build_diagnostic(error))
```

**Nota:** `ValidationResult` já é um agregador - não precisa de unwrap. Exceções do parser Lark devem ser capturadas e convertidas em `ValidationError`.

### 3.6 Exclusões (O que não fazer)

* **Autocomplete (nesta fase):** Adiado até que a AST suporte navegação robusta.
* **Correção Rápida (Quick Fix):** O LSP não alterará o código do usuário (princípio da não-interferência no pensamento do pesquisador).
* **Geração de Artefatos:** O LSP nunca gerará arquivos `.json` ou `.csv`.

## 4. Consequências

### Positivas

* **Consistência Absoluta:** Impossível o editor reportar um erro que o compilador aceita (e vice-versa).
* **Manutenibilidade:** Atualizações na gramática ou nas regras semânticas do Synesis se propagam automaticamente para o editor sem alteração no código do LSP.
* **Performance:** Foca o LSP apenas em IO e transporte de mensagens, delegando o processamento pesado para o core já otimizado.

### Negativas

* **Latência:** Para arquivos gigantescos, repassar o texto completo para o compilador a cada keystroke pode ser custoso (mitigação: *debounce* de 300ms implementado no servidor Python).
* **Dependência:** Se o compilador quebrar (crash), o LSP morre junto. O tratamento de exceções no LSP deve ser robusto (blindagem).

---

### Mapeamento Preliminar: Compilador v1.1 → LSP

Baseado no seu `index.md`, aqui está como os componentes se encaixam:

| Conceito LSP | Componente Synesis (v1.1) Correspondente | Ação do Adaptador |
| --- | --- | --- |
| **Diagnostic Range** | `SourceLocation` (file, line, col) | Converter `line/col` (1-based) para `Position` (0-based) do LSP. |
| **Diagnostic Message** | `ValidationResult.to_diagnostic()` | Extrair string de texto puro. |
| **Diagnostic Severity** | `ErrorSeverity` (Enum) | Mapear: `ERROR`→`Error`, `WARNING`→`Warning`, `INFO`→`Information`. |
| **Parsing** | `Lark` (LALR) | Invocar parser. Capturar `UnexpectedToken` e `UnexpectedCharacters` para erros de sintaxe. |
| **Sugestão de Correção** | `UnregisteredSource.suggestions` | (Futuro) Usar para `CodeAction`, mas por enquanto apenas exibir na mensagem. |

---

IMPORTANTE: Para evitar *overengineering* e alucinações de IA (como inventar protocolos JSON-RPC do zero), a melhor decisão técnica é adotar um framework de mercado que abstraia a camada de comunicação, permitindo que você foque apenas na lógica de **Adaptação** definida no ADR-002.

Aqui está o plano de execução:

---

## 5. Pré-Requisito: Implementação no Compilador

**ANTES** de implementar o LSP, é necessário criar a interface de adaptação no compilador.

### Arquivo a Criar: `synesis/lsp_adapter.py`

Este módulo expõe a função `validate_single_file()` que o LSP invocará.

**Checklist de Implementação no Compilador:**

#### Etapa 1: Criar estrutura básica do adaptador
- [ ] Criar arquivo `synesis/lsp_adapter.py`
- [ ] Implementar dataclass `ValidationContext`
- [ ] Importar componentes necessários: `parse_file`, `SynesisTransformer`, `SemanticValidator`

#### Etapa 2: Implementar parsing de string in-memory
- [ ] Adaptar `parse_file()` (que atualmente lê do disco) para aceitar string
- [ ] Ou criar wrapper que escreve temporariamente em memória usando `io.StringIO`
- [ ] Capturar exceções Lark (`UnexpectedToken`, `UnexpectedCharacters`)
- [ ] Converter exceções Lark em `ValidationError` apropriados

#### Etapa 3: Implementar validação semântica isolada
- [ ] Criar função `validate_single_file(source, file_uri, context)`
- [ ] Invocar parser Lark com string source
- [ ] Se `context.template` fornecido: invocar `SemanticValidator`
- [ ] Se `context.bibliography` fornecido: validar bibrefs
- [ ] Retornar `ValidationResult` agregado

#### Etapa 4: Implementar descoberta automática de contexto
- [ ] Criar função helper `_discover_context(file_uri) -> ValidationContext`
- [ ] Buscar `.synt` no diretório pai
- [ ] Buscar `.bib` referenciado em `.synp` (se existir)
- [ ] Retornar contexto parcial se dependências não encontradas

#### Etapa 5: Tratamento especial para bibrefs ausentes
- [ ] Modificar `UnregisteredSource` para aceitar severidade customizável
- [ ] Quando `context.bibliography` é `None`, gerar WARNING em vez de ERROR
- [ ] Adicionar mensagem indicando "validação parcial - bibliografia não disponível"

#### Etapa 6: Testes unitários
- [ ] Testar parsing de string com sintaxe válida
- [ ] Testar parsing de string com erro sintático
- [ ] Testar validação com contexto completo
- [ ] Testar validação com contexto parcial (sem template/bib)
- [ ] Testar descoberta automática de contexto

**Perguntas de Implementação para o Compilador:**

Antes de prosseguir, preciso de suas decisões sobre:

1. **Parsing In-Memory**: O parser Lark atual (`synesis.parser.lexer.parse_file`) lê de `Path`. Como você prefere adaptar?
   - **Opção A**: Criar `parse_string(source: str)` que usa `Lark.parse()` diretamente
   - **Opção B**: Usar `io.StringIO` para simular arquivo
   - **Opção C**: Modificar `parse_file` para aceitar `Union[Path, str]`

2. **Conversão de Exceções Lark**: Quando o parser Lark falha, ele lança exceções. Como converter?
   - **Opção A**: Criar novos `ValidationError` types (`SyntaxError`, `UnexpectedToken`)
   - **Opção B**: Capturar e converter para `ValidationError` genérico com mensagem da exceção
   - **Opção C**: Deixar exceções propagarem (LSP captura e converte)

3. **Severidade de Bibrefs sem Contexto**: Quando `.bib` não está disponível, o que fazer?
   - **Opção A**: Sempre WARNING (validação parcial)
   - **Opção B**: Não validar bibrefs (silenciosamente ignorar)
   - **Opção C**: ERROR com mensagem "configure arquivo .bib"

4. **Cache de Contexto**: O LSP validará o mesmo arquivo múltiplas vezes. Devemos:
   - **Opção A**: Deixar cache para o LSP implementar
   - **Opção B**: Implementar cache de template/bibliografia no adaptador
   - **Opção C**: Não fazer cache (recarregar sempre)

5. **Descoberta de Contexto**: A busca automática por `.synt` e `.bib` deve ser:
   - **Opção A**: Implementada no adaptador (busca no filesystem)
   - **Opção B**: Responsabilidade do LSP (passa contexto explícito)
   - **Opção C**: Híbrida (adaptador tenta descobrir, LSP pode sobrescrever)

**STATUS: ✅ IMPLEMENTADO**

#### Decisões Tomadas e Implementadas:

1. **Parsing In-Memory**: ✅ Opção A - Função `parse_string()` já existente no lexer
2. **Conversão de Exceções Lark**: ✅ Opção A - Criado `SyntaxError(ValidationError)`
3. **Severidade de Bibrefs**: ✅ Opção A - Não valida quando `bibliography=None`
4. **Cache de Contexto**: ✅ Opção A - Responsabilidade do LSP
5. **Descoberta de Contexto**: ✅ Opção A - Implementada no adaptador

#### Arquivos Criados/Modificados:

**Criados:**
- ✅ `synesis/lsp_adapter.py` (319 linhas) - Interface completa LSP ↔ Compilador
- ✅ `tests/test_lsp_adapter.py` (196 linhas) - 13 testes unitários (todos passando)

**Modificados:**
- ✅ `synesis/semantic/validator.py` - Ajustado `_validate_bibref()` para aceitar `bibliography=None`

#### Interface Pública Disponível:

```python
from synesis.lsp_adapter import validate_single_file, ValidationContext

# Validação com descoberta automática de contexto
result = validate_single_file(source_code, file_uri)

# Validação com contexto explícito
context = ValidationContext(template=template, bibliography=bib)
result = validate_single_file(source_code, file_uri, context)

# Resultado
for error in result.errors:
    print(f"{error.location}: {error.to_diagnostic()}")
```

#### Testes Implementados:

- ✅ `test_validate_syntax_error` - Captura de erros sintáticos
- ✅ `test_validate_valid_syntax_minimal` - Parsing sem validação semântica
- ✅ `test_validate_with_template_valid` - Validação com template
- ✅ `test_validate_without_bibliography` - Bibrefs ignorados quando bib=None
- ✅ `test_validate_with_bibliography_missing_ref` - Erro de bibref ausente
- ✅ `test_validate_item_with_codes` - Validação de códigos
- ✅ `test_discover_context_no_files` - Contexto vazio
- ✅ `test_discover_context_with_template` - Descoberta de template
- ✅ `test_find_template_in_parent` - Busca em diretórios pais
- ✅ `test_find_bibliography` - Busca de arquivo .bib
- ✅ `test_parse_multiple_nodes` - Múltiplos nós no mesmo arquivo
- ✅ `test_syntax_error_provides_location` - Localização precisa de erros
- ✅ `test_file_uri_with_file_protocol` - Suporte a URIs file://

**Resultado:** 13/13 testes passando ✅

---

## 6. Estrutura de Diretórios do Projeto LSP

O LSP será implementado **separadamente** do compilador, na pasta `0_Synesis/LSP`:

```
0_Synesis/
├── Compiler/                    # Compilador Synesis (existente)
│   └── synesis/
│       ├── lsp_adapter.py      # ✅ Interface LSP ↔ Compilador (PRONTO)
│       └── ...
│
└── LSP/                         # Language Server Protocol (novo)
    ├── synesis_lsp/             # Pacote Python do LSP Server
    │   ├── __init__.py
    │   ├── server.py            # Servidor principal com pygls
    │   ├── converters.py        # ValidationError → Diagnostic
    │   └── handlers.py          # Event handlers (did_open, did_change)
    │
    ├── tests/                   # Testes do LSP
    │   ├── __init__.py
    │   ├── test_server.py
    │   └── test_converters.py
    │
    ├── vscode-extension/        # Extensão VSCode (TypeScript)
    │   ├── src/
    │   │   └── extension.ts     # Cliente LSP
    │   ├── package.json
    │   └── tsconfig.json
    │
    ├── pyproject.toml           # Configuração do pacote Python
    ├── requirements.txt         # Dependências (pygls, synesis)
    └── lsp_index.md            # Este documento
```

### Dependências entre Pacotes:

```
┌─────────────────────┐
│  vscode-extension   │  (Cliente TypeScript)
│  (package.json)     │
└──────────┬──────────┘
           │ comunica via stdio
           ▼
┌─────────────────────┐
│   synesis_lsp       │  (Servidor Python)
│   (pyproject.toml)  │
└──────────┬──────────┘
           │ importa
           ▼
┌─────────────────────┐
│      synesis        │  (Compilador)
│   (existente)       │
│   lsp_adapter.py    │
└─────────────────────┘
```

### Instalação:

```bash
# 1. Instalar compilador (se não instalado)
cd 0_Synesis/Compiler
pip install -e .

# 2. Instalar LSP server
cd ../LSP
pip install -e .

# 3. Instalar extensão VSCode
cd vscode-extension
npm install
npm run compile
```

---

### 1. Base Tecnológica e Repositório de Referência

Não reinvente a roda. O padrão da indústria para criar LSPs em Python é a biblioteca **`pygls` (Python Generic Language Server)**. Ela é mantida pela Open Law Library e é a base de LSPs oficiais como o de `reStructuredText` e `Fortran`.

* **Repositório Base:** [openlawlibrary/pygls](https://github.com/openlawlibrary/pygls)
* **Exemplo Específico:** Utilize o exemplo [json-extension](https://www.google.com/search?q=https://github.com/openlawlibrary/pygls/tree/master/examples/json-extension) dentro do repositório como seu "template". Ele faz exatamente o que você precisa: carrega um arquivo, valida (no caso dele, JSON) e retorna diagnósticos.

**Por que esta escolha é sólida?**

1. **Abstração de Protocolo:** O `pygls` já implementa toda a especificação LSP 3.16+ (mensagens, threads, async IO).
2. **Assincronicidade:** Usa `asyncio` nativo do Python, garantindo que o servidor não trave o editor enquanto o compilador roda.
3. **Tipagem:** Possui definições de tipos (`types.py`) para todos os objetos LSP (Diagnostic, Range, Position), evitando que você tenha que criar dataclasses manuais.

---

### 2. Checklist de Implementação (Focado no ADR-002)

Este checklist assume que o pacote `synesis` (seu compilador) já está instalável ou acessível via `PYTHONPATH`.

#### Fase 1: Scaffold do Servidor (Python)

* [ ] Instalar `pygls` no ambiente virtual do projeto (`pip install pygls`).
* [ ] Criar arquivo `synesis/lsp/server.py`.
* [ ] Instanciar o objeto `LanguageServer("synesis-lsp", "v0.1")`.
* [ ] Implementar a função de start/entrypoint (TCP ou STDIO).
* [ ] **Teste de Fumaça:** Rodar o servidor e verificar se ele inicia sem erros.

#### Fase 2: O Adaptador (Compiler → LSP)

* [ ] Criar função utilitária `_validate(ls, params)` que recebe o documento.
* [ ] Implementar conversão de coordenadas:
* Synesis (linha 1-based, coluna) → LSP `Position` (linha 0-based, character).
* Synesis `SourceLocation` → LSP `Range` (Start/End).


* [ ] Implementar mapeamento de Severidade:
* `ErrorSeverity.ERROR` → `DiagnosticSeverity.Error` (1).
* `ErrorSeverity.WARNING` → `DiagnosticSeverity.Warning` (2).
* `ErrorSeverity.INFO` → `DiagnosticSeverity.Information` (3).


* [ ] Implementar a chamada ao compilador:
* Invocar parser/validator com o texto cru (`document.source`).
* Capturar lista de `ValidationResult`.
* Converter para lista de `Diagnostic` (pygls).


* [ ] Chamar `ls.publish_diagnostics(uri, diagnostics)`.

#### Fase 3: Eventos de Ciclo de Vida

* [ ] Registrar decorador `@server.feature(TEXT_DOCUMENT_DID_OPEN)`.
* [ ] Registrar decorador `@server.feature(TEXT_DOCUMENT_DID_CHANGE)`.
* [ ] Configurar *debounce* (opcional, mas recomendado): aguardar 300ms após a última digitação antes de chamar o compilador.

#### Fase 4: Cliente VSCode (Minimalista)

* [ ] Criar pasta `editors/vscode`.
* [ ] Inicializar `package.json` definindo:
* `activationEvents`: `onLanguage:synesis`.
* `contributes.languages`: extensão `.syn`, `.synp`, `.syno`.


* [ ] Criar `client/src/extension.ts`:
* Usar `vscode-languageclient` para lançar o processo python (`python -m synesis.lsp`).

---

### 3. Prompts para Implementação

Utilize estes prompts em sequência com seu assistente de código (eu ou outro). Eles são desenhados para injetar o contexto necessário e restringir a "criatividade" da IA apenas à sintaxe correta.

#### Prompt 1: Scaffold do Servidor com pygls

> "Atue como um Engenheiro de Software Sênior em Python. Vamos criar o servidor LSP para a linguagem Synesis usando a biblioteca `pygls`.
> **Contexto:** Já tenho um compilador funcional no pacote `synesis`.
> **Tarefa:** Crie o arquivo `synesis/lsp/server.py`.
> **Requisitos:**
> 1. Importe `LanguageServer` de `pygls.server`.
> 2. Inicialize o servidor com nome 'synesis-lsp' e versão '0.1'.
> 3. Configure a execução para funcionar via STDIO (entrada/saída padrão), pois será chamado pelo VSCode.
> 4. Deixe espaços reservados (com `pass` e comentários TODO) para os eventos `TEXT_DOCUMENT_DID_OPEN` e `TEXT_DOCUMENT_DID_CHANGE`.
> 5. Use Type Hints estritos.
> 6. Não implemente lógica de validação ainda, apenas a estrutura de execução."
> 
> 

#### Prompt 2: Lógica de Adaptação (Mapeamento de Tipos)

> "Agora vamos implementar a lógica de transformação de dados. O compilador Synesis retorna erros com a seguinte estrutura (dataclass):
> ```python
> @dataclass
> class ValidationResult:
>     location: SourceLocation # tem .line (1-based) e .column
>     severity: ErrorSeverity  # Enum: ERROR, WARNING, INFO
>     message: str             # Texto do erro
> 
> ```
> 
> 
> **Tarefa:** Implemente dentro do `synesis/lsp/server.py`:
> 1. Uma função helper `_convert_severity(synesis_severity) -> DiagnosticSeverity`.
> 2. Uma função helper `_build_diagnostic(validation_result) -> Diagnostic`. Note que o LSP usa indexação zero (0-based) para linhas, então subtraia 1. Assuma que o erro tem comprimento 1 se não houver range final definido.
> 3. Use as classes `Diagnostic`, `Range`, `Position`, `DiagnosticSeverity` do módulo `lsprotocol.types` (usado pelo pygls)."
> 
> 

#### Prompt 3: Conexão com o Compilador (Loop de Validação)

> "Vamos conectar os pontos. Preciso que você implemente a função `validate(ls, params)` e a registre nos eventos `TEXT_DOCUMENT_DID_OPEN` e `TEXT_DOCUMENT_DID_CHANGE`.
>
> **IMPORTANTE:** Siga as convenções de documentação do arquivo `@Compiler/coding_pattern.md`:
> - Docstring de módulo obrigatória com seções: Propósito, Componentes, Dependências, Exemplo
> - Type hints completos em todas as funções
> - Comentários inline apenas para lógica não-trivial
>
> **Lógica:**
> 1. Recupere o documento atual: `doc = ls.workspace.get_document(params.text_document.uri)`.
> 2. Obtenha o código fonte: `source = doc.source`.
> 3. Chame a função `synesis.lsp_adapter.validate_single_file(source, doc.uri, context)` que retorna um `ValidationResult`.
> 4. Itere sobre `result.errors + result.warnings + result.info` e converta cada `ValidationError` para `Diagnostic` usando os helpers criados anteriormente.
> 5. Publique os diagnósticos: `ls.publish_diagnostics(doc.uri, diagnostics)`.
> 6. Trate exceções genéricas (`try/except Exception`) para evitar que o servidor LSP caia (crash) se o compilador falhar. Em caso de erro, logue no console do LSP usando `ls.show_message_log()`.
> 7. Implemente debounce no servidor usando decorador do pygls (não no cliente TypeScript)."
>
> 

#### Prompt 4: Cliente VSCode (TypeScript)

> "Gere o código para o arquivo `extension.ts` de uma extensão VSCode que atuará como cliente para este servidor Python.
> **Requisitos:**
> 1. Use `vscode-languageclient/node`.
> 2. O servidor deve ser iniciado executando o comando: `python -m synesis.lsp`.
> 3. Configure `ServerOptions` e `ClientOptions` corretamente para arquivos do tipo `synesis`.
> 4. O código deve ser simples: ativar, iniciar cliente, desativar.
> 5. Não adicione configurações complexas de settings."
> 
> 

---

### 4. Garantia de Solidez

Para garantir que o código gerado seja sólido:

1. **Isolamento de Processo:** Ao usar `pygls` sobre STDIO, garantimos que se o Python travar, ele não derruba o VSCode. O `vscode-languageclient` gerencia o reinício automaticamente.
2. **Tratamento de Exceções:** No Prompt 3, a instrução para o bloco `try/except` ao redor da chamada do compilador é crítica. O LSP **nunca** deve morrer silenciosamente. Ele deve capturar o erro do compilador e, idealmente, mostrar um log ou um aviso na UI, mas manter a conexão viva.
3. **Assincronicidade:** O `pygls` roda em um loop de eventos. Se a compilação for muito pesada (bloqueante), no futuro poderemos movê-la para uma *Thread* ou *Processo* separado usando `loop.run_in_executor`, mantendo o servidor responsivo a comandos de cancelamento.
