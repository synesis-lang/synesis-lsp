"""
test_symbols.py - Testes para document symbols (outline view)

Propósito:
    Validar extração de DocumentSymbol[] de arquivos Synesis.
    Testa SOURCE/ITEM/ONTOLOGY com hierarquia e fallback regex.
"""

from __future__ import annotations

from lsprotocol.types import SymbolKind

from synesis_lsp.symbols import compute_document_symbols, _extract_symbols_regex


def test_empty_source():
    """Fonte vazio retorna lista vazia."""
    result = compute_document_symbols("", "test.syn")
    assert result == []


def test_single_source():
    """SOURCE @bibref gera DocumentSymbol kind=Class."""
    source = "SOURCE @entrevista01\n    codigo: N/A\nEND SOURCE"
    result = compute_document_symbols(source, "test.syn")

    assert len(result) >= 1
    source_sym = result[0]
    assert source_sym.kind == SymbolKind.Class
    assert "@entrevista01" in source_sym.name
    assert "SOURCE" in source_sym.name


def test_source_with_items():
    """SOURCE com ITEMs gera hierarquia: SOURCE > ITEM children."""
    source = """SOURCE @entrevista01
    codigo: N/A
END SOURCE

ITEM @entrevista01
    ordem_1a: "texto citado aqui"
    ordem_2a: proposito
END ITEM

ITEM @entrevista01
    ordem_1a: "outro texto"
    ordem_2a: chamado_vocacao
END ITEM
"""
    result = compute_document_symbols(source, "test.syn")

    # Deve ter 1 SOURCE com 2 ITEM children
    source_symbols = [s for s in result if s.kind == SymbolKind.Class]
    assert len(source_symbols) == 1

    source_sym = source_symbols[0]
    assert source_sym.children is not None
    assert len(source_sym.children) == 2

    for child in source_sym.children:
        assert child.kind == SymbolKind.Method
        assert "ITEM" in child.name


def test_multiple_sources():
    """Múltiplos SOURCEs geram múltiplos symbols Class."""
    source = """SOURCE @entrevista01
    codigo: N/A
END SOURCE

SOURCE @entrevista02
    codigo: N/A
END SOURCE
"""
    result = compute_document_symbols(source, "test.syn")

    source_symbols = [s for s in result if s.kind == SymbolKind.Class]
    assert len(source_symbols) == 2


def test_ontology_block():
    """ONTOLOGY gera DocumentSymbol kind=Struct."""
    source = """ONTOLOGY proposito
    descricao: "Sentido de missao"
    ordem_3a: teste
END ONTOLOGY
"""
    result = compute_document_symbols(source, "test.syno")

    assert len(result) >= 1
    onto_sym = result[0]
    assert onto_sym.kind == SymbolKind.Struct
    assert "proposito" in onto_sym.name
    assert "ONTOLOGY" in onto_sym.name


def test_multiple_ontologies():
    """Múltiplos ONTOLOGYs geram múltiplos symbols Struct."""
    source = """ONTOLOGY dons_do_espirito
    descricao: "Capacitacoes do Espirito"
END ONTOLOGY

ONTOLOGY maravilhamento
    descricao: "Experiencia de admiracao"
END ONTOLOGY

ONTOLOGY milagres
    descricao: "Intervencao divina"
END ONTOLOGY
"""
    result = compute_document_symbols(source, "test.syno")

    struct_symbols = [s for s in result if s.kind == SymbolKind.Struct]
    assert len(struct_symbols) == 3

    names = [s.name for s in struct_symbols]
    assert any("dons_do_espirito" in n for n in names)
    assert any("maravilhamento" in n for n in names)
    assert any("milagres" in n for n in names)


def test_mixed_syn_file():
    """Arquivo .syn com SOURCE + ITEMs gera hierarquia correta."""
    source = """SOURCE @entrevista01
    codigo: N/A
END SOURCE

ITEM @entrevista01
    ordem_1a: "texto aqui"
    ordem_2a: proposito
END ITEM

SOURCE @entrevista02
    codigo: N/A
END SOURCE

ITEM @entrevista02
    ordem_1a: "outro texto"
    ordem_2a: chamado_vocacao
END ITEM
"""
    result = compute_document_symbols(source, "test.syn")

    source_symbols = [s for s in result if s.kind == SymbolKind.Class]
    assert len(source_symbols) == 2

    # Cada source deve ter 1 item child
    for s in source_symbols:
        assert s.children is not None
        assert len(s.children) == 1


def test_range_is_0_based():
    """Range deve usar posições 0-based (convertidas de 1-based)."""
    source = "SOURCE @entrevista01\n    codigo: N/A\nEND SOURCE"
    result = compute_document_symbols(source, "test.syn")

    assert len(result) >= 1
    sym = result[0]
    # SOURCE está na linha 1 (1-based) → linha 0 (0-based)
    assert sym.range.start.line == 0
    assert sym.range.start.character == 0


def test_item_on_line_5():
    """ITEM na linha 5 do fonte gera range com line=4 (0-based)."""
    source = """SOURCE @entrevista01
    codigo: N/A
END SOURCE

ITEM @entrevista01
    ordem_1a: "texto"
END ITEM
"""
    result = compute_document_symbols(source, "test.syn")

    source_sym = [s for s in result if s.kind == SymbolKind.Class][0]
    assert source_sym.children is not None
    assert len(source_sym.children) == 1

    item_sym = source_sym.children[0]
    # ITEM na linha 5 (1-based) → line=4 (0-based)
    assert item_sym.range.start.line == 4


def test_syntax_error_returns_regex_fallback():
    """Erro de sintaxe usa fallback regex em vez de crashar."""
    source = "SOURCE sem_arroba\n    codigo: N/A\nEND SOURCE"
    # compile_string deve falhar, fallback regex deve funcionar
    result = compute_document_symbols(source, "test.syn")
    # Não deve crashar — pode retornar vazio ou regex results
    assert isinstance(result, list)


def test_regex_fallback_source():
    """Fallback regex extrai SOURCEs."""
    source = "SOURCE @entrevista01\n    codigo: N/A\nEND SOURCE"
    result = _extract_symbols_regex(source)

    source_syms = [s for s in result if s.kind == SymbolKind.Class]
    assert len(source_syms) >= 1
    assert "@entrevista01" in source_syms[0].name


def test_regex_fallback_ontology():
    """Fallback regex extrai ONTOLOGYs."""
    source = "ONTOLOGY proposito\n    descricao: texto\nEND ONTOLOGY"
    result = _extract_symbols_regex(source)

    struct_syms = [s for s in result if s.kind == SymbolKind.Struct]
    assert len(struct_syms) >= 1
    assert "proposito" in struct_syms[0].name
