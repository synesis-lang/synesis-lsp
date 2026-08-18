"""
blocks.py - Retorna blocos SOURCE/ITEM com bibref e range estruturados

Propósito:
    Custom request synesis/getBlocks — substitui synesisParser.js na extensão.
    Fornece (kind, bibref, range) por bloco, sem string-parsing de labels no cliente.

Custom Request:
    synesis/getBlocks → lista de blocos SOURCE e ITEM com range LSP e bibref resolvido

Notas de implementação:
    - Reutiliza compile_string() (mesmo caminho de symbols.py)
    - Fallback regex para texto inválido (cursor em documento sendo editado)
    - bibref normalizado sem '@' (como coderService espera)
    - range em coordenadas 0-based (padrão LSP)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Fallback regex — use `regex` module (suporta \p{L}) se disponível, senão \w
try:
    import regex as _re_module
    _RE_SOURCE = _re_module.compile(r"^\s*SOURCE\s+@([\p{L}\p{N}._-]+)", _re_module.MULTILINE)
    _RE_ITEM = _re_module.compile(r"^\s*ITEM\s+@([\p{L}\p{N}._-]+)", _re_module.MULTILINE)
except ImportError:
    _RE_SOURCE = re.compile(r"^\s*SOURCE\s+@([\w._-]+)", re.MULTILINE)
    _RE_ITEM = re.compile(r"^\s*ITEM\s+@([\w._-]+)", re.MULTILINE)

# Delimitadores usados para achar o FIM real de um bloco (ver _find_block_end).
_RE_BLOCK_END = re.compile(r"^(\s*)END\s+(SOURCE|ITEM)\b", re.IGNORECASE)
_RE_BLOCK_START = re.compile(r"^(\s*)(SOURCE|ITEM)\s+@", re.IGNORECASE)


def _indent_width(line: str) -> int:
    """Largura da indentação de uma linha."""
    return len(line) - len(line.lstrip())


def _find_block_end(lines: list[str], start_0: int, kind: str) -> int:
    """
    Linha (0-based) do fim real do bloco iniciado em `start_0`.

    Antes, o fim era inferido por adjacência — "a linha anterior ao início do
    próximo bloco". Todo espaço entre o `END` verdadeiro e o próximo bloco
    (linhas em branco e, sobretudo, COMENTÁRIOS) era atribuído ao bloco
    anterior. Um `# Estudo de Silva 2020` escrito acima de `SOURCE @b2020`
    pertencia, para o getBlocks, ao ITEM de @a2019: o cursor ali resolvia o
    bibref errado, e o synesis-coder inseria o ITEM gerado depois do comentário
    da fonte seguinte.

    Comentários são `%ignore` na gramática, então não existem no AST nem no
    lexer — daí o fim precisar ser derivado do texto.

    A comparação de indentação não é cosmética: um valor de campo multilinha
    pode conter uma linha `END ITEM` indentada, e isso COMPILA. Sem exigir que o
    `END` esteja no nível da abertura, um bloco assim seria truncado no meio.

    Bloco sem `END` (estado normal durante a digitação) termina na linha
    anterior ao próximo bloco de mesmo nível.

    Args:
        lines: linhas do documento
        start_0: linha 0-based onde o bloco começa
        kind: "SOURCE" ou "ITEM"

    Returns:
        Índice 0-based da linha final do bloco.
    """
    if start_0 >= len(lines):
        return max(0, len(lines) - 1)

    base_indent = _indent_width(lines[start_0])
    target = kind.upper()

    for i in range(start_0 + 1, len(lines)):
        end_match = _RE_BLOCK_END.match(lines[i])
        if (
            end_match
            and end_match.group(2).upper() == target
            and len(end_match.group(1)) <= base_indent
        ):
            return i

        start_match = _RE_BLOCK_START.match(lines[i])
        if start_match and len(start_match.group(1)) <= base_indent:
            return max(start_0, i - 1)

    return max(0, len(lines) - 1)


def _end_position(lines: list[str], end_line_0: int) -> tuple[int, int]:
    """Converte a linha final em (line, character) do range LSP."""
    end_char = len(lines[end_line_0]) if 0 <= end_line_0 < len(lines) else 0
    return end_line_0, end_char


def get_blocks(file_path: str, workspace_root: Optional[Path] = None) -> dict:
    """
    Retorna blocos SOURCE e ITEM de um arquivo .syn com bibref e range.

    Args:
        file_path: Caminho para arquivo .syn
        workspace_root: Raiz do workspace para resolver paths relativos

    Returns:
        {
            "success": bool,
            "blocks": [
                {
                    "kind": "SOURCE" | "ITEM",
                    "bibref": str,           # sem '@'
                    "range": {
                        "start": {"line": int, "character": int},
                        "end":   {"line": int, "character": int}
                    }
                }
            ]
        }
    """
    if not file_path:
        return {"success": False, "error": "Parâmetro 'file' não fornecido"}

    path = Path(file_path)
    if not path.is_absolute() and workspace_root:
        path = workspace_root / path

    if not path.exists():
        return {"success": False, "error": f"Arquivo não encontrado: {file_path}"}

    try:
        source = path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"success": False, "error": f"Erro ao ler arquivo: {exc}"}

    blocks = _extract_blocks(source, str(path))
    return {"success": True, "blocks": blocks}


def _extract_blocks(source: str, uri: str) -> list[dict]:
    """
    Extrai blocos via compile_string; se o parse falhar, cai para o lexer.

    Escada de degradação (mais preciso → menos):
      1. AST      — documento compila
      2. lexer    — documento inválido (estado normal durante digitação)
      3. regex    — lexer indisponível/falhou; último recurso
    """
    try:
        import synesis
        nodes = synesis.compile_string(source, uri)
        return _blocks_from_nodes(nodes, source)
    except Exception:
        pass

    try:
        return _blocks_from_lex(source)
    except Exception:
        logger.debug("blocks: lexer falhou, usando fallback regex", exc_info=True)
        return _blocks_from_regex(source)


def _blocks_from_nodes(nodes: list, source: str) -> list[dict]:
    """Constrói lista de blocos a partir dos AST nodes do compilador."""
    from synesis.ast.nodes import ItemNode, SourceNode

    lines = source.splitlines()

    source_nodes = [n for n in nodes if isinstance(n, SourceNode)]
    item_nodes = [n for n in nodes if isinstance(n, ItemNode)]

    blocks: list[dict] = []

    for kind, node_list in (("SOURCE", source_nodes), ("ITEM", item_nodes)):
        for node in node_list:
            loc = node.location
            if loc is None:
                continue
            start_0 = max(0, loc.line - 1)
            start_col = max(0, loc.column - 1)
            end_0, end_char = _end_position(
                lines, _find_block_end(lines, start_0, kind)
            )
            blocks.append({
                "kind": kind,
                "bibref": _normalize_bibref(node.bibref),
                "range": {
                    "start": {"line": start_0, "character": start_col},
                    "end":   {"line": end_0,   "character": end_char},
                },
            })

    # Ordenar por linha de início
    blocks.sort(key=lambda b: b["range"]["start"]["line"])
    return blocks


_FREE_TEXT_BLOCKS = frozenset({"KW_GUIDELINES", "KW_DESCRIPTION"})
_CONTROL_TERMINALS = frozenset({"NEWLINE", "_INDENT", "_DEDENT"})


def _blocks_from_lex(source: str) -> list[dict]:
    """
    Extrai blocos via `synesis.lex_tokens` quando compile_string falha.

    Preferível ao fallback regex porque respeita a estrutura da linguagem: um
    `SOURCE @x` escrito na prosa de um bloco GUIDELINES/DESCRIPTION é texto, não
    declaração. O regex reporta esse bloco fantasma; aqui ele é ignorado.
    """
    from synesis import lex_tokens

    toks = [t for t in lex_tokens(source) if t.type not in _CONTROL_TERMINALS]
    lines = source.splitlines()

    # (line_idx_0based, kind, bibref)
    achados: list[tuple[int, str, str]] = []
    free_text_depth = 0

    for i, tok in enumerate(toks):
        prev = toks[i - 1].type if i else None
        nxt = toks[i + 1] if i + 1 < len(toks) else None

        # Só a forma de BLOCO abre texto livre (`GUIDELINES` sozinho na linha);
        # a forma de campo (`description: x`) tem valor na mesma linha.
        if tok.type in _FREE_TEXT_BLOCKS:
            if prev == "KW_END":
                free_text_depth = max(0, free_text_depth - 1)
            elif not (nxt is not None and nxt.line == tok.line):
                free_text_depth += 1
            continue

        if free_text_depth > 0:
            continue

        if tok.type not in ("KW_SOURCE", "KW_ITEM") or prev == "KW_END":
            continue

        # bibref vem no token seguinte, na mesma linha (o lexer colapsa em
        # TEXT_LINE em vez de BIBREF neste contexto)
        if nxt is None or nxt.line != tok.line:
            continue
        m = re.match(r"\s*@?([^\s]+)", nxt.value)
        if not m:
            continue

        achados.append((tok.line - 1, tok.type[3:], m.group(1)))

    return _build_ranges(achados, lines)


def _build_ranges(
    achados: list[tuple[int, str, str]], lines: list[str]
) -> list[dict]:
    """
    Converte (linha, kind, bibref) em blocos com range LSP 0-based.

    O fim vem de `_find_block_end` (o `END` real), não da adjacência do próximo
    bloco — mesma regra do caminho AST, para que a escada de degradação não mude
    de comportamento conforme o documento compile ou não.
    """
    achados.sort(key=lambda t: t[0])
    blocks: list[dict] = []

    for line_idx, kind, bibref in achados:
        end_line, end_char = _end_position(
            lines, _find_block_end(lines, line_idx, kind)
        )
        col = _indent_width(lines[line_idx]) if line_idx < len(lines) else 0
        blocks.append({
            "kind": kind,
            "bibref": _normalize_bibref(bibref),
            "range": {
                "start": {"line": line_idx, "character": col},
                "end":   {"line": end_line,  "character": end_char},
            },
        })

    return blocks


def _blocks_from_regex(source: str) -> list[dict]:
    """
    Fallback: extrai blocos via regex quando compile_string falha (doc inválido).

    Delega a construção dos ranges a `_build_ranges` — antes esta função tinha
    sua própria cópia da lógica, e corrigir o cálculo de fim exigiria fazê-lo
    duas vezes.
    """
    lines = source.splitlines()

    all_matches: list[tuple[int, str, str]] = []  # (line_idx, kind, bibref)
    for m in _RE_SOURCE.finditer(source):
        line_idx = source[: m.start()].count("\n")
        all_matches.append((line_idx, "SOURCE", m.group(1)))
    for m in _RE_ITEM.finditer(source):
        line_idx = source[: m.start()].count("\n")
        all_matches.append((line_idx, "ITEM", m.group(1)))

    return _build_ranges(all_matches, lines)


def _normalize_bibref(value: str) -> str:
    """Remove '@' e espaços — formato esperado pelo coderService."""
    return str(value).lstrip("@").strip()
