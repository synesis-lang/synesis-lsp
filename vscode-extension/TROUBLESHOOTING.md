# Troubleshooting - Synesis Language Server

**Guia completo de resolução de problemas para a extensão Synesis VSCode**

---

## 🔴 Erro: "ModuleNotFoundError: No module named 'synesis'"

### Sintoma

```
ModuleNotFoundError: No module named 'synesis'
ImportError: Pacote 'synesis' não encontrado. Instale o compilador primeiro
Server process exited with code 1
```

### Causa

O compilador Synesis não está instalado no ambiente Python que o VSCode está usando.

### Solução

#### Passo 1: Instalar o Compilador

```bash
# Navegue até o diretório do compilador
cd /caminho/para/0_Synesis/Compiler

# Instale em modo editável
pip install -e .

# OU, se usar Python 3 explicitamente
python3 -m pip install -e .
```

#### Passo 2: Verificar Instalação

```bash
# Teste se o módulo está acessível
python3 -c "from synesis.lsp_adapter import validate_single_file; print('✅ OK')"
```

**Saída esperada**: `✅ OK`

#### Passo 3: Verificar Pacotes Instalados

```bash
python3 -m pip list | grep synesis
```

**Saída esperada**:
```
synesis         0.1.0    /caminho/para/Compiler
synesis-lsp     0.1.0    /caminho/para/LSP
```

#### Passo 4: Recarregar VSCode

1. Pressione `Ctrl+Shift+P` (Mac: `Cmd+Shift+P`)
2. Digite: `Developer: Reload Window`
3. Pressione Enter

---

## 🔴 Erro: "Multiple top-level packages discovered in a flat-layout"

### Sintoma

```
error: Multiple top-level packages discovered in a flat-layout:
['out_dir', 'synesis', 'davi_pesquisa', 'bibliometrics']
```

### Causa

O arquivo `pyproject.toml` do compilador está incompleto ou mal configurado.

### Solução

Verifique se o arquivo `Compiler/pyproject.toml` contém:

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "synesis"
version = "0.1.0"
description = "Synesis compiler for qualitative research corpora"
requires-python = ">=3.10"
dependencies = [
    "lark >= 1.1",
    "bibtexparser >= 1.4",
    "click >= 8.0",
]

