# Interfaces e Contratos - Synesis LSP

Documento de referencia para os contratos entre o compilador Synesis e o servidor LSP.
Qualquer mudanca nestas interfaces requer atualizacao em `converters.py`.

## 1. Compilador -> LSP (Tipos de Entrada)

### ValidationResult

Agregador retornado por `validate_single_file()`. Contem listas separadas por severidade.

```python
# synesis/ast/results.py
@dataclass
class ValidationResult:
    errors: List[ValidationError]    # Severidade ERROR
    warnings: List[ValidationError]  # Severidade WARNING
    info: List[ValidationError]      # Severidade INFO
```

### ValidationError

Cada erro individual retornado pelo compilador.

```python
# synesis/ast/results.py
@dataclass
class ValidationError:
    location: SourceLocation   # Posicao no codigo-fonte
    severity: ErrorSeverity    # ERROR | WARNING | INFO
    message: str               # Mensagem interna

    def to_diagnostic(self) -> str:
        """Retorna mensagem pedagogica para o usuario."""
```

### SourceLocation

Posicao no codigo-fonte. **Coordenadas 1-based** (primeira linha = 1).

```python
# synesis/ast/nodes.py
@dataclass
class SourceLocation:
    file: str    # Caminho ou URI do arquivo
    line: int    # Linha (1-based)
    column: int  # Coluna (1-based)
```

### ErrorSeverity

Enum de severidades do compilador.

```python
# synesis/ast/results.py
class ErrorSeverity(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
```

## 2. LSP (Tipos de Saida)

### Mapeamento de Severidade

| Compilador (`ErrorSeverity`) | LSP (`DiagnosticSeverity`) | Valor |
|------------------------------|----------------------------|-------|
| `ERROR`                      | `Error`                    | 1     |
| `WARNING`                    | `Warning`                  | 2     |
| `INFO`                       | `Information`              | 3     |

### Conversao de Coordenadas

```
Synesis (1-based)  ->  LSP (0-based)
line=1, column=1   ->  line=0, character=0
line=5, column=10  ->  line=4, character=9
```

Formula:
```
lsp_line = synesis_line - 1
lsp_character = synesis_column - 1
```

### Diagnostic (saida)

```python
Diagnostic(
    range=Range(
        start=Position(line=lsp_line, character=lsp_char),
        end=Position(line=lsp_line, character=lsp_char + 1),
    ),
    severity=convert_severity(error.severity),
    source="synesis",
    message=error.to_diagnostic(),
)
```

## 3. Interface do Adaptador (lsp_adapter)

### validate_single_file

Funcao principal que o LSP invoca para validar um arquivo.

```python
# synesis/lsp_adapter.py
def validate_single_file(
    source: str,
    file_uri: str,
    context: Optional[ValidationContext] = None,
) -> ValidationResult:
```

**Parametros:**
- `source`: Conteudo do arquivo como string (texto cru do editor)
- `file_uri`: URI do arquivo (`file:///caminho/arquivo.syn`)
- `context`: Contexto opcional. Se `None`, o adaptador descobre automaticamente.

**Retorno:** `ValidationResult` com erros, warnings e info.

### ValidationContext

Contexto para validacao enriquecida.

```python
# synesis/lsp_adapter.py
@dataclass
class ValidationContext:
    template: Optional[TemplateNode] = None
    bibliography: Optional[Dict[str, BibEntry]] = None
    ontology_index: Optional[Dict[str, OntologyNode]] = None
```

### Funcoes auxiliares do adaptador

```python
_find_workspace_root(file_uri: str) -> Optional[Path]
_discover_context(file_uri: str) -> ValidationContext
_invalidate_cache(workspace_root: Path) -> None
```

## 4. Regras de Consistencia

1. **Erros sintaticos**: Sempre reportados (independem de contexto)
2. **Erros semanticos**: Reportados apenas quando `context.template` esta disponivel
3. **Bibrefs**: Validados apenas quando `context.bibliography` esta disponivel
4. **Codigos**: Sempre geram WARNING se nao encontrados em `ontology_index`
5. **Sem `.synp`**: LSP faz apenas validacao sintatica + palavras-chave

## 5. Checklist para Mudancas

Ao alterar interfaces no compilador:

- [ ] Atualizar `ValidationError` ou `ValidationResult` -> atualizar `converters.py`
- [ ] Alterar `SourceLocation` -> verificar `convert_location()` em `converters.py`
- [ ] Novo `ErrorSeverity` -> adicionar em `convert_severity()` em `converters.py`
- [ ] Mudanca em `validate_single_file()` -> verificar `server.py:validate_document()`
- [ ] Atualizar este documento (`INTERFACES.md`)
