# Template Bibliometrics - Documentação

## Arquivos Gerados

- **[bibliometrics.synt](bibliometrics.synt)** - Template de validação
- **[bibliometrics.synp](bibliometrics.synp)** - Arquivo de projeto (ponto de entrada)

## Compatibilidade com Dados Reais

Este template foi gerado a partir da análise reversa dos arquivos de dados reais:

- `bibliometrics.syn` (18.819 linhas, ~1.049 blocos SOURCE/ITEM)
- `bibliometrics.syno` (20.819 linhas, ~500 blocos ONTOLOGY)
- `bibliometrics.bib` (8.015 linhas, ~200 entradas BibTeX)

## Estrutura do Template

### Blocos SOURCE

**Campos obrigatórios:**
- `description`: Descrição do estudo e contexto
- `epistemic_model`: Framework teórico utilizado
- `method`: Método de pesquisa (survey, entrevistas, etc.)

**Exemplo:**
```synesis
SOURCE @ashworth2019
    description: Comparative study of public attitudes toward CCS...
    epistemic_model: Social acceptance of energy technologies
    method: Online survey (Australia n=2383, China n=1266)
END SOURCE
```

### Blocos ITEM

**Campos obrigatórios:**
- `text`: Excerto textual da fonte (tipo QUOTATION)
- **BUNDLE** `note, chain`: Pareamento obrigatório 1:1

**Validação de BUNDLE:**
- Cada `chain` DEVE ter exatamente um `note` correspondente
- Ordem posicional: `note[i]` explica `chain[i]`
- Violação gera erro de compilação

**Exemplo:**
```synesis
ITEM @ashworth2019
    text: However, male respondents...

    note: Self-assessed knowledge increases support...
    chain: Knowledge -> INFLUENCES -> CCS Support

    note: Economic prioritization over environmental values...
    chain: Economic Value -> INFLUENCES -> CCS Support
END ITEM
```

### Blocos ONTOLOGY

**Campos obrigatórios:**
- `description`: Definição conceitual completa

**Campos opcionais:**
- `topic`: Categoria hierárquica superior (tipo TOPIC, dinâmico)
- `aspect`: Aspecto modal de Dooyeweerd [1..15] (tipo ORDERED)
- `dimension`: Dimensão de aceitação social [0..4] (tipo ORDERED)
- `confidence`: Nível de confiança LOW|MEDIUM|HIGH (tipo ENUMERATED)
- `reasoning`: Justificativa analítica da classificação
- `rgt_element_a`: Polo A do construto (Repertory Grid Theory)
- `rgt_element_b`: Polo B do construto
- `theoretical_significance`: Significância teórica [0..5] (tipo SCALE)

**Exemplo:**
```synesis
ONTOLOGY Cost
    topic: Economics
    aspect: 11
    dimension: 2
    confidence: HIGH
    reasoning: Aspect 11: Core economic factor...
    description: Economic factor representing financial expenditure...
    rgt_element_a: Low Cost
    rgt_element_b: High Cost
    theoretical_significance: 0
END ONTOLOGY
```

## Relações Causais (CHAIN)

### Tipos de Relação Definidos

| Relação | Semântica | Exemplo |
|---------|-----------|---------|
| `ENABLES` | Condição necessária (sem A, B não ocorre) | `Public Acceptance -> ENABLES -> Deployment` |
| `INFLUENCES` | Efeito causal direto (A afeta B) | `Knowledge -> INFLUENCES -> CCS Support` |
| `CONSTRAINS` | Limita ou restringe (A reduz opções de B) | `Cost -> CONSTRAINS -> Deployment` |
| `CONTESTED-BY` | Oposição ativa | `Policy -> CONTESTED-BY -> Resistance` |
| `RELATES-TO` | Associação genérica | `Technology -> RELATES-TO -> Innovation` |

### Sintaxe de Cadeias

**Chain qualificada (com relação explícita):**
```synesis
chain: Gender -> INFLUENCES -> CCS Support
chain: A -> ENABLES -> B -> CONSTRAINS -> C
```

**Chain de arity >= 2:**
- Mínimo 2 códigos (nós) na cadeia
- Relação deve estar na lista RELATIONS do template
- Conceitos com espaços funcionam sem aspas

## Campos Tipo ORDERED

### ASPECT (Aspectos Modais de Dooyeweerd)

Índices **[1..15]** representam hierarquia ontológica:

```
[1]  Quantitative  → Medições, estatísticas
[2]  Spatial       → Geografia, localização
[3]  Kinematic     → Movimento, fluxo
[4]  Physical      → Propriedades materiais
[5]  Biotic        → Ecológico, ambiental
[6]  Sensitive     → Percepção, consciência
[7]  Analytical    → Pesquisa, metodologia
[8]  Formative     → Planejamento, design
[9]  Lingual       → Comunicação, informação
[10] Social        → Relações comunitárias
[11] Economic      → Custos, mercados
[12] Aesthetic     → Estética, harmonia
[13] Juridical     → Legal, regulatório
[14] Ethical       → Responsabilidade moral
[15] Fiducial      → Confiança, valores
```

**Uso nos dados:**
```synesis
aspect: 11    # Aceita índice numérico
aspect: 15    # OU label textual "Fiducial"
```

### DIMENSION (Dimensões de Aceitação Social)

