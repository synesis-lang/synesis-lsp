# 🧪 Guia de Testes da Extensão Synesis VSCode

Este guia mostra como executar e testar a extensão Synesis no VSCode.

## ✅ Status Atual

- ✅ LSP Server instalado (`synesis-lsp`)
- ✅ Código TypeScript compilado (`out/extension.js`)
- ✅ Configurações de debug criadas (`.vscode/launch.json`)
- ⚠️ Compilador Synesis precisa ser configurado

## 🚀 Método 1: Teste Rápido (Modo Debug)

### Passo 1: Adicionar Compilador ao PYTHONPATH

Como o compilador tem problema de instalação, vamos usar via PYTHONPATH:

```bash
# No terminal, configure a variável de ambiente
export PYTHONPATH="/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/Compiler:$PYTHONPATH"

# Verifique se funciona
python3 -c "import synesis; print('✅ Compilador acessível!')"
```

### Passo 2: Abrir Projeto no VSCode

```bash
cd "/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/LSP/vscode-extension"

# Abrir VSCode
code .
```

### Passo 3: Executar em Modo Debug

**No VSCode:**

1. **Pressione F5** (ou `Run → Start Debugging`)
2. Uma **nova janela do VSCode** será aberta (Extension Development Host)
3. Nessa nova janela, crie um arquivo de teste

### Passo 4: Criar Arquivo de Teste

Na janela de desenvolvimento, crie `teste.syn`:

```synesis
# Teste simples de validação
SOURCE @teste2023
    author: "João Silva"
    title: "Teste de Validação"
    year: 2023
END SOURCE
```

### Passo 5: Verificar Funcionamento

**Você deve ver:**

✅ **Syntax Highlighting**: Palavras-chave coloridas
✅ **Validação**: Erros/warnings aparecem sublinhados
✅ **Output**: `View → Output → Synesis LSP` mostra logs

**Se aparecer erro "synesis not found":**
- Feche a janela de desenvolvimento
- Configure PYTHONPATH globalmente
- Tente novamente

---

## 🔧 Método 2: Configurar PYTHONPATH Permanente

### Opção A: Configuração Global do VSCode

1. Abra Settings: `Cmd+,` (Mac) ou `Ctrl+,` (Windows/Linux)
2. Busque: `synesis.pythonPath`
3. Configure um script wrapper:

Crie arquivo `/tmp/python-synesis-wrapper.sh`:

```bash
#!/bin/bash
export PYTHONPATH="/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/Compiler:$PYTHONPATH"
exec python3 "$@"
```

Torne executável:
```bash
chmod +x /tmp/python-synesis-wrapper.sh
```

Configure em VSCode:
```json
{
  "synesis.pythonPath": "/tmp/python-synesis-wrapper.sh"
}
```

### Opção B: Configuração via .env

Crie arquivo `.env` no workspace:

```bash
PYTHONPATH=/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/Compiler
```

---

## 🐛 Método 3: Fixar Instalação do Compilador

Para resolver definitivamente o problema de instalação:

### Corrigir pyproject.toml do Compilador

Edite `/path/to/Compiler/pyproject.toml` e adicione:

```toml
[build-system]
requires = ["setuptools>=65.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["synesis"]
```

Depois reinstale:

```bash
cd Compiler
pip3 install -e .
```

---

## 📊 Verificação de Funcionalidades

### Checklist de Teste

Ao executar a extensão, verifique:

- [ ] **Syntax Highlighting**
  - `PROJECT`, `SOURCE`, etc. devem estar coloridos
  - Comentários `#` em cor diferente
  - Strings `"texto"` destacadas

- [ ] **Validação em Tempo Real**
  - Erros aparecem sublinhados
  - `View → Problems` (Cmd+Shift+M) lista erros

- [ ] **Output do LSP**
  - `View → Output → Synesis LSP` mostra logs
  - "Synesis Language Server iniciado com sucesso"

- [ ] **Auto-indentação**
  - Ao pressionar Enter após `PROJECT`, indenta automaticamente
  - `END PROJECT` dedenta

- [ ] **Bracket Matching**
  - Ao digitar `[`, fecha automaticamente com `]`

### Casos de Teste

#### Teste 1: Arquivo Válido
```synesis
SOURCE @silva2023
    author: "João Silva"
END SOURCE
```
**Esperado**: Sem erros

#### Teste 2: Erro de Sintaxe
```synesis
SOURCE @silva2023
    author: "João Silva"
# Falta END SOURCE
```
**Esperado**: Erro sublinhado

#### Teste 3: Campo Inválido
```synesis
SOURCE @silva2023
    campo_inexistente: "valor"
END SOURCE
```
**Esperado**: Warning ou erro

---

## 🔍 Debug e Troubleshooting

### Ver Logs do LSP

1. `View → Output`
2. Dropdown: Selecione "Synesis LSP"
3. Verifique mensagens de erro

### Habilitar Trace Verbose

Settings → `synesis.trace.server` → `"verbose"`

Veja comunicação completa LSP nos logs.

### Recarregar Extensão

Se fizer mudanças no código:

1. **Recompilar**: `npm run compile`
2. **Recarregar**: `Cmd+R` (Mac) ou `Ctrl+R` (Windows) na janela de desenvolvimento

### Testar LSP Manualmente

```bash
# Terminal 1: Iniciar servidor
export PYTHONPATH="/path/to/Compiler:$PYTHONPATH"
python3 -m synesis_lsp

# Terminal 2: Enviar mensagem LSP
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | nc localhost 3000
```

---

## 📦 Método 4: Criar Pacote .vsix

Para instalar permanentemente no VSCode:

```bash
# Criar pacote
npm run package

# Instalar
code --install-extension synesis-vscode-0.1.0.vsix
```

Depois disso, configure `synesis.pythonPath` nas settings globais.

---

## 🎯 Próximos Passos

Após validar que funciona:

1. **Teste com arquivos reais** do seu projeto
2. **Verifique performance** em arquivos grandes
3. **Teste todas as extensões**: `.syn`, `.synp`, `.synt`, `.syno`
4. **Valide mensagens de erro** são claras e úteis

---

## 💡 Dicas

- **Atalho F5**: Inicia debug rapidamente
- **Cmd+Shift+M**: Abre painel de problemas
- **Cmd+R**: Recarrega extensão sem fechar janela
- **Output Channel**: Sempre verifique logs em caso de problemas

---

## 🆘 Problemas Comuns

### "ModuleNotFoundError: No module named 'synesis'"

**Causa**: PYTHONPATH não configurado
**Solução**: Use Método 2 acima

### "Extension host terminated unexpectedly"

**Causa**: Erro no código TypeScript ou Python crashou
**Solução**: Verifique Output → Synesis LSP para stack trace

### Validação não funciona

**Causa**: LSP não iniciou corretamente
**Solução**:
1. Verifique Output
2. Teste `python3 -m synesis_lsp` manualmente
3. Configure `synesis.trace.server` para "verbose"

### Highlighting funciona mas validação não

**Causa**: Highlighting é via TextMate (não precisa de LSP), validação precisa
**Solução**: Problema está no LSP server, veja logs

---

**Boa sorte com os testes! 🚀**
