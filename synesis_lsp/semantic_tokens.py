"""
semantic_tokens.py - Colorização semântica derivada da gramática

Propósito:
    Produz tokens semânticos a partir do fluxo de tokens do lexer do compilador
    (`synesis.lex_tokens`), em vez de reimplementar a sintaxe em regex.

    Consequência prática: construtos novos na gramática (keywords, modificadores)
    aparecem coloridos automaticamente, sem editar listas paralelas aqui. Foi a
    divergência entre essas listas e a gramática que deixou IDENTIFIES/REFERS TO
    sem cor e fez keywords serem coloridas dentro de blocos DESCRIPTION.

Mapeamento de tokens Synesis → LSP:
    Terminais KW_* de bloco/campo                      → Keyword (declaration)
    KW_PROJECT/TEMPLATE/INCLUDE/BIBLIOGRAPHY/ANNOTATIONS→ Namespace
    BIBREF, @bibref                                    → Variable
    FIELD_NAME, nome_campo:                            → Property
    TEXT_LINE, STRING (valores e texto livre)          → String
    CONCEPT_NAME, códigos ontológicos                  → EnumMember
    COMMENT                                            → Comment
    ->                                                 → Operator
    INFLUENCES, ENABLES, ... (relações do template)    → Type

Notas de implementação:
    - O lexer é contextual: dentro de DESCRIPTION/GUIDELINES o conteúdo já vem
      como TEXT_LINE, então keywords nunca são coloridas ali. Sem flags manuais.
    - Dois construtos exigem refino pós-lex, porque o lexer os devolve opacos:
      chains e @bibref. Ver `_refine_opaque_tokens`.
    - Encoding delta: [deltaLine, deltaStartChar, length, tokenType, tokenModifiers]
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Dict, List, Tuple

from lsprotocol.types import (
    SemanticTokenModifiers,
    SemanticTokens,
    SemanticTokensLegend,
    SemanticTokenTypes,
)
from synesis import LexToken, lex_tokens

logger = logging.getLogger(__name__)

# Tipos de tokens suportados
TOKEN_TYPES: List[str] = [
    SemanticTokenTypes.Keyword.value,     # 0: SOURCE, ITEM, END, ONTOLOGY
    SemanticTokenTypes.Variable.value,    # 1: @bibref
    SemanticTokenTypes.Property.value,    # 2: nome_campo:
    SemanticTokenTypes.String.value,      # 3: valor de campo / conteúdo GUIDELINES
    SemanticTokenTypes.EnumMember.value,  # 4: código ontológico (Trust, CCS_Support)
    SemanticTokenTypes.Namespace.value,   # 5: PROJECT, TEMPLATE, INCLUDE
    SemanticTokenTypes.Comment.value,     # 6: # comentário
    SemanticTokenTypes.Operator.value,    # 7: ->
    SemanticTokenTypes.Type.value,        # 8: relações de chain (INFLUENCES, ENABLES, ...)
]

TOKEN_MODIFIERS: List[str] = [
    SemanticTokenModifiers.Declaration.value,   # 0: para keywords de declaração
    SemanticTokenModifiers.Modification.value,  # 1: para conteúdo de GUIDELINES
]


def build_legend() -> SemanticTokensLegend:
    """Cria uma instância fresca do legend para evitar mutações acidentais."""
    return SemanticTokensLegend(
        token_types=TOKEN_TYPES,
        token_modifiers=TOKEN_MODIFIERS,
    )


LEGEND = build_legend()

# Índices dos tipos (ordem em TOKEN_TYPES)
_TK_KEYWORD = 0
_TK_VARIABLE = 1
_TK_PROPERTY = 2
_TK_STRING = 3
_TK_ENUM_MEMBER = 4  # códigos ontológicos
_TK_NAMESPACE = 5
_TK_COMMENT = 6
_TK_OPERATOR = 7
_TK_RELATION = 8     # relações de chain (INFLUENCES, ENABLES, ...)

# Modifier bitmask
_MOD_DECLARATION = 1 << 0   # bit 0
_MOD_MODIFICATION = 1 << 1  # bit 1: conteúdo GUIDELINES (texto livre itálico)

# Keywords que declaram estrutura de projeto, coloridas como namespace.
# (Demais KW_* já colorem como keyword pelo fallback em _token_type_for; só os
# tipos de include/estrutura recebem a cor de namespace.)
_NAMESPACE_KEYWORDS: frozenset[str] = frozenset({
    "KW_PROJECT", "KW_TEMPLATE", "KW_INCLUDE",
    "KW_BIBLIOGRAPHY", "KW_ANNOTATIONS", "KW_SHARED", "KW_DATASET",
})

# Terminais não-KW_* com colorização própria. Terminais ausentes deste mapa e
# que não sejam KW_* são ignorados (não recebem cor) — ver `_token_type_for`.
_TERMINAL_TYPES: Dict[str, int] = {
    "COMMENT": _TK_COMMENT,
    "BIBREF": _TK_VARIABLE,
    "STRING": _TK_STRING,
    "TEXT_LINE": _TK_STRING,
    "FIELD_NAME": _TK_PROPERTY,
    "CONCEPT_NAME": _TK_ENUM_MEMBER,
    "CODE_ELEMENT": _TK_ENUM_MEMBER,
    "CHAIN_ELEMENT": _TK_ENUM_MEMBER,
    "IDENTIFIER": _TK_ENUM_MEMBER,
    "NUMBER": _TK_STRING,
}

# Tokens estruturais do Indenter — não representam texto do usuário.
_CONTROL_TERMINALS: frozenset[str] = frozenset({"NEWLINE", "_INDENT", "_DEDENT"})

# Blocos cujo conteúdo é texto livre e recebe modifier de "modification"
# (renderizado em itálico pelos temas). O lexer já entrega o conteúdo como
# TEXT_LINE; este conjunto serve apenas para escolher o modifier.
_FREE_TEXT_BLOCKS: frozenset[str] = frozenset({"KW_GUIDELINES", "KW_DESCRIPTION"})

# Relações padrão usadas como fallback quando o template ainda não foi compilado
# (ex: documento aberto antes do LSP terminar loadProject).
_DEFAULT_RELATIONS: frozenset[str] = frozenset({
    "INFLUENCES", "ENABLES", "CONSTRAINS", "CONTESTED-BY", "RELATES-TO",
    "CAUSES", "PREVENTS", "REQUIRES", "EXCLUDES", "CORRELATES", "DEPENDS-ON",
})

_RE_ARROW = re.compile(r'->')
_RE_BIBREF = re.compile(r'@[\w.-]+')
# Rótulo de campo dentro de um TEXT_LINE colapsado (`citation: valor`).
# Só casa no início e sem espaços no nome, para não confundir com prosa que
# contenha ':' no meio (ex.: 'Passo 1: faça X' dentro de GUIDELINES).
_RE_FIELD_LABEL = re.compile(r'^([\w.-]+)\s*:')

# Cabeçalho de FIELD colapsado: `<nome> TYPE <TIPO>` volta como um único
# TEXT_LINE após KW_FIELD. `nome` é property; TYPE e o tipo são keywords.
# Os tipos vêm da gramática (KW_* de tipo), colados aqui para reconhecê-los
# dentro do TEXT_LINE onde o lexer não os separou.
_FIELD_TYPE_NAMES = (
    "CODE", "TEXT", "MEMO", "QUOTATION", "CHAIN", "DATE",
    "SCALE", "ENUMERATED", "ORDERED", "TOPIC",
)
_RE_FIELD_HEADER = re.compile(
    r'^([\w.-]+)(\s+)(TYPE)(\s+)(' + '|'.join(_FIELD_TYPE_NAMES) + r')\b',
    re.IGNORECASE,
)
# Keywords soltas dentro de um TEXT_LINE que o lexer não isolou. Usado no valor
# de REFERS TO (`abstract ON BIBLIOGRAPHY`), de ON DATASET
# (`campo ON DATASET "caminho"`) e de CONTEXT FROM DATASET (propriedade de
# FIELD), onde o alvo colapsa com o sufixo num único TEXT_LINE: o alvo é
# identificador; ON/FROM/BIBLIOGRAPHY/DATASET/CONTEXT são keywords.
_RE_TRAILING_KEYWORDS = re.compile(
    r'\b(ON|FROM|CONTEXT|BIBLIOGRAPHY|ANNOTATIONS|ONTOLOGY|DATASET)\b', re.IGNORECASE
)
# Comentário de linha inteira. A gramática declara `%ignore COMMENT`, então o
# lexer NUNCA emite esses tokens — precisam ser recuperados do texto.
_RE_COMMENT_LINE = re.compile(r'^(\s*)(#.*)$')


def _build_relation_re(relation_names: frozenset[str]) -> re.Pattern:
    """Compila regex para o conjunto de nomes de relação fornecido."""
    escaped = [re.escape(r) for r in sorted(relation_names, key=len, reverse=True)]
    return re.compile(r'\b(' + '|'.join(escaped) + r')\b')


# RawToken: (line_0based, col_0based, length, token_type_index, modifier_bitmask)
RawToken = Tuple[int, int, int, int, int]

# Cache por URI: cada documento aberto mantém sua própria entrada, evitando o
# thrashing de um cache global de entrada única quando o usuário alterna entre
# arquivos. Chave de conteúdo é digest estável (hash() do Python é salted por
# processo e não serve para comparação persistente).
_TOKENS_CACHE: Dict[str, Tuple[str, frozenset[str], SemanticTokens]] = {}


def _digest(source: str) -> str:
    return hashlib.blake2b(source.encode("utf-8"), digest_size=16).hexdigest()


def invalidate_cache(uri: str | None = None) -> None:
    """Descarta o cache de um documento (ou de todos, se uri for None)."""
    if uri is None:
        _TOKENS_CACHE.clear()
    else:
        _TOKENS_CACHE.pop(uri, None)


def compute_semantic_tokens(
    source: str,
    uri: str,
    relation_names: frozenset[str] | None = None,
) -> SemanticTokens:
    """
    Computa tokens semânticos para um arquivo Synesis.

    relation_names: conjunto de nomes de relação válidos extraídos do template
    (ex: {"INFLUENCES", "ENABLES", "CONSTRAINS"}). Se None, usa _DEFAULT_RELATIONS
    como fallback para cobrir o período entre abertura do documento e loadProject.
    """
    effective_relations = relation_names if relation_names is not None else _DEFAULT_RELATIONS
    digest = _digest(source)

    cached = _TOKENS_CACHE.get(uri)
    if cached is not None:
        cached_digest, cached_relations, cached_result = cached
        if cached_digest == digest and cached_relations == effective_relations:
            return cached_result

    re_relation = _build_relation_re(effective_relations)
    tokens = _extract_tokens(source, re_relation)
    result = SemanticTokens(data=_encode_deltas(tokens))
    _TOKENS_CACHE[uri] = (digest, effective_relations, result)
    return result


def _token_type_for(terminal: str) -> int | None:
    """
    Mapeia um terminal da gramática para um tipo de token LSP.

    Regra de fallback para KW_*: qualquer keyword nova na gramática já nasce
    colorida, sem edição deste módulo. É o que evita a divergência que motivou
    a reescrita — não substituir por uma lista explícita de keywords.
    """
    if terminal in _TERMINAL_TYPES:
        return _TERMINAL_TYPES[terminal]
    if terminal.startswith("KW_"):
        return _TK_NAMESPACE if terminal in _NAMESPACE_KEYWORDS else _TK_KEYWORD
    return None


def _closes_free_text(lex: List[LexToken], i: int) -> bool:
    """True se `lex[i]` é o KW_END de um `END GUIDELINES`/`END DESCRIPTION`."""
    nxt = lex[i + 1] if i + 1 < len(lex) else None
    return nxt is not None and nxt.type in _FREE_TEXT_BLOCKS and nxt.line == lex[i].line


def _extract_tokens(source: str, re_relation: re.Pattern) -> List[RawToken]:
    """Converte o fluxo de tokens do lexer em tokens semânticos posicionais."""
    tokens: List[RawToken] = []
    lex = [t for t in lex_tokens(source) if t.type not in _CONTROL_TERMINALS]

    # Modifier de texto livre: ativado ao entrar em GUIDELINES/DESCRIPTION em
    # forma de BLOCO e desativado no END correspondente. O lexer já garante que
    # o conteúdo vem como TEXT_LINE; isto só escolhe o modifier (itálico).
    free_text_depth = 0
    prev_kw: str | None = None
    skip_next = False

    for i, tok in enumerate(lex):
        if skip_next:
            skip_next = False
            prev_kw = tok.type
            continue

        terminal = tok.type
        nxt = lex[i + 1] if i + 1 < len(lex) else None

        # Blocos de texto livre: só a forma de BLOCO abre escopo.
        #   bloco : `DESCRIPTION\n  <texto>\nEND DESCRIPTION`
        #   campo : `description: valor` (mesma linha)
        # Distinguem-se porque na forma de bloco não há valor na mesma linha.
        if terminal in _FREE_TEXT_BLOCKS:
            inline_field = nxt is not None and nxt.line == tok.line
            if prev_kw == "KW_END":
                free_text_depth = max(0, free_text_depth - 1)
            elif not inline_field:
                free_text_depth += 1
                # A própria keyword abre o bloco: emitir e seguir
                tokens.append(
                    (tok.line - 1, tok.column - 1, len(tok.value),
                     _TK_KEYWORD, _MOD_DECLARATION)
                )
                prev_kw = terminal
                continue

        # Dentro de bloco de texto livre nada é código: o lexer ainda reconhece
        # keywords soltas na prosa (`FORMATO` vira KW_FORMAT + 'O'), mas o
        # conteúdo é literal. Emitir a linha inteira como texto, exceto o
        # `END <BLOCO>` que fecha o escopo.
        if free_text_depth > 0:
            if terminal == "KW_END" and _closes_free_text(lex, i):
                free_text_depth = max(0, free_text_depth - 1)
                tokens.append(
                    (tok.line - 1, tok.column - 1, len(tok.value),
                     _TK_KEYWORD, _MOD_DECLARATION)
                )
            elif terminal in _FREE_TEXT_BLOCKS and prev_kw == "KW_END":
                tokens.append(
                    (tok.line - 1, tok.column - 1, len(tok.value),
                     _TK_KEYWORD, _MOD_DECLARATION)
                )
            else:
                tokens.append(
                    (tok.line - 1, tok.column - 1, len(tok.value),
                     _TK_STRING, _MOD_MODIFICATION)
                )
            prev_kw = terminal
            continue

        ttype = _token_type_for(terminal)
        if ttype is None:
            prev_kw = terminal
            continue

        line = tok.line - 1      # LSP usa 0-based
        col = tok.column - 1
        length = len(tok.value)
        modifier = 0

        # Comentário fora de bloco chega como TEXT_LINE (o `%ignore COMMENT` da
        # gramática só vale dentro dos blocos). Colorir como comentário, não
        # como texto — senão o cabeçalho do arquivo perde a cor.
        if terminal == "TEXT_LINE" and free_text_depth == 0:
            m = _RE_COMMENT_LINE.match(tok.value)
            if m:
                tokens.append(
                    (line, col + len(m.group(1)), len(m.group(2)), _TK_COMMENT, 0)
                )
                prev_kw = terminal
                continue

        if ttype == _TK_KEYWORD:
            modifier = _MOD_DECLARATION
        elif terminal == "TEXT_LINE" and free_text_depth > 0:
            modifier = _MOD_MODIFICATION

        # Tokens opacos precisam de refino antes de virar um token único
        if _refine_opaque_tokens(
            tok, terminal, prev_kw, nxt, line, col, tokens, re_relation
        ):
            prev_kw = terminal
            continue

        # Nome de campo que COMEÇA com keyword (`source_date`, `item_id`): as
        # keywords de bloco não têm o lookahead de fronteira que as de tipo têm,
        # então o lexer parte o nome em KW_* + TEXT_LINE colado (mesma coluna).
        # Reconstruir o nome inteiro e tratar como cabeçalho de FIELD.
        if (
            ttype == _TK_KEYWORD
            and prev_kw == "KW_FIELD"
            and nxt is not None
            and nxt.type == "TEXT_LINE"
            and nxt.line == tok.line
            and nxt.column == tok.end_column  # colado, sem espaço
        ):
            nome_completo = tok.value + nxt.value
            m = _RE_FIELD_HEADER.match(nome_completo)
            if m:
                _emit_field_header(line, col, m, tokens)
                skip_next = True  # o TEXT_LINE colado já foi consumido acima
                prev_kw = terminal
                continue

        # Keyword usada como NOME DE CAMPO, colorida como property:
        #   - anotação: `memo:`, `code:` (seguida de ':')
        #   - declaração: `FIELD memo TYPE ...` (nome seguido de KW_TYPE)
        # O lexer emite KW_* porque o terminal casa, mas é rótulo, não comando.
        if ttype == _TK_KEYWORD and nxt is not None and nxt.line == tok.line:
            nome_de_campo = nxt.value.lstrip().startswith(":") or (
                prev_kw == "KW_FIELD" and nxt.type == "KW_TYPE"
            )
            if nome_de_campo:
                tokens.append((line, col, length, _TK_PROPERTY, 0))
                prev_kw = terminal
                continue

        tokens.append((line, col, length, ttype, modifier))
        prev_kw = terminal

    _append_comment_tokens(source, tokens)
    return tokens


def _append_comment_tokens(source: str, tokens: List[RawToken]) -> None:
    """
    Emite tokens de comentário varrendo o texto.

    NÃO REMOVER: a gramática declara `%ignore COMMENT`, portanto `lex_tokens()`
    nunca devolve comentários — não é uma duplicação do lexer, é a única fonte
    possível para eles.

    Linhas já cobertas por algum token do lexer são puladas: dentro de
    GUIDELINES/DESCRIPTION um '#' é texto literal, não comentário.
    """
    cobertas = {t[0] for t in tokens}
    for idx, linha in enumerate(source.splitlines()):
        if idx in cobertas:
            continue
        m = _RE_COMMENT_LINE.match(linha)
        if m:
            tokens.append((idx, len(m.group(1)), len(m.group(2)), _TK_COMMENT, 0))


def _refine_opaque_tokens(
    tok: LexToken,
    terminal: str,
    prev_kw: str | None,
    nxt: LexToken | None,
    line: int,
    col: int,
    tokens: List[RawToken],
    re_relation: re.Pattern,
) -> bool:
    """
    Decompõe tokens que o lexer devolve como uma unidade opaca.

    NÃO REMOVER sem verificar o lexer: dois construtos exigem isto porque o
    lexer contextual não os separa —

    1. Chains: `chain: A -> INFLUENCES -> B` volta como um único CONCEPT_NAME
       com todo o valor. As relações (INFLUENCES, ...) vêm do TEMPLATE, não da
       gramática, então o lexer não tem como reconhecê-las.
    2. @bibref: em `SOURCE @silva2020`, o `@silva2020` volta como TEXT_LINE, e
       não como BIBREF — o lexer contextual colapsa os dois. A AST tem o valor
       mas não a coluna, então a posição só é recuperável aqui.

    Retorna True se emitiu tokens (chamador deve pular a emissão padrão).
    """
    value = tok.value

    # Valor de campo vem com o ':' colado (`: Trust -> X`). O ':' pertence ao
    # rótulo, não ao valor: descartá-lo evita colori-lo como conteúdo.
    if terminal == "CONCEPT_NAME" and value.startswith(":"):
        offset = len(value) - len(value[1:].lstrip())
        value = value[1:].lstrip()
        col += offset
        if not value:
            return True

    # 1. Valor de chain/código: decompor setas, relações e códigos
    if terminal == "CONCEPT_NAME" and (
        _RE_ARROW.search(value) or re_relation.search(value)
    ):
        _tokenize_chain_value(line, col, value, tokens, re_relation)
        return True

    # 1b. Valor de campo cujo ':' foi removido acima. Ocorre quando o NOME do
    # campo colide com um KW_* (`memo:`, `code:`, `text:`): o lexer parte em
    # KW_* + CONCEPT_NAME(': valor'). O valor é string, como em qualquer campo
    # de texto não-colidente (`note:`, `tag:`) — não enumMember.
    if terminal == "CONCEPT_NAME" and value != tok.value:
        tokens.append((line, col, len(value), _TK_STRING, 0))
        return True

    # 2. @bibref colapsado em TEXT_LINE após SOURCE/ITEM
    if terminal == "TEXT_LINE" and prev_kw in {"KW_SOURCE", "KW_ITEM"}:
        m = _RE_BIBREF.search(value)
        if m:
            tokens.append(
                (line, col + m.start(), len(m.group(0)), _TK_VARIABLE, 0)
            )
            return True

    # 3. Cabeçalho de FIELD colapsado: `<nome> TYPE <TIPO> [props...]` após
    # KW_FIELD. O lexer engole a linha inteira em um TEXT_LINE; separar nome
    # (property), TYPE e o tipo (keywords), e deixar o restante (props como
    # `ARITY >= 2`) para o tratamento genérico de keywords soltas.
    if terminal == "TEXT_LINE" and prev_kw == "KW_FIELD":
        m = _RE_FIELD_HEADER.match(value)
        if m:
            _emit_field_header(line, col, m, tokens)
            return True

    # 4. Valor de REFERS TO: `<alvo> ON BIBLIOGRAPHY`. O alvo é identificador
    # (enumMember); ON/BIBLIOGRAPHY são keywords que o lexer não isolou.
    if terminal == "TEXT_LINE" and prev_kw == "KW_TO":
        _tokenize_with_trailing_keywords(line, col, value, tokens)
        return True

    # 4b. Lista de campos após REQUIRED/OPTIONAL/FORBIDDEN em SOURCE FIELDS.
    # `lattes_id ON BIBLIOGRAPHY` colapsa em TEXT_LINE: os nomes são property,
    # ON/BIBLIOGRAPHY são keywords.
    if terminal == "TEXT_LINE" and prev_kw in {
        "KW_REQUIRED", "KW_OPTIONAL", "KW_FORBIDDEN", "KW_BUNDLE",
    }:
        _tokenize_with_trailing_keywords(line, col, value, tokens, rest_type=_TK_PROPERTY)
        return True

    # 4c. Alvo de IDENTIFIES: `IDENTIFIES researcher`. É rótulo de entidade,
    # como o alvo de REFERS TO — enumMember, para os dois lados do par de
    # ligação multiprojeto ficarem consistentes.
    if terminal == "TEXT_LINE" and prev_kw == "KW_IDENTIFIES":
        alvo = value.strip()
        if alvo:
            offset = value.index(alvo)
            tokens.append((line, col + offset, len(alvo), _TK_ENUM_MEMBER, 0))
        return True

    # 5. `nome_campo: valor` colapsado em um único TEXT_LINE. Ocorre quando o
    # nome não colide com nenhum terminal KW_* (`citation:`, `note:`): o lexer
    # devolve a linha inteira. Separar rótulo (property) de valor (string).
    if terminal == "TEXT_LINE":
        m = _RE_FIELD_LABEL.match(value)
        if m:
            label = m.group(1)
            tokens.append((line, col, len(label), _TK_PROPERTY, 0))
            resto = value[m.end():]
            if resto.strip():
                offset = m.end() + (len(resto) - len(resto.lstrip()))
                tokens.append(
                    (line, col + offset, len(resto.strip()), _TK_STRING, 0)
                )
            return True

    return False


def _emit_field_header(
    line: int, col: int, m: re.Match, tokens: List[RawToken]
) -> None:
    """
    Emite os tokens de um cabeçalho de FIELD casado por _RE_FIELD_HEADER:
    nome (property), TYPE e o tipo (keywords), e props na mesma linha.
    """
    nome, sep1, kw_type, sep2, tipo = m.groups()
    c = col
    tokens.append((line, c, len(nome), _TK_PROPERTY, 0))
    c += len(nome) + len(sep1)
    tokens.append((line, c, len(kw_type), _TK_KEYWORD, _MOD_DECLARATION))
    c += len(kw_type) + len(sep2)
    tokens.append((line, c, len(tipo), _TK_KEYWORD, _MOD_DECLARATION))
    resto = m.string[m.end():]
    if resto.strip():
        _tokenize_field_props(line, col + m.end(), resto, tokens)


_RE_FIELD_PROP_KEYWORDS = re.compile(
    r'\b(ARITY|VALUES|FORMAT|RELATIONS|SCOPE|BUNDLE|CONTEXT|FROM)\b', re.IGNORECASE
)


def _tokenize_field_props(
    line: int, start_col: int, text: str, tokens: List[RawToken]
) -> None:
    """
    Colore props de FIELD que ficaram na mesma linha do cabeçalho
    (`... TYPE CHAIN ARITY >= 2`). Keywords de prop viram keyword; o resto fica
    sem cor (valores como `>= 2` não têm token próprio no restante da linha).
    """
    for m in _RE_FIELD_PROP_KEYWORDS.finditer(text):
        tokens.append(
            (line, start_col + m.start(), len(m.group(0)), _TK_KEYWORD, _MOD_DECLARATION)
        )


def _tokenize_with_trailing_keywords(
    line: int,
    start_col: int,
    text: str,
    tokens: List[RawToken],
    rest_type: int = _TK_ENUM_MEMBER,
) -> None:
    """
    Emite keywords soltas (ON, BIBLIOGRAPHY, ...) num TEXT_LINE, tratando o
    restante conforme `rest_type`.

    Usado em dois contextos com "resto" de tipo diferente:
      - valor de REFERS TO: alvo é identificador (enumMember, padrão)
      - lista de REQUIRED/OPTIONAL: nomes de campo (property)
    """
    pos = 0
    for m in _RE_TRAILING_KEYWORDS.finditer(text):
        antes = text[pos:m.start()].strip()
        if antes:
            offset = text.index(antes, pos)
            tokens.append((line, start_col + offset, len(antes), rest_type, 0))
        tokens.append(
            (line, start_col + m.start(), len(m.group(0)), _TK_KEYWORD, _MOD_DECLARATION)
        )
        pos = m.end()
    resto = text[pos:].strip()
    if resto:
        offset = text.index(resto, pos)
        tokens.append((line, start_col + offset, len(resto), rest_type, 0))


def _tokenize_chain_value(
    line_idx: int,
    start_col: int,
    text: str,
    tokens: List[RawToken],
    re_relation: re.Pattern,
) -> None:
    """Emite tokens de operator (->) e type (relações) e enumMember (códigos) para uma chain."""
    pos = 0
    while pos < len(text):
        arrow = _RE_ARROW.search(text, pos)
        relation = re_relation.search(text, pos)

        next_match = None
        if arrow and relation:
            next_match = arrow if arrow.start() <= relation.start() else relation
        elif arrow:
            next_match = arrow
        elif relation:
            next_match = relation

        if next_match is None:
            rest = text[pos:].strip()
            if rest:
                rest_offset = text.index(rest, pos)
                tokens.append(
                    (line_idx, start_col + rest_offset, len(rest), _TK_ENUM_MEMBER, 0)
                )
            break

        before = text[pos:next_match.start()].strip()
        if before:
            before_offset = text.index(before, pos)
            tokens.append(
                (line_idx, start_col + before_offset, len(before), _TK_ENUM_MEMBER, 0)
            )

        if next_match is arrow:
            tokens.append((line_idx, start_col + next_match.start(), 2, _TK_OPERATOR, 0))
        else:
            tokens.append((
                line_idx,
                start_col + next_match.start(),
                len(next_match.group(0)),
                _TK_RELATION,
                0,
            ))

        pos = next_match.end()


def _encode_deltas(tokens: List[RawToken]) -> List[int]:
    """
    Ordena tokens por posição e codifica em formato delta LSP.

    Formato: [deltaLine, deltaStartChar, length, tokenType, tokenModifiers]
    Cada token é relativo ao anterior.
    """
    if not tokens:
        return []

    tokens.sort(key=lambda t: (t[0], t[1]))

    data: List[int] = []
    prev_line = 0
    prev_col = 0

    for line, col, length, token_type, modifiers in tokens:
        delta_line = line - prev_line
        delta_col = col - prev_col if delta_line == 0 else col

        data.extend([delta_line, delta_col, length, token_type, modifiers])

        prev_line = line
        prev_col = col

    return data