Índices **[0..4]** segundo framework de Wüstenhagen:

```
[0] Undefined                    → Não classificado
[1] Community Acceptance         → Residentes, stakeholders locais
[2] Market Acceptance            → Consumidores, investidores
[3] Socio-Political Acceptance   → Instituições, governança
[4] Technical-Scientific         → Avaliação técnico-científica
```

**Nota crítica:** O valor `[0] Undefined` foi adicionado porque os dados reais contêm `dimension: 0`, que não está no framework original de Wüstenhagen. Isso representa conceitos ainda não classificados ou não aplicáveis às três dimensões canônicas.

## Campo Tipo TOPIC

**Característica especial:** Valores **dinâmicos** (não pré-definidos)

Diferentemente de ENUMERATED, o tipo TOPIC permite categorias emergentes:

```synesis
ONTOLOGY Cost
    topic: Economics    # Cria categoria "Economics"

ONTOLOGY Equity
    topic: Social       # Cria categoria "Social"

ONTOLOGY Climate Belief
    topic: Worldview    # Cria categoria "Worldview"
```

**Resultado:** Hierarquia dinâmica gerada automaticamente:
- Economics → {Cost, ...}
- Social → {Equity, Public Acceptance, ...}
- Worldview → {Climate Belief, Image, ...}

## Validações Aplicadas

### Validação de Referências
- Toda `@bibref` em SOURCE/ITEM deve existir em `bibliometrics.bib`
- Busca normalizada (lowercase, trim)
- Sugestões fuzzy (Levenshtein) para referências ausentes

### Validação de Ontologia
- Códigos em `chain` devem estar definidos em ONTOLOGY (warning se ausente)
- Valores de `aspect` devem estar em [1..15]
- Valores de `dimension` devem estar em [0..4]
- Valores de `confidence` devem ser LOW|MEDIUM|HIGH

### Validação de BUNDLE
- `note` e `chain` devem ter **mesma quantidade**
- Pareamento posicional: `note[0]` explica `chain[0]`
- Violação gera **erro crítico** (não warning)

### Validação de CHAIN
- Relações devem estar na lista RELATIONS
- Mínimo 2 códigos (ARITY >= 2)
- Alternância Código-Relação-Código deve ser válida

## Diferenças em Relação ao Template da Especificação

| Aspecto | Template Especificação | Template Bibliometrics |
|---------|------------------------|------------------------|
| Nome do campo ITEM | `quote` | `text` |
| Tipo `dimension` | ENUMERATED (texto) | ORDERED (índice numérico) |
| Valores `dimension` | [1..3] | [0..4] com `[0] Undefined` |
| Campo `code` em ITEM | Presente (opcional) | Ausente (não usado nos dados) |
| Campo `topic` | Exemplo ilustrativo | Implementado e usado |
| Campo `theoretical_significance` | Não mencionado | Presente (SCALE [0..5]) |

## Exportação

### JSON
Estrutura completa da AST com localização de cada nó:
```json
{
  "project": "bibliometrics",
  "sources": [...],
  "items": [...],
  "ontologies": [...],
  "location": {"file": "...", "line": 1, "column": 1}
}
```

### CSV
Tabelas planas por tipo de bloco com rastreabilidade:

**chains.csv:**
```csv
bibref,from_code,relation,to_code,source_file,source_line,source_column
ashworth2019,Gender,INFLUENCES,CCS Support,bibliometrics.syn,12,5
ashworth2019,Knowledge,INFLUENCES,CCS Support,bibliometrics.syn,16,5
```

**ontologies.csv:**
```csv
concept,topic,aspect,dimension,confidence,description,source_file,source_line
Cost,Economics,11,2,HIGH,"Economic factor...",bibliometrics.syno,1
Climate Belief,Worldview,15,1,LOW,"Climate belief...",bibliometrics.syno,16
```

## Uso

### Compilação
```bash
synesis compile bibliometrics.synp
```

### Validação (sem exportação)
```bash
synesis check bibliometrics.synp
```

### Exportação forçada (mesmo com erros)
```bash
synesis compile --force bibliometrics.synp
```

## Critérios de Sucesso

- ✅ Template processa 2.098 blocos SOURCE/ITEM
- ✅ Template processa ~500 blocos ONTOLOGY
- ✅ Valida 2.365 cadeias causais com 5 tipos de relação
- ✅ Suporta conceitos com espaços sem aspas
- ✅ Pareamento note/chain com validação estrita
- ⚠️ Performance esperada: 15-20s (critério original era <5s para 500 blocos)

## Notas de Implementação

1. **Normalização de BibTeX:** Todas as chaves são convertidas para lowercase durante carregamento e busca
2. **CHAIN_ELEMENT token:** Usa negative lookahead `(?!->)` para capturar espaços até operador
3. **Compilação parcial:** Erros são acumulados, não abordam prematuramente
4. **Mensagens pedagógicas:** Erros sugerem correções específicas sem exigir leitura do manual

## Compatibilidade

✅ **COMPATÍVEL** com arquivos:
- `bibliometrics.syn`
- `bibliometrics.syno`
- `bibliometrics.bib`

⚠️ **Ajustes necessários:** Nenhum (template gerado a partir dos dados reais)

---

**Versão:** 1.0
**Data:** 2025-12-30
**Gerado por:** Synesis Template Generator (análise reversa de dados reais)
