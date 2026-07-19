"""
test_semantic_tokens.py - Comportamento desejado da colorização semântica

Complementar a test_semantic_tokens_golden.py: aqui fixamos o que DEVE
acontecer; lá protegemos contra regressões não previstas.
"""

from __future__ import annotations

import pytest

from synesis_lsp.semantic_tokens import (
    _NAMESPACE_KEYWORDS,
    TOKEN_TYPES,
    _token_type_for,
    compute_semantic_tokens,
    invalidate_cache,
)


def tokens_de(source: str, relations=None):
    """Decodifica o encoding delta em (linha_1based, tipo, modifier, texto)."""
    invalidate_cache()
    data = compute_semantic_tokens(source, "file:///t.synt", relations).data
    linhas = source.splitlines()
    out = []
    line = col = 0
    i = 0
    while i < len(data):
        d_line, d_col, length, ttype, tmod = data[i : i + 5]
        line += d_line
        col = d_col if d_line else col + d_col
        texto = linhas[line][col : col + length] if line < len(linhas) else ""
        out.append((line + 1, TOKEN_TYPES[ttype], tmod, texto))
        i += 5
    return out


def tipos_de(source, texto, relations=None):
    """Tipos atribuídos a um texto específico."""
    return [t[1] for t in tokens_de(source, relations) if t[3] == texto]


# ------------------------------------------------- bugs que motivaram a reescrita

def test_identifies_e_keyword():
    """
    Regressão do bug original: IDENTIFIES existia na gramática mas não em
    nenhuma lista de regex, e ficava sem cor.
    """
    src = "FIELD lattes_id TYPE TEXT\n    IDENTIFIES researcher\nEND FIELD\n"
    assert tipos_de(src, "IDENTIFIES") == ["keyword"]


def test_alvo_de_identifies_e_refers_to_sao_consistentes():
    """
    IDENTIFIES e REFERS TO formam o par de ligação multiprojeto; o rótulo de
    entidade em ambos deve ter a mesma cor (enumMember).
    """
    ident = tipos_de(
        "FIELD i TYPE TEXT\n    IDENTIFIES researcher\nEND FIELD\n", "researcher"
    )
    refers = tipos_de(
        "FIELD b TYPE TEXT\n    REFERS TO abstract ON BIBLIOGRAPHY\nEND FIELD\n", "abstract"
    )
    assert ident == refers == ["enumMember"]


def test_refers_to_e_keyword():
    src = "FIELD x TYPE TEXT\n    REFERS TO abstract\nEND FIELD\n"
    assert tipos_de(src, "REFERS") == ["keyword"]


def test_description_bloco_nao_colore_keywords_no_corpo():
    """
    Regressão do bug estrutural: dentro de DESCRIPTION o conteúdo é texto
    livre, mas o motor de regex coloria FIELD/TYPE como keywords.
    """
    src = (
        "FIELD x TYPE TEXT\n"
        "    DESCRIPTION\n"
        "    Aqui FIELD e TYPE sao texto comum\n"
        "    END DESCRIPTION\n"
        "END FIELD\n"
    )
    corpo = [t for t in tokens_de(src) if t[0] == 3]
    assert len(corpo) == 1
    assert corpo[0][1] == "string"
    assert "FIELD" in corpo[0][3]


def test_guidelines_nao_colore_keywords_no_corpo():
    src = (
        "FIELD x TYPE TEXT\n"
        "    GUIDELINES\n"
        "    FORMATO DE ORIGEM: use SCOPE e TYPE conforme o manual\n"
        "    END GUIDELINES\n"
        "END FIELD\n"
    )
    corpo = [t for t in tokens_de(src) if t[0] == 3]
    assert all(t[1] == "string" for t in corpo), corpo


def test_guidelines_fecha_escopo():
    """Após END GUIDELINES, keywords voltam a ser keywords."""
    src = (
        "FIELD x TYPE TEXT\n"
        "    GUIDELINES\n"
        "    texto livre\n"
        "    END GUIDELINES\n"
        "    SCOPE SOURCE\n"
        "END FIELD\n"
    )
    assert tipos_de(src, "SCOPE") == ["keyword"]


# ----------------------------------------------------- estrutura basica

def test_blocos_e_bibref():
    src = "SOURCE @silva2020\n    text: exemplo\nEND SOURCE\n"
    toks = tokens_de(src)
    assert ("keyword" in [t[1] for t in toks if t[3] == "SOURCE"])
    assert tipos_de(src, "@silva2020") == ["variable"]


def test_comentario_no_topo():
    """Comentários fora de bloco: a gramática usa %ignore, então o lexer não
    os emite — precisam ser recuperados do texto."""
    src = "# cabecalho do arquivo\nPROJECT Demo\nEND PROJECT\n"
    assert tipos_de(src, "# cabecalho do arquivo") == ["comment"]


def test_comentario_dentro_de_bloco():
    src = "SOURCE @x\n    # nota interna\n    text: a\nEND SOURCE\n"
    assert tipos_de(src, "# nota interna") == ["comment"]