[project.optional-dependencies]
dev = [
    "pytest >= 7.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["synesis*"]
exclude = ["out_dir*", "davi_pesquisa*", "bibliometrics*", "examples*"]
```

**Pontos críticos**:
- `[build-system]` deve estar presente
- `[tool.setuptools.packages.find]` deve excluir diretórios não-pacote

Depois de corrigir, reinstale:

```bash
cd Compiler
pip uninstall synesis  # Remove instalação antiga
pip install -e .       # Reinstala
```

---

## 🔴 Erro: "Server crashed 5 times in the last 3 minutes"

### Sintoma

```
The Synesis Language Server server crashed 5 times in the last 3 minutes.
The server will not be restarted.
```

### Causa

O servidor LSP está falhando repetidamente devido a erro de importação ou configuração.

### Solução

#### Passo 1: Verificar Output do LSP

1. Abra `View → Output` (ou `Ctrl+Shift+U`)
2. Selecione "Synesis LSP" no dropdown
3. Procure pela primeira mensagem de erro (ignore repetições)

#### Passo 2: Verificar Python Path

Verifique qual Python o VSCode está usando:

```bash
which python3
# OU
which python
```

Configure o caminho correto em `settings.json`:

```json
{
  "synesis.pythonPath": "/caminho/completo/para/python3"
}
```

**Exemplos comuns**:
- macOS Homebrew: `/opt/homebrew/bin/python3`
- macOS Framework: `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`
- Linux: `/usr/bin/python3`
- Windows: `C:\\Python312\\python.exe`

#### Passo 3: Testar Manualmente

```bash
# Teste o servidor diretamente
python3 -m synesis_lsp

# Deve mostrar logs do pygls sem erros
# Pressione Ctrl+C para sair
```

#### Passo 4: Reinstalar LSP

```bash
cd /caminho/para/LSP
pip uninstall synesis-lsp
pip install -e .
```

#### Passo 5: Limpar Cache e Recarregar

1. Feche todas as janelas do VSCode
2. Delete cache do VSCode (opcional):
   ```bash
   # macOS/Linux
   rm -rf ~/.vscode/extensions/synesis-*

   # Windows
   # Delete: %USERPROFILE%\.vscode\extensions\synesis-*
   ```
3. Reabra VSCode

---

## 🟡 Warning: Validação não está funcionando

### Sintoma

- Arquivos `.syn` abrem sem erros
- Mas não aparecem diagnósticos (sublinhados vermelhos/amarelos)
- Nenhuma mensagem de erro no Output

### Diagnóstico

#### 1. Verificar se extensão está ativa

```bash
# No terminal integrado do VSCode
code --list-extensions | grep synesis
```

**Saída esperada**: Nome da extensão Synesis

#### 2. Verificar configuração

Abra `Settings` → procure por "synesis":

```json
{
  "synesis.validation.enabled": true,  // Deve estar true
  "synesis.trace.server": "verbose"    // Ative para debug
}
```

#### 3. Verificar associação de arquivos

Abra um arquivo `.syn` e verifique o canto inferior direito do VSCode. Deve mostrar "Synesis" como linguagem.

Se mostrar "Plain Text", clique e selecione "Synesis" manualmente.

#### 4. Forçar revalidação

1. Abra arquivo `.syn`
2. Faça uma edição (adicione espaço, delete)
3. Salve (`Ctrl+S`)

---

## 🟡 Validação muito lenta

### Sintoma

Editor trava ou fica lento ao digitar em arquivos grandes.

### Solução

#### Opção 1: Desabilitar validação automática

```json
{
  "synesis.validation.enabled": false
}
```

Valide manualmente via CLI quando necessário:

```bash
synesis check arquivo.syn
```

#### Opção 2: Aumentar debounce (futuro)

Atualmente o debounce está fixo em 300ms. Em futuras versões, será configurável:

```json
{
  "synesis.validation.debounceMs": 1000  // Aguarda 1s após parar de digitar
}
```

---

## 🟡 Diagnósticos incorretos ou desatualizados

### Sintoma

LSP reporta erro que não existe, ou não detecta erro óbvio.

### Diagnóstico

O LSP usa 100% do compilador Synesis. Se o diagnóstico está errado, pode ser:

1. **Bug no compilador**: Teste com CLI
   ```bash
   synesis check arquivo.syn
   ```

2. **Cache desatualizado**: Recarregue janela
   - `Ctrl+Shift+P` → `Reload Window`

3. **Contexto incompleto**: LSP não encontrou template/bibliografia
   - Verifique Output do LSP para warnings sobre contexto

### Solução

Se CLI também reporta incorreto:
- O bug está no compilador
- Reporte em: [GitHub Issues - Synesis Compiler]

Se CLI está correto mas LSP está errado:
- O bug está no adaptador LSP
- Reporte em: [GitHub Issues - Synesis LSP]

---

## 🔵 Debug Avançado

### Habilitar Logs Completos

```json
{
  "synesis.trace.server": "verbose"
}
```

Recarregue janela e verifique `View → Output → Synesis LSP`.

### Logs Importantes

**Inicialização bem-sucedida**:
```
Synesis Language Server iniciado com sucesso
Registered "textDocument/didOpen" with options "None"
Registered "textDocument/didChange" with options "None"
```

**Validação executando**:
```
Validando arquivo: file:///caminho/para/arquivo.syn
Contexto descoberto: template=..., bibliografia=...
Validação concluída: X erros, Y warnings
```

### Testar Importações Python

Crie script de teste:

```python
#!/usr/bin/env python3
"""test_lsp.py - Script de diagnóstico LSP"""

print("1. Testando importações...")
try:
    from synesis.lsp_adapter import validate_single_file, ValidationContext
    print("   ✅ synesis.lsp_adapter")
except ImportError as e:
    print(f"   ❌ synesis.lsp_adapter: {e}")
    exit(1)

try:
    from pygls.server import LanguageServer
    print("   ✅ pygls")
except ImportError as e:
    print(f"   ❌ pygls: {e}")
    exit(1)

try:
    from synesis_lsp.server import main
    print("   ✅ synesis_lsp.server")
except ImportError as e:
    print(f"   ❌ synesis_lsp.server: {e}")
    exit(1)

print("\n2. Testando validação básica...")
source = """SOURCE @test2024
    author: Test Author
END SOURCE"""

result = validate_single_file(source, "test://test.syn", None)
print(f"   ✅ Validação OK: {len(result.errors)} erros, {len(result.warnings)} warnings")

print("\n✅ TODOS OS TESTES PASSARAM!")
```

Execute:

```bash
python3 test_lsp.py
```

### Testar Servidor Manualmente

```bash
# Iniciar servidor em modo stdio
python3 -m synesis_lsp

# Enviar mensagem de inicialização (JSON-RPC)
# Ctrl+C para sair
```

---

## 🛠️ Reinstalação Completa

Se nada funcionar, reinstale do zero:

```bash
# 1. Desinstalar tudo
pip uninstall synesis synesis-lsp -y

# 2. Limpar cache
rm -rf ~/.cache/pip
rm -rf ~/.vscode/extensions/synesis-*

# 3. Reinstalar compilador
cd /caminho/para/0_Synesis/Compiler
pip install -e .

# 4. Reinstalar LSP
cd ../LSP
pip install -e .

# 5. Verificar
python3 -m pip list | grep synesis

# 6. Testar importações
python3 -c "from synesis.lsp_adapter import validate_single_file; print('OK')"

# 7. Reabrir VSCode
# Feche TODAS as janelas e reabra
```

---

## 📞 Suporte

Se o problema persistir após seguir este guia:

1. **Colete informações**:
   ```bash
   # Versões
   python3 --version
   code --version
   pip list | grep -E "(synesis|lark|pygls)"

   # Logs
   # Copie Output do VSCode: View → Output → Synesis LSP
   ```

2. **Reporte Issue**:
   - [GitHub Issues - Synesis LSP](https://github.com/synesis-project/synesis-lsp/issues)
   - Inclua: SO, versão Python, logs completos, arquivo `.syn` de teste

3. **Discussões**:
   - [GitHub Discussions](https://github.com/synesis-project/synesis-lsp/discussions)
   - Para dúvidas gerais de uso

---

## ✅ Checklist de Diagnóstico Rápido

Antes de reportar problemas, verifique:

- [ ] Python 3.10+ instalado: `python3 --version`
- [ ] Compilador instalado: `pip list | grep synesis`
- [ ] LSP instalado: `pip list | grep synesis-lsp`
- [ ] Importação OK: `python3 -c "from synesis.lsp_adapter import validate_single_file"`
- [ ] Extensão instalada: `code --list-extensions | grep synesis`
- [ ] Arquivo `.syn` associado à linguagem "Synesis" (canto inferior direito)
- [ ] Validação habilitada: Settings → `synesis.validation.enabled`
- [ ] Janela recarregada: `Ctrl+Shift+P` → `Reload Window`
- [ ] Logs verificados: `View → Output → Synesis LSP`

---

**Última atualização**: 2026-01-03
**Versão**: 0.1.0
