"""
server.py - Servidor LSP principal para Synesis usando pygls

Propósito:
    Servidor Language Server Protocol que fornece validação em tempo real
    para arquivos Synesis (.syn, .synp, .synt, .syno) em editores compatíveis.

Componentes principais:
    - SynesisLanguageServer: Servidor principal com pygls
    - validate_document: Função de validação usando lsp_adapter
    - Event handlers: did_open, did_change, did_close

Dependências críticas:
    - pygls: Framework LSP
    - synesis.lsp_adapter: Interface com compilador
    - synesis_lsp.converters: Conversão de tipos

Exemplo de uso:
    python -m synesis_lsp.server

Notas de implementação:
    - Comunica via STDIO (entrada/saída padrão)
    - Validação imediata em did_change (sem debounce)
    - Cache de contexto (template/bibliografia) por workspace
    - Tratamento robusto de exceções (nunca crasha)
    - Validação pode ser desabilitada via synesis.validation.enabled

Gerado conforme: Especificação Synesis v1.1 + ADR-002 LSP
"""

from __future__ import annotations

import logging
import sys
from importlib import metadata
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from lsprotocol.types import (
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    WORKSPACE_DID_CHANGE_CONFIGURATION,
    WORKSPACE_DID_CHANGE_WATCHED_FILES,
    DidChangeConfigurationParams,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    DidChangeWatchedFilesParams,
    FileChangeType,
    FileEvent,
    FileSystemWatcher,
    WatchKind,
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    SemanticTokensParams,
    TEXT_DOCUMENT_DOCUMENT_SYMBOL,
    DocumentSymbolParams,
    TEXT_DOCUMENT_HOVER,
    HoverParams,
    TEXT_DOCUMENT_INLAY_HINT,
    InlayHintParams,
    TEXT_DOCUMENT_DEFINITION,
    DefinitionParams,
    TEXT_DOCUMENT_COMPLETION,
    CompletionParams,
    CompletionOptions,
    TEXT_DOCUMENT_SIGNATURE_HELP,
    SignatureHelpParams,
    SignatureHelpOptions,
    TEXT_DOCUMENT_RENAME,
    RenameParams,
    TEXT_DOCUMENT_PREPARE_RENAME,
    PrepareRenameParams,
    TEXT_DOCUMENT_REFERENCES,
    ReferenceParams,
    TEXT_DOCUMENT_CODE_ACTION,
    CodeActionParams,
)
from pygls.server import LanguageServer

# Importa do compilador e converters locais
try:
    from synesis.lsp_adapter import (
        ValidationContext,
        validate_single_file,
        _find_workspace_root,
        _discover_context,
        _invalidate_cache,
    )
except ImportError as e:
    raise ImportError(
        "Pacote 'synesis' não encontrado. "
        "Instale o compilador primeiro: cd ../Compiler && pip install -e ."
    ) from e

from synesis_lsp.cache import WorkspaceCache
from synesis_lsp.converters import build_diagnostics, enrich_error_message
from synesis_lsp.semantic_tokens import build_legend, compute_semantic_tokens
from synesis_lsp.symbols import compute_document_symbols
from synesis_lsp.hover import compute_hover
from synesis_lsp.explorer_requests import get_references, get_codes, get_relations
from synesis_lsp.inlay_hints import compute_inlay_hints
from synesis_lsp.definition import compute_definition
from synesis_lsp.completion import compute_completions
from synesis_lsp.graph import get_relation_graph
from synesis_lsp.signature_help import compute_signature_help
from synesis_lsp.rename import prepare_rename, compute_rename
from synesis_lsp.template_diagnostics import build_template_diagnostics
from synesis_lsp.ontology_topics import get_ontology_topics
from synesis_lsp.ontology_annotations import get_ontology_annotations
from synesis_lsp.abstract_viewer import get_abstract
from synesis_lsp.references import compute_references
from synesis_lsp.code_actions import compute_code_actions
from synesis_lsp.workspace_diagnostics import compute_workspace_diagnostics, validate_workspace_file

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
_startup_logged = False