def test_hash_dentro_de_guidelines_nao_e_comentario():
    """Em texto livre, '#' é literal (ex.: título Markdown), não comentário."""
    src = (
        "FIELD x TYPE TEXT\n"
        "    GUIDELINES\n"
        "    Use titulo Markdown: # Nome\n"
        "    END GUIDELINES\n"
        "END FIELD\n"
    )
    corpo = [t for t in tokens_de(src) if t[0] == 3]
    assert all(t[1] != "comment" for t in corpo), corpo


def test_namespace_para_keywords_de_projeto():
    src = 'PROJECT Demo\n    TEMPLATE "t.synt"\nEND PROJECT\n'
    assert tipos_de(src, "PROJECT")[0] == "namespace"
    assert tipos_de(src, "TEMPLATE") == ["namespace"]


def test_nome_de_campo_e_property():
    src = "ITEM @x\n    citation: texto qualquer\nEND ITEM\n"
    assert tipos_de(src, "citation") == ["property"]


def test_nome_de_campo_que_colide_com_keyword():
    """`code:`/`description:` são rótulos de campo, não keywords."""
    src = "ITEM @x\n    code: A1, B2\nEND ITEM\n"
    assert tipos_de(src, "code") == ["property"]


# ------------------------------------- cabeçalho de FIELD (TYPE colapsado)

def test_type_e_o_tipo_sao_keywords():
    """
    `FIELD x TYPE SCALE` colapsa em KW_FIELD + TEXT_LINE('x TYPE SCALE'):
    o lexer não separa TYPE nem o tipo. Devem ser coloridos como keyword.
    """
    src = "FIELD x TYPE SCALE\nEND FIELD\n"
    assert tipos_de(src, "TYPE") == ["keyword"]
    assert tipos_de(src, "SCALE") == ["keyword"]
    assert tipos_de(src, "x") == ["property"]


@pytest.mark.parametrize("tipo", ["TEXT", "MEMO", "ENUMERATED", "ORDERED", "TOPIC", "CHAIN"])
def test_todos_os_tipos_viram_keyword(tipo):
    src = f"FIELD campo TYPE {tipo}\nEND FIELD\n"
    assert tipos_de(src, tipo) == ["keyword"]


def test_props_de_field_na_mesma_linha():
    """Props após o tipo (`ARITY`) continuam coloridas."""
    src = "FIELD x TYPE CHAIN ARITY >= 2\nEND FIELD\n"
    assert tipos_de(src, "ARITY") == ["keyword"]
    assert tipos_de(src, "CHAIN") == ["keyword"]


def test_nome_de_field_igual_a_tipo_e_property():
    """`FIELD memo TYPE MEMO`: o nome `memo` é property, o tipo `MEMO` é keyword."""
    src = "FIELD memo TYPE MEMO\nEND FIELD\n"
    toks = tokens_de(src)
    memo_tokens = [t for t in toks if t[3] == "memo"]
    assert memo_tokens == [(1, "property", 0, "memo")]
    assert tipos_de(src, "MEMO") == ["keyword"]


@pytest.mark.parametrize(
    "nome", ["source_date", "item_id", "ontology_description", "type_of"]
)
def test_nome_de_field_que_comeca_com_keyword(nome):
    """
    Keywords de bloco (SOURCE, ITEM, ONTOLOGY, TYPE) não têm lookahead de
    fronteira, então o lexer parte `source_date` em KW_SOURCE + '_date'. O nome
    completo deve ser reconstruído como property, não a keyword-prefixo.
    """
    src = f"FIELD {nome} TYPE TEXT\nEND FIELD\n"
    toks = tokens_de(src)
    nome_tokens = [t for t in toks if t[3] == nome]
    assert nome_tokens == [(1, "property", 0, nome)], toks
    assert tipos_de(src, "TYPE") == ["keyword"]
    assert tipos_de(src, "TEXT") == ["keyword"]


# --------------------------------------- REFERS TO ... ON BIBLIOGRAPHY

def test_on_bibliography_sao_keywords():
    """No valor de REFERS TO, ON e BIBLIOGRAPHY são keywords; o alvo, não."""
    src = "FIELD b TYPE TEXT\n    REFERS TO abstract ON BIBLIOGRAPHY\nEND FIELD\n"
    assert tipos_de(src, "ON") == ["keyword"]
    assert tipos_de(src, "BIBLIOGRAPHY") == ["keyword"]
    assert tipos_de(src, "abstract") == ["enumMember"]


# --------------------------------- REQUIRED/OPTIONAL em SOURCE FIELDS

def test_required_com_on_bibliography():
    """
    `REQUIRED lattes_id ON BIBLIOGRAPHY`: o nome é property, ON/BIBLIOGRAPHY são
    keywords. Mesma classe do bug de REFERS TO, noutro construto.
    """
    src = (
        "SOURCE FIELDS\n"
        "    REQUIRED lattes_id ON BIBLIOGRAPHY\n"
        "END SOURCE FIELDS\n"
    )
    assert tipos_de(src, "lattes_id") == ["property"]
    assert tipos_de(src, "ON") == ["keyword"]
    assert tipos_de(src, "BIBLIOGRAPHY") == ["keyword"]


