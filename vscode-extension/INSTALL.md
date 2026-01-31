# Guia de Instalação Rápida - Synesis VSCode Extension

## 🚀 Instalação Completa (5 minutos)

### Passo 1: Instalar Python 3.10+

```bash
# Verificar versão do Python
python3 --version
# Deve mostrar 3.10 ou superior
```

Se não tiver Python 3.10+, instale de [python.org](https://www.python.org/downloads/)

### Passo 2: Instalar Compilador Synesis

```bash
cd /caminho/para/0_Synesis/Compiler
pip3 install -e .

# Verificar instalação
python3 -c "import synesis; print('Compilador instalado!')"
```

### Passo 3: Instalar LSP Server

```bash
cd /caminho/para/0_Synesis/LSP
pip3 install -e .

# Verificar instalação
python3 -m synesis_lsp --help
```

### Passo 4: Instalar Extensão VSCode

#### Opção A: Desenvolvimento/Teste

```bash
cd /caminho/para/0_Synesis/LSP/vscode-extension

# Instalar dependências Node.js
npm install

# Compilar TypeScript → JavaScript
npm run compile

# Abrir VSCode neste diretório
code .

# Pressionar F5 para abrir janela de desenvolvimento
```

#### Opção B: Instalação Permanente

```bash
cd /caminho/para/0_Synesis/LSP/vscode-extension

# Instalar dependências
npm install

# Criar pacote .vsix
npm run package

# Instalar no VSCode
code --install-extension synesis-vscode-0.1.0.vsix
```

### Passo 5: Configurar (Opcional)

Se Python não está em PATH padrão, configure em VSCode:

1. `File → Preferences → Settings`
2. Busque "synesis"
3. Configure `Synesis: Python Path` com caminho completo:
   ```
   /usr/local/bin/python3
   ```

### Passo 6: Testar

1. Crie arquivo `teste.syn`:
   ```synesis
   SOURCE @teste2023
       author: João Silva
   END SOURCE
   ```

2. Abra no VSCode
3. Veja syntax highlighting e validação em tempo real!

## ✅ Verificação de Instalação

Execute cada comando e verifique se funciona:

```bash
# 1. Python instalado?
python3 --version

# 2. Compilador instalado?
python3 -c "import synesis; print('OK')"

# 3. LSP instalado?
python3 -m synesis_lsp --help

# 4. Extension compilada?
ls vscode-extension/out/extension.js
```

Se todos passarem, está pronto! 🎉

## 🐛 Problemas Comuns

### "ModuleNotFoundError: No module named 'synesis'"

**Solução**: Reinstale o compilador
```bash
cd Compiler
pip3 install -e .
```

### "ModuleNotFoundError: No module named 'synesis_lsp'"

**Solução**: Reinstale o LSP
```bash
cd LSP
pip3 install -e .
```

### "npm: command not found"

**Solução**: Instale Node.js de [nodejs.org](https://nodejs.org/)

### Extensão não aparece no VSCode

**Solução**: Verifique se compilou corretamente
```bash
cd vscode-extension
npm run compile
ls out/  # Deve mostrar extension.js
```

### LSP não inicia no VSCode

1. Verifique Output: `View → Output → Synesis LSP`
2. Procure mensagens de erro
3. Configure `synesis.pythonPath` nas settings

## 📚 Próximos Passos

1. Leia [README.md](README.md) para funcionalidades completas
2. Veja [exemplos](../../Compiler/examples/) de arquivos Synesis
3. Configure workspace com template e bibliografia
4. Comece a escrever código Synesis com validação em tempo real!

## 💡 Dicas

- **Debug**: Habilite `"synesis.trace.server": "verbose"` para ver comunicação LSP
- **Performance**: Desabilite validação em arquivos >1000 linhas
- **Workspace**: Organize projeto com estrutura recomendada:
  ```
  meu-projeto/
  ├── projeto.synp
  ├── bibliometrics.synt
  ├── bibliometrics.bib
  ├── bibliometrics.syno
  └── bibliometrics.syn
  ```
  Regra: pode haver varios `.synt`, mas o **unico** valido e o definido no `.synp`.

---

**Problemas persistentes?** Abra issue em [GitHub Issues](https://github.com/synesis-project/synesis-lsp/issues)