class SynesisLanguageServer(LanguageServer):
    """
    Servidor LSP especializado para Synesis.

    Attributes:
        workspace_documents: Mapeamento de workspace_root -> set de URIs abertos
                            Usado para revalidar documentos após mudanças em .synp/.synt/.bib
        validation_enabled: Flag de controle para habilitar/desabilitar validação em tempo real

    Nota sobre Cache:
        - O cache de ValidationContext é gerenciado pelo módulo lsp_adapter
        - O cache do lsp_adapter valida automaticamente mtimes dos arquivos
        - Este servidor apenas rastreia documentos abertos e invalida o cache
          quando arquivos de contexto (.synp/.synt/.bib) são modificados
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace_documents: dict[str, set[str]] = {}
        self.validation_enabled: bool = True  # Habilitado por padrão
        self.workspace_cache: WorkspaceCache = WorkspaceCache()


# Instância global do servidor
server = SynesisLanguageServer("synesis-lsp", "v0.10.4")


def _resolve_workspace_root(ls: SynesisLanguageServer, params) -> Optional[str]:
    """
    Resolve o workspace root a partir dos parâmetros ou documentos abertos.

    Estratégia:
        1. Se params é dict com 'workspaceRoot', usa diretamente
        2. Se params é lista com primeiro elemento dict com 'workspaceRoot', usa esse
        3. Senão, tenta extrair do primeiro documento aberto via _find_workspace_root
    """
    # Tenta extrair de params
    if isinstance(params, dict):
        if "workspaceRoot" in params:
            return params["workspaceRoot"]
        if "rootUri" in params:
            return params["rootUri"]
        if "rootPath" in params:
            return params["rootPath"]
    if isinstance(params, list) and len(params) > 0:
        first = params[0]
        if isinstance(first, dict):
            if "workspaceRoot" in first:
                return first["workspaceRoot"]
            if "rootUri" in first:
                return first["rootUri"]
            if "rootPath" in first:
                return first["rootPath"]

    # Fallback: usa primeiro documento aberto
    for workspace_key, doc_uris in ls.workspace_documents.items():
        if doc_uris:
            return workspace_key

    # Último recurso: tenta workspace folders do LSP
    if ls.workspace and hasattr(ls.workspace, "folders"):
        folders = ls.workspace.folders
        if folders:
            first_folder = next(iter(folders.values()), None)
            if first_folder:
                return first_folder.uri

    return None


def _normalize_workspace_path(workspace_root) -> Optional[Path]:
    """
    Normaliza workspace_root para Path, aceitando path ou file URI.

    Mantém o caminho sem resolve() para evitar dependência do filesystem.
    """
    if not workspace_root:
        return None

    if isinstance(workspace_root, Path):
        return workspace_root

    if not isinstance(workspace_root, str):
        return None

    if workspace_root.startswith("file://"):
        parsed = urlparse(workspace_root)
        path_str = unquote(parsed.path or "")

        # UNC paths: file://server/share/path -> //server/share/path
        if parsed.netloc:
            path_str = f"//{parsed.netloc}{path_str}"

        # Windows drive: /d:/path -> d:/path
        if len(path_str) >= 3 and path_str[0] == "/" and path_str[2] == ":":
            path_str = path_str[1:]

        return Path(path_str)

    return Path(workspace_root)


def _workspace_key(workspace_root) -> Optional[str]:
    """Normaliza workspace_root para chave consistente do cache."""
    path = _normalize_workspace_path(workspace_root)
    if not path:
        return None

    key = path.as_posix()
    if sys.platform.startswith("win"):
        key = key.lower()
    return key


@server.command("synesis/loadProject")
def load_project(ls: SynesisLanguageServer, params) -> dict:
    """
    Compila projeto completo e armazena resultado em cache.

    Retorna estatísticas do projeto (não o JSON completo de ~21MB).
    O resultado fica em cache para servir custom requests subsequentes.
    """
    try:
        workspace_root = _resolve_workspace_root(ls, params)
        if not workspace_root:
            return {"success": False, "error": "Workspace não encontrado"}

        workspace_path = _normalize_workspace_path(workspace_root)
        if not workspace_path:
            return {"success": False, "error": "Workspace inválido"}

        # Buscar .synp no workspace
        synp_files = []
        if workspace_path.suffix.lower() == ".synp":
            synp_files = [workspace_path]
        else:
            if workspace_path.is_file():
                workspace_path = workspace_path.parent
            synp_files = sorted(workspace_path.glob("**/*.synp"))
        if not synp_files:
            return {"success": False, "error": "Nenhum arquivo .synp encontrado"}

        logger.info(f"Compilando projeto: {synp_files[0]}")

        # Compilar via disco (~3.7s)
        from synesis.compiler import SynesisCompiler

        compiler = SynesisCompiler(synp_files[0])
        result = compiler.compile()

        # Cachear resultado
        ws_key = _workspace_key(workspace_path)
        if not ws_key:
            return {"success": False, "error": "Workspace inválido"}
        ls.workspace_cache.put(ws_key, result, workspace_path)

        # Retornar estatísticas (leve)
        return {
            "success": True,
            "stats": {
                "source_count": result.stats.source_count,
                "item_count": result.stats.item_count,
                "ontology_count": result.stats.ontology_count,
                "code_count": result.stats.code_count,
                "chain_count": result.stats.chain_count,
                "triple_count": result.stats.triple_count,
            },
            "has_errors": result.has_errors(),
            "has_warnings": result.has_warnings(),
        }
    except ImportError:
        return {"success": False, "error": "Compilador synesis não encontrado"}
    except Exception as e:
        # Trata SynesisSyntaxError e outros erros
        # Usa error_handler para mensagem pedagógica enriquecida
        location = getattr(e, "location", None)
        enriched_msg = enrich_error_message(
            e,
            source=None,  # Não temos source aqui (compilação de projeto)
            filename=str(synp_files[0]) if "synp_files" in dir() else None,
        )
        error_dict = {"success": False, "error": enriched_msg}
        if location:
            error_dict["location"] = {
                "file": str(location.file),
                "line": location.line,
                "column": location.column,
            }
        logger.error(f"loadProject falhou: {e}", exc_info=True)
        return error_dict


@server.command("synesis/getProjectStats")
def get_project_stats(ls: SynesisLanguageServer, params) -> dict:
    """
    Retorna estatísticas do projeto compilado a partir do cache.

    Requer que synesis/loadProject tenha sido chamado antes.
    """
    workspace_root = _resolve_workspace_root(ls, params)
    if not workspace_root:
        return {"success": False, "error": "Workspace não encontrado"}

    workspace_key = _workspace_key(workspace_root)
    if not workspace_key:
        return {"success": False, "error": "Workspace inválido"}

    cached = ls.workspace_cache.get(workspace_key)
    if not cached:
        return {
            "success": False,
            "error": "Projeto não carregado. Chame synesis/loadProject primeiro.",
        }

    stats = cached.result.stats
    return {
        "success": True,
        "stats": {
            "source_count": stats.source_count,
            "item_count": stats.item_count,
            "ontology_count": stats.ontology_count,
            "code_count": stats.code_count,
            "chain_count": stats.chain_count,
            "triple_count": stats.triple_count,
        },
    }


@server.feature(
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    build_legend(),
)
def semantic_tokens_full(
    ls: SynesisLanguageServer, params: SemanticTokensParams
) -> SemanticTokens:
    """
    Retorna tokens semânticos para colorização baseada no AST.

    Usa análise do texto-fonte (~0ms) para extrair tokens.
    """
    uri = params.text_document.uri
    doc = ls.workspace.get_document(uri)
    return compute_semantic_tokens(doc.source, uri)


@server.feature(TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(
    ls: SynesisLanguageServer, params: DocumentSymbolParams
) -> list:
    """
    Retorna document symbols para outline/breadcrumb do editor.

    Usa compile_string (~3-69ms) para extrair blocos SOURCE, ITEM, ONTOLOGY.
    """
    uri = params.text_document.uri
    doc = ls.workspace.get_document(uri)
    return compute_document_symbols(doc.source, uri)


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: SynesisLanguageServer, params: HoverParams):
    """
    Retorna informação contextual ao passar o mouse.

    @bibref → bibliografia, campo: → template, código → ontologia.
    Depende do workspace_cache; retorna None se cache vazio.
    """
    uri = params.text_document.uri
    doc = ls.workspace.get_document(uri)

    cached_result = _get_cached_for_uri(ls, uri)

    return compute_hover(doc.source, params.position, cached_result)


@server.feature(TEXT_DOCUMENT_INLAY_HINT)
def inlay_hint(ls: SynesisLanguageServer, params: InlayHintParams):
    """
    Retorna inlay hints com (Autor, Ano) após cada @bibref.

    Depende do workspace_cache; retorna [] se cache vazio.
    """
    uri = params.text_document.uri
    doc = ls.workspace.get_document(uri)

    cached_result = _get_cached_for_uri(ls, uri)

    return compute_inlay_hints(doc.source, cached_result, params.range)


@server.feature(TEXT_DOCUMENT_DEFINITION)
def definition(ls: SynesisLanguageServer, params: DefinitionParams):
    """
    Go-to-definition: @bibref → SOURCE, código → ONTOLOGY.

    Depende do workspace_cache; retorna None se cache vazio.
    """
    uri = params.text_document.uri
    doc = ls.workspace.get_document(uri)

    cached_result = _get_cached_for_uri(ls, uri)

    return compute_definition(doc.source, params.position, cached_result)


@server.feature(TEXT_DOCUMENT_REFERENCES)
def references(ls: SynesisLanguageServer, params: ReferenceParams):
    """
    Find All References: encontra todas as referências a codes e bibrefs.

    Depende do workspace_cache; retorna None se cache vazio.
    """
    uri = params.text_document.uri
    doc = ls.workspace.get_document(uri)

    cached_result = _get_cached_for_uri(ls, uri)
    if not cached_result:
        return None

    # Extrair palavra na posição do cursor
    line_idx = params.position.line
    lines = doc.source.split("\n")
    if line_idx >= len(lines):
        return None

    line = lines[line_idx]
    char_idx = params.position.character

    # Extrair palavra (incluindo @ para bibrefs)
    word = _get_word_at_position(line, char_idx)
    if not word:
        return None

    # Extrair workspace_root
    workspace_root = None
    workspace_folders = getattr(ls, "workspace", None)
    if workspace_folders:
        folders = getattr(workspace_folders, "folders", None)
        if folders and len(folders) > 0:
            workspace_root = Path(folders[0].uri.replace("file:///", "").replace("file://", ""))

    # Incluir declaração se context.includeDeclaration for True
    include_declaration = params.context.include_declaration if params.context else True

    return compute_references(cached_result, word, workspace_root, include_declaration)


@server.feature(TEXT_DOCUMENT_CODE_ACTION)
def code_action(ls: SynesisLanguageServer, params: CodeActionParams):
    """
    Code Actions: quick fixes para erros comuns (campos desconhecidos, etc.).

    Depende do workspace_cache; retorna None se cache vazio.
    """
    uri = params.text_document.uri
    cached_result = _get_cached_for_uri(ls, uri)

    return compute_code_actions(
        uri=uri,
        range_=params.range,
        diagnostics=params.context.diagnostics,
        cached_result=cached_result
    )


@server.feature(
    TEXT_DOCUMENT_COMPLETION,
    CompletionOptions(trigger_characters=["@"]),
)
def completion(ls: SynesisLanguageServer, params: CompletionParams):
    """
    Autocomplete: bibrefs após @, códigos da ontologia, campos do template.

    Depende do workspace_cache; retorna lista vazia se cache vazio.
    """
    uri = params.text_document.uri
    doc = ls.workspace.get_document(uri)

    cached_result = _get_cached_for_uri(ls, uri)

    trigger_char = None
    if params.context:
        trigger_char = getattr(params.context, "trigger_character", None)

    return compute_completions(doc.source, params.position, cached_result, trigger_char)


@server.feature(
    TEXT_DOCUMENT_SIGNATURE_HELP,
    SignatureHelpOptions(trigger_characters=[":"]),
)
def signature_help(ls: SynesisLanguageServer, params: SignatureHelpParams):
    """
    Mostra definição do campo durante preenchimento de valor.

    Trigger: após "campo:". Exibe tipo, escopo e descrição do FieldSpec.
    """
    uri = params.text_document.uri
    doc = ls.workspace.get_document(uri)

    cached_result = _get_cached_for_uri(ls, uri)

    return compute_signature_help(doc.source, params.position, cached_result)


@server.feature(TEXT_DOCUMENT_PREPARE_RENAME)
def prepare_rename_handler(ls: SynesisLanguageServer, params: PrepareRenameParams):
    """
    Verifica se o símbolo sob o cursor é renomeável.

    Retorna Range do símbolo se renomeável, None caso contrário.
    """
    uri = params.text_document.uri
    doc = ls.workspace.get_document(uri)

    cached_result = _get_cached_for_uri(ls, uri)

    return prepare_rename(doc.source, params.position, cached_result)


@server.feature(TEXT_DOCUMENT_RENAME)
def rename(ls: SynesisLanguageServer, params: RenameParams):
    """
    Renomeia bibref ou código em todo o workspace.

    Produz WorkspaceEdit com TextEdits para todos os arquivos afetados.
    """
    uri = params.text_document.uri
    doc = ls.workspace.get_document(uri)

    cached_result = _get_cached_for_uri(ls, uri)

    return compute_rename(doc.source, params.position, params.new_name, cached_result)


def _get_cached_for_workspace(ls: SynesisLanguageServer, params):
    """Helper: resolve workspace e retorna cached_result."""
    workspace_root = _resolve_workspace_root(ls, params)
    if not workspace_root:
        return None, "Workspace não encontrado"
    workspace_key = _workspace_key(workspace_root)
    if not workspace_key:
        return None, "Workspace inválido"
    return ls.workspace_cache.get(workspace_key), None


def _get_cached_for_uri(ls: SynesisLanguageServer, uri: str):
    """
    Helper: resolve workspace a partir de URI do documento.

    Usa _find_workspace_root (lsp_adapter) e, se falhar, tenta folders do LSP.
    Retorna cached_result ou None.
    """
    workspace_root = _find_workspace_root(uri)
    if not workspace_root and ls.workspace and hasattr(ls.workspace, "folders"):
        folders = ls.workspace.folders
        if folders:
            first_folder = next(iter(folders.values()), None)
            if first_folder:
                workspace_root = first_folder.uri

    workspace_key = _workspace_key(workspace_root)
    if not workspace_key:
        return None

    return ls.workspace_cache.get(workspace_key)


def _collect_existing_field_errors(result) -> set[tuple[str, Optional[str]]]:
    """Coleta erros já reportados pelo compilador para evitar duplicatas."""
    existing: set[tuple[str, Optional[str]]] = set()
    if not result:
        return existing
    all_errors = result.errors + result.warnings + result.info
    for error in all_errors:
        field = getattr(error, "field_name", None)
        if not field:
            continue
        block = getattr(error, "block_type", None)
        block_name = str(block).upper() if block else None
        existing.add((field, block_name))
    return existing


@server.command("synesis/getReferences")
def cmd_get_references(ls: SynesisLanguageServer, params) -> dict:
    """Retorna lista de SOURCEs com contagem de items."""
    cached, error = _get_cached_for_workspace(ls, params)
    if error and not cached:
        return get_references(None)
    return get_references(cached)


@server.command("synesis/getCodes")
def cmd_get_codes(ls: SynesisLanguageServer, params) -> dict:
    """Retorna lista de códigos com frequência de uso."""
    cached, error = _get_cached_for_workspace(ls, params)
    if error and not cached:
        return get_codes(None)
    return get_codes(cached)


@server.command("synesis/getRelations")
def cmd_get_relations(ls: SynesisLanguageServer, params) -> dict:
    """Retorna lista de triples (relações entre conceitos)."""
    cached, error = _get_cached_for_workspace(ls, params)
    if error and not cached:
        return get_relations(None)
    return get_relations(cached)


@server.command("synesis/getRelationGraph")
def cmd_get_relation_graph(ls: SynesisLanguageServer, params) -> dict:
    """Retorna código Mermaid.js do grafo de relações."""
    cached, error = _get_cached_for_workspace(ls, params)
    if error and not cached:
        return get_relation_graph(None)

    # Extrai bibref opcional dos params
    bibref = None
    if isinstance(params, dict):
        bibref = params.get("bibref")
    elif isinstance(params, list) and len(params) > 0:
        first = params[0]
        if isinstance(first, dict):
            bibref = first.get("bibref")

    return get_relation_graph(cached, bibref=bibref)


@server.command("synesis/debug/diagnostics")
def debug_diagnostics(ls: SynesisLanguageServer, params) -> dict:
    """
    Debug command to check diagnostic system status.

    Returns dict with diagnostic system status and test results.
    """
    uri = None
    if isinstance(params, list) and len(params) > 0:
        first = params[0]
        if isinstance(first, dict):
            uri = first.get("uri")
    elif isinstance(params, dict):
        uri = params.get("uri")

    status = {
        "validation_enabled": ls.validation_enabled,
        "template_diagnostics_module": "imported",
    }

    if uri:
        # Test specific URI
        try:
            cached = _get_cached_for_uri(ls, uri)
            status["cached_available"] = cached is not None

            if cached:
                template = getattr(cached.result, "template", None)
                status["template_available"] = template is not None

                if template:
                    field_specs = getattr(template, "field_specs", {})
                    status["template_fields"] = list(field_specs.keys())

            context = _discover_context(uri)
            status["context_discoverable"] = context is not None

        except Exception as e:
            status["error"] = str(e)

    return {"success": True, "status": status}


@server.command("synesis/getOntologyTopics")
def cmd_get_ontology_topics(ls: SynesisLanguageServer, params) -> dict:
    """Retorna hierarquia de tópicos da ontologia."""
    cached, error = _get_cached_for_workspace(ls, params)
    if error and not cached:
        return get_ontology_topics(None)

    # Extrair workspace_root dos params
    workspace_root = None
    if isinstance(params, dict):
        workspace_root_str = params.get("workspaceRoot")
        if workspace_root_str:
            workspace_root = Path(workspace_root_str)
    elif isinstance(params, list) and len(params) > 0:
        first = params[0]
        if isinstance(first, dict):
            workspace_root_str = first.get("workspaceRoot")
            if workspace_root_str:
                workspace_root = Path(workspace_root_str)

    return get_ontology_topics(cached, workspace_root=workspace_root)


@server.command("synesis/getOntologyAnnotations")
def cmd_get_ontology_annotations(ls: SynesisLanguageServer, params) -> dict:
    """Retorna anotações de ontologia com occurrences."""
    cached, error = _get_cached_for_workspace(ls, params)
    if error and not cached:
        return get_ontology_annotations(None)

    # Extrair workspace_root e activeFile dos params
    workspace_root = None
    active_file = None

    if isinstance(params, dict):
        workspace_root_str = params.get("workspaceRoot")
        if workspace_root_str:
            workspace_root = Path(workspace_root_str)
        active_file = params.get("activeFile")
    elif isinstance(params, list) and len(params) > 0:
        first = params[0]
        if isinstance(first, dict):
            workspace_root_str = first.get("workspaceRoot")
            if workspace_root_str:
                workspace_root = Path(workspace_root_str)
            active_file = first.get("activeFile")

    return get_ontology_annotations(
        cached,
        workspace_root=workspace_root,
        active_file=active_file
    )


@server.command("synesis/getAbstract")
def cmd_get_abstract(ls: SynesisLanguageServer, params) -> dict:
    """Retorna campo ABSTRACT de arquivo .syn."""
    # Extrair file path dos params
    file_path = None
    workspace_root = None

    if isinstance(params, dict):
        file_path = params.get("file")
        workspace_root_str = params.get("workspaceRoot")
        if workspace_root_str:
            workspace_root = Path(workspace_root_str)
    elif isinstance(params, list) and len(params) > 0:
        first = params[0]
        if isinstance(first, dict):
            file_path = first.get("file")
            workspace_root_str = first.get("workspaceRoot")
            if workspace_root_str:
                workspace_root = Path(workspace_root_str)

    if not file_path:
        return {"success": False, "error": "Parâmetro 'file' não fornecido"}

    # Tentar obter cached_result (opcional)
    cached = None
    if workspace_root:
        ws_key = _workspace_key(workspace_root)
        cached = ls.workspace_cache.get(ws_key) if ws_key else None

    return get_abstract(file_path, cached_result=cached, workspace_root=workspace_root)


@server.command("synesis/validateWorkspace")
def cmd_validate_workspace(ls: SynesisLanguageServer, params) -> dict:
    """
    Valida todos os arquivos Synesis no workspace.

    Returns dict com resultados de validação por arquivo.
    """
    # Extrair workspace_root dos params
    workspace_root = None

    if isinstance(params, dict):
        workspace_root_str = params.get("workspaceRoot")
        if workspace_root_str:
            workspace_root = Path(workspace_root_str)
    elif isinstance(params, list) and len(params) > 0:
        first = params[0]
        if isinstance(first, dict):
            workspace_root_str = first.get("workspaceRoot")
            if workspace_root_str:
                workspace_root = Path(workspace_root_str)

    if not workspace_root:
        return {"success": False, "error": "Workspace root não fornecido"}

    # Função de validação para passar ao compute_workspace_diagnostics
    def validate_func(uri: str, file_path: Path) -> list:
        return validate_workspace_file(uri, file_path, validate_single_file)

    # Computar diagnósticos para todo workspace
    diagnostics_map = compute_workspace_diagnostics(workspace_root, validate_func)

    # Publicar diagnósticos para cada arquivo
    for uri, diagnostics in diagnostics_map.items():
        ls.publish_diagnostics(uri, diagnostics)

    # Retornar resumo
    total_files = len(diagnostics_map)
    files_with_errors = sum(1 for diags in diagnostics_map.values() if diags)
    total_diagnostics = sum(len(diags) for diags in diagnostics_map.values())

    return {
        "success": True,
        "totalFiles": total_files,
        "filesWithErrors": files_with_errors,
        "totalDiagnostics": total_diagnostics
    }


def validate_document(ls: SynesisLanguageServer, uri: str) -> None:
    """
    Valida um documento Synesis e publica diagnósticos.

    Args:
        ls: Instância do servidor
        uri: URI do documento a validar

    Fluxo:
        1. Verifica se validação está habilitada (synesis.validation.enabled)
        2. Obtém conteúdo do documento
        3. Valida usando validate_single_file (que tem cache interno com mtime)
        4. Converte ValidationResult → List[Diagnostic]
        5. Publica diagnósticos via ls.publish_diagnostics()
        6. Registra documento no workspace para futura revalidação

    Nota sobre Cache:
        - O cache de contexto é gerenciado internamente pelo lsp_adapter
        - O cache valida automaticamente mtimes dos arquivos .synp/.synt/.bib
        - O servidor apenas rastreia quais documentos estão abertos por workspace
        - Quando .synp/.synt/.bib mudam, o servidor invalida o cache do lsp_adapter
          e revalida todos os documentos abertos

    Tratamento de Erros:
        - Captura todas as exceções para evitar crash do servidor
        - Loga erros mas mantém servidor responsivo
        - Em caso de erro fatal, publica diagnostic genérico
    """
    # Verifica se validação está habilitada
    if not ls.validation_enabled:
        logger.debug(f"Validação desabilitada, pulando: {uri}")
        # Limpa diagnósticos existentes quando validação está desabilitada
        ls.publish_diagnostics(uri, [])
        return

    try:
        # Obtém documento do workspace
        doc = ls.workspace.get_document(uri)
        source = doc.source

        # VALIDAR COM DESCOBERTA AUTOMÁTICA DE CONTEXTO
        # O lsp_adapter gerencia cache internamente com validação por mtime
        result = validate_single_file(source, uri, context=None)

        # CONVERTER PARA DIAGNÓSTICOS LSP
        diagnostics = build_diagnostics(result)

        # Diagnósticos adicionais baseados em template (fallback)
        try:
            template = None
            cached = _get_cached_for_uri(ls, uri)
            if cached:
                template = getattr(cached.result, "template", None)
                if template:
                    logger.debug(f"Template found in cache for {uri}")
                else:
                    logger.debug(f"No template in cache for {uri}")

            if not template:
                logger.debug(f"Attempting template discovery for {uri}")
                context = _discover_context(uri)
                template = getattr(context, "template", None)
                if template:
                    logger.debug(f"Template discovered for {uri}")
                else:
                    logger.debug(f"Template discovery failed for {uri}")

            if template:
                existing_fields = _collect_existing_field_errors(result)
                logger.debug(f"Collected {len(existing_fields)} existing field errors")

                template_diags = build_template_diagnostics(source, uri, template, existing_fields)
                logger.debug(f"Generated {len(template_diags)} template diagnostics")

                diagnostics.extend(template_diags)
            else:
                logger.info(f"No template available for {uri}, skipping template diagnostics")

        except Exception as e:
            logger.warning(f"Template diagnostics failed for {uri}: {e}", exc_info=True)

        # PUBLICAR DIAGNÓSTICOS
        try:
            logger.debug(f"Publishing {len(diagnostics)} diagnostics for {uri}")
            ls.publish_diagnostics(uri, diagnostics)
            logger.info(f"Published diagnostics for {uri}")
        except Exception as e:
            logger.error(f"Failed to publish diagnostics for {uri}: {e}", exc_info=True)

        # REGISTRAR DOCUMENTO NO WORKSPACE (para revalidação futura)
        workspace_root = _find_workspace_root(uri)
        if workspace_root:
            workspace_key = _workspace_key(workspace_root)
            if workspace_key:
                if workspace_key not in ls.workspace_documents:
                    ls.workspace_documents[workspace_key] = set()
                ls.workspace_documents[workspace_key].add(uri)

        logger.info(
            f"Validação completa: {uri} - "
            f"{len(result.errors)} erros, "
            f"{len(result.warnings)} avisos"
        )

    except Exception as e:
        # Log do erro mas não crash
        logger.error(f"Erro ao validar {uri}: {e}", exc_info=True)

        # Enriquece mensagem com error_handler se possível
        enriched_msg = enrich_error_message(e, source=source, filename=uri)

        # Publica diagnostic de erro interno
        from lsprotocol.types import Diagnostic, DiagnosticSeverity, Position, Range

        error_diagnostic = Diagnostic(
            range=Range(
                start=Position(line=0, character=0),
                end=Position(line=0, character=1),
            ),
            severity=DiagnosticSeverity.Error,
            source="synesis-lsp",
            message=enriched_msg,
        )
        ls.publish_diagnostics(uri, [error_diagnostic])


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: SynesisLanguageServer, params: DidOpenTextDocumentParams) -> None:
    """
    Handler para abertura de documento.

    Valida imediatamente quando usuário abre arquivo Synesis.
    """
    logger.info(f"Documento aberto: {params.text_document.uri}")
    validate_document(ls, params.text_document.uri)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: SynesisLanguageServer, params: DidChangeTextDocumentParams) -> None:
    """
    Handler para mudanças no documento.

    Nota sobre debounce:
        - pygls 1.0+ suporta debounce nativo via decorador
        - Versão atual implementa validação imediata
        - Para adicionar debounce, usar: @server.feature(TEXT_DOCUMENT_DID_CHANGE, debounce=0.3)
    """
    logger.info(f"Documento modificado: {params.text_document.uri}")
    validate_document(ls, params.text_document.uri)


@server.feature(TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: SynesisLanguageServer, params: DidCloseTextDocumentParams) -> None:
    """
    Handler para fechamento de documento.

    Limpa diagnósticos e remove documento do rastreamento.
    """
    uri = params.text_document.uri
    logger.info(f"Documento fechado: {uri}")

    # Limpa diagnósticos
    ls.publish_diagnostics(uri, [])

    # Remove do rastreamento de workspace
    workspace_root = _find_workspace_root(uri)
    if workspace_root:
        workspace_key = _workspace_key(workspace_root)
        if workspace_key and workspace_key in ls.workspace_documents:
            ls.workspace_documents[workspace_key].discard(uri)


@server.feature(WORKSPACE_DID_CHANGE_CONFIGURATION)
def did_change_configuration(
    ls: SynesisLanguageServer, params: DidChangeConfigurationParams
) -> None:
    """
    Handler para mudanças na configuração do workspace.

    Atualiza configurações do servidor (como synesis.validation.enabled)
    e revalida documentos abertos se necessário.

    Nota: A configuração vem diretamente no params.settings quando o cliente
    sincroniza via configurationSection: 'synesis' no LanguageClientOptions.
    """
    try:
        # A configuração vem em params.settings quando sincronizada
        settings = params.settings

        # Lê validation.enabled (padrão: True)
        old_validation_enabled = ls.validation_enabled

        # settings pode ser um dict com seção 'synesis' ou já ser a seção
        if isinstance(settings, dict):
            # Pode vir como {'synesis': {...}} ou diretamente {...}
            synesis_config = settings.get("synesis", settings)

            if isinstance(synesis_config, dict):
                validation_config = synesis_config.get("validation", {})
                if isinstance(validation_config, dict):
                    ls.validation_enabled = validation_config.get("enabled", True)
                else:
                    ls.validation_enabled = True
            else:
                ls.validation_enabled = True
        else:
            ls.validation_enabled = True

        logger.info(f"Configuração atualizada: validation.enabled = {ls.validation_enabled}")

        # Se validação foi reativada, revalida todos os documentos
        if not old_validation_enabled and ls.validation_enabled:
            logger.info("Validação reativada, revalidando documentos abertos")
            for workspace_key, doc_uris in ls.workspace_documents.items():
                for doc_uri in list(doc_uris):
                    try:
                        validate_document(ls, doc_uri)
                    except Exception as e:
                        logger.error(f"Erro ao revalidar {doc_uri}: {e}", exc_info=True)

        # Se validação foi desativada, limpa diagnósticos
        elif old_validation_enabled and not ls.validation_enabled:
            logger.info("Validação desativada, limpando diagnósticos")
            for workspace_key, doc_uris in ls.workspace_documents.items():
                for doc_uri in list(doc_uris):
                    ls.publish_diagnostics(doc_uri, [])

    except Exception as e:
        logger.error(f"Erro ao processar mudança de configuração: {e}", exc_info=True)


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: SynesisLanguageServer, params: DidSaveTextDocumentParams) -> None:
    """
    Handler para salvamento de documento.

    Comportamento especial para arquivos .synp e .synt:
        - Invalida cache do workspace
        - Revalida todos os documentos abertos no workspace

    Para outros arquivos (.syn, .syno, .bib):
        - Apenas revalida o arquivo salvo (já feito pelo didChange)
    """
    uri = params.text_document.uri
    logger.info(f"Documento salvo: {uri}")

    # Detecta tipo de arquivo
    file_path = Path(uri.replace("file://", ""))
    file_extension = file_path.suffix

    # Arquivos que afetam contexto do workspace (.synp, .synt)
    if file_extension in [".synp", ".synt"]:
        logger.info(f"Arquivo de contexto modificado: {uri}")

        # 1. ENCONTRAR WORKSPACE ROOT
        workspace_root = _find_workspace_root(uri)
        if not workspace_root:
            logger.warning(f"Workspace root não encontrado para {uri}")
            return

        workspace_key = _workspace_key(workspace_root)
        if not workspace_key:
            logger.warning(f"Workspace inválido para {uri}")
            return

        # 2. INVALIDAR CACHES
        _invalidate_cache(workspace_root)
        ls.workspace_cache.invalidate(workspace_key)
        logger.info(f"Caches invalidados para: {workspace_key}")

        # 3. REVALIDAR TODOS OS DOCUMENTOS ABERTOS NO WORKSPACE
        if workspace_key in ls.workspace_documents:
            documents_to_revalidate = list(ls.workspace_documents[workspace_key])
            logger.info(
                f"Revalidando {len(documents_to_revalidate)} documentos no workspace"
            )

            for doc_uri in documents_to_revalidate:
                try:
                    validate_document(ls, doc_uri)
                except Exception as e:
                    logger.error(f"Erro ao revalidar {doc_uri}: {e}", exc_info=True)

    # Arquivos .bib também afetam validação (bibrefs)
    elif file_extension == ".bib":
        logger.info(f"Bibliografia modificada: {uri}")

        workspace_root = _find_workspace_root(uri)
        if workspace_root:
            workspace_key = _workspace_key(workspace_root)
            if not workspace_key:
                logger.warning(f"Workspace inválido para {uri}")
                return

            # Invalidar caches
            _invalidate_cache(workspace_root)
            ls.workspace_cache.invalidate(workspace_key)
            logger.info(f"Caches invalidados para: {workspace_key}")

            # Revalidar documentos
            if workspace_key in ls.workspace_documents:
                for doc_uri in list(ls.workspace_documents[workspace_key]):
                    try:
                        validate_document(ls, doc_uri)
                    except Exception as e:
                        logger.error(f"Erro ao revalidar {doc_uri}: {e}", exc_info=True)

    # Arquivos .syn e .syno afetam o projeto compilado (workspace_cache)
    elif file_extension in [".syn", ".syno"]:
        workspace_root = _find_workspace_root(uri)
        if workspace_root:
            workspace_key = _workspace_key(workspace_root)
            if workspace_key:
                ls.workspace_cache.invalidate(workspace_key)


@server.feature(WORKSPACE_DID_CHANGE_WATCHED_FILES)
def did_change_watched_files(
    ls: SynesisLanguageServer, params: DidChangeWatchedFilesParams
) -> None:
    """
    Handler para mudanças em arquivos monitorados (.synp, .synt, .bib).

    Este handler é acionado quando arquivos monitorados são:
        - Criados (FileChangeType.Created)
        - Modificados (FileChangeType.Changed)
        - Deletados (FileChangeType.Deleted)

    Comportamento:
        - Invalida cache do workspace afetado
        - Revalida documentos abertos no workspace
    """
    for change in params.changes:
        uri = change.uri
        change_type = change.type

        logger.info(
            f"Arquivo monitorado mudou: {uri} (tipo: {change_type.name})"
        )

        # Detecta extensão do arquivo
        file_path = Path(uri.replace("file://", ""))
        file_extension = file_path.suffix

        # Apenas processar arquivos Synesis
        if file_extension not in [".synp", ".synt", ".bib", ".syn", ".syno"]:
            continue

        # Encontrar workspace root
        workspace_root = _find_workspace_root(uri)
        if not workspace_root:
            continue

        workspace_key = _workspace_key(workspace_root)
        if not workspace_key:
            continue

        # Invalidar caches
        _invalidate_cache(workspace_root)
        ls.workspace_cache.invalidate(workspace_key)
        logger.info(f"Caches invalidados para workspace: {workspace_key}")

        # Revalidar todos os documentos abertos no workspace
        if workspace_key in ls.workspace_documents:
            documents_to_revalidate = list(ls.workspace_documents[workspace_key])
            logger.info(
                f"Revalidando {len(documents_to_revalidate)} documentos "
                f"devido a mudança em {file_path.name}"
            )

            for doc_uri in documents_to_revalidate:
                try:
                    validate_document(ls, doc_uri)
                except Exception as e:
                    logger.error(f"Erro ao revalidar {doc_uri}: {e}", exc_info=True)


def main() -> None:
    """
    Ponto de entrada principal do servidor.

    Inicia servidor LSP em modo STDIO para comunicação com VSCode.
    """
    global _startup_logged
    logger.info("Iniciando Synesis Language Server...")
    if not _startup_logged:
        _startup_logged = True
        logger.info("Python executable: %s", sys.executable)
        try:
            import synesis  # type: ignore

            logger.info("synesis module: %s", getattr(synesis, "__file__", "<unknown>"))
        except Exception as exc:
            logger.warning("Falha ao importar synesis: %s", exc)
        logger.info(
            "synesis-lsp package: %s", metadata.version("synesis-lsp")
        )
    server.start_io()


if __name__ == "__main__":
    main()