def test_lista_de_required_e_property():
    """Lista de nomes após REQUIRED/OPTIONAL é colorida como property."""
    src = (
        "SOURCE FIELDS\n"
        "    REQUIRED a, b, c\n"
        "    OPTIONAL d\n"
        "END SOURCE FIELDS\n"
    )
    assert tipos_de(src, "a, b, c") == ["property"]
    assert tipos_de(src, "d") == ["property"]


# ------------------------------- valor de campo que colide com keyword

def test_valor_de_memo_e_string():
    """
    `memo:` colide com KW_MEMO; o valor deve ser string, consistente com
    campos de texto não-colidentes (`note:`), não enumMember.
    """
    src = "ITEM @x\n    memo: uma anotacao\nEND ITEM\n"
    assert tipos_de(src, "uma anotacao") == ["string"]


def test_valor_de_memo_consistente_com_note():
    """memo (colide) e note (não colide) devem colorir o valor igual."""
    memo = tipos_de("ITEM @x\n    memo: texto\nEND ITEM\n", "texto")
    note = tipos_de("ITEM @x\n    note: texto\nEND ITEM\n", "texto")
    assert memo == note == ["string"]


# ------------------------------------------------------------- chains

def test_chain_decomposta():
    """Relações vêm do template, não da gramática: o lexer devolve o valor
    inteiro como um token opaco e o refino separa setas e relações."""
    src = "ITEM @x\n    chain: Trust -> INFLUENCES -> CCS_Support\nEND ITEM\n"
    toks = tokens_de(src)
    assert tipos_de(src, "->") == ["operator", "operator"]
    assert tipos_de(src, "INFLUENCES") == ["type"]
    assert ("Trust", "enumMember") in [(t[3], t[1]) for t in toks]


def test_chain_com_relacao_custom_do_template():
    src = "ITEM @x\n    chain: A -> APPLIES -> B\nEND ITEM\n"
    assert tipos_de(src, "APPLIES", frozenset({"APPLIES"})) == ["type"]


# ------------------------------------------------------------ robustez

@pytest.mark.parametrize(
    "nome,source",
    [
        ("vazio", ""),
        ("bloco nao fechado", "SOURCE @x\n    text: a"),
        ("lixo", "SOURCE @x\n    @@@ !!!\nEND SOURCE\n"),
        ("dedent inconsistente", "ITEM @x\n        a: 1\n    b: 2\nEND ITEM\n"),
    ],
)
def test_documento_invalido_nao_quebra(nome, source):
    invalidate_cache()
    result = compute_semantic_tokens(source, "file:///t.synt", None)
    assert isinstance(result.data, list)
    assert len(result.data) % 5 == 0


def test_cache_por_uri_nao_faz_thrashing():
    """Alternar entre arquivos deve manter ambos em cache."""
    invalidate_cache()
    a = "SOURCE @a\nEND SOURCE\n"
    b = "SOURCE @b\nEND SOURCE\n"
    r1 = compute_semantic_tokens(a, "file:///a.syn", None)
    compute_semantic_tokens(b, "file:///b.syn", None)
    r2 = compute_semantic_tokens(a, "file:///a.syn", None)
    assert r1 is r2  # mesma instância => veio do cache


def test_cache_invalida_quando_conteudo_muda():
    invalidate_cache()
    uri = "file:///x.syn"
    r1 = compute_semantic_tokens("SOURCE @a\nEND SOURCE\n", uri, None)
    r2 = compute_semantic_tokens("SOURCE @b\nEND SOURCE\n", uri, None)
    assert r1 is not r2


# --------------------------------------------------- contrato de propagação

def test_toda_keyword_da_gramatica_recebe_cor():
    """
    Invariante da propagação automática: qualquer terminal KW_* da gramática
    tem que receber algum tipo de token. Falha se alguém adicionar uma keyword
    nova e a colorização não a cobrir — que foi exatamente o bug do IDENTIFIES.
    """
    from synesis.parser.lexer import create_parser

    keywords = {t.name for t in create_parser().terminals if t.name.startswith("KW_")}
    assert keywords, "gramática sem terminais KW_* — mudança incompatível?"

    sem_cor = [kw for kw in keywords if _token_type_for(kw) is None]
    assert not sem_cor, f"keywords sem cor atribuída: {sorted(sem_cor)}"


def test_keyword_desconhecida_vira_keyword_por_fallback():
    """Uma keyword hipotética futura deve cair no fallback, não ficar sem cor."""
    assert _token_type_for("KW_ALGO_QUE_NAO_EXISTE_AINDA") is not None


def test_namespace_keywords_sao_subconjunto_da_gramatica():
    from synesis.parser.lexer import create_parser

    keywords = {t.name for t in create_parser().terminals if t.name.startswith("KW_")}
    assert _NAMESPACE_KEYWORDS <= keywords, (
        f"_NAMESPACE_KEYWORDS cita terminais inexistentes: "
        f"{sorted(_NAMESPACE_KEYWORDS - keywords)}"
    )
