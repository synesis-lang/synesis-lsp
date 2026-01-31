/**
 * extension.ts - Cliente LSP para Synesis no VSCode
 *
 * Propósito:
 *   Gerencia conexão entre VSCode e synesis-lsp server Python.
 *   Fornece validação em tempo real para arquivos Synesis.
 *
 * Componentes:
 *   - activate(): Inicializa extensão e cliente LSP
 *   - deactivate(): Cleanup ao desativar extensão
 *   - createLanguageClient(): Configura servidor e cliente
 *
 * Gerado conforme: Especificação Synesis v1.1 + ADR-002 LSP
 */

import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';
import {
    LanguageClient,
    LanguageClientOptions,
    ServerOptions,
    TransportKind,
} from 'vscode-languageclient/node';

let client: LanguageClient | undefined;

/**
 * Ativa a extensão Synesis.
 *
 * Chamado quando VSCode detecta arquivo .syn/.synp/.synt/.syno
 * ou quando usuário executa comando da extensão.
 */
export function activate(context: vscode.ExtensionContext): void {
    console.log('Synesis extension is now active');

    // Configura output channel para logs
    const outputChannel = vscode.window.createOutputChannel('Synesis LSP');

    try {
        // Cria e inicia cliente LSP
        client = createLanguageClient(outputChannel);

        // Inicia cliente
        client.start();

        // Registra para cleanup
        context.subscriptions.push(client);

        outputChannel.appendLine('Synesis Language Server iniciado com sucesso');
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        outputChannel.appendLine(`Erro ao iniciar Synesis LSP: ${message}`);
        vscode.window.showErrorMessage(
            `Falha ao iniciar Synesis Language Server: ${message}`
        );
    }
}

/**
 * Desativa a extensão.
 *
 * Chamado quando VSCode está fechando ou extensão está sendo descarregada.
 */
export function deactivate(): Thenable<void> | undefined {
    if (!client) {
        return undefined;
    }
    return client.stop();
}

/**
 * Cria e configura o Language Client.
 *
 * @param outputChannel - Canal para logs
 * @returns Cliente LSP configurado
 */
function createLanguageClient(
    outputChannel: vscode.OutputChannel
): LanguageClient {
    // Configuração do servidor
    const serverOptions: ServerOptions = {
        command: getPythonCommand(outputChannel),
        args: ['-m', 'synesis_lsp'],
        options: {
            cwd: undefined, // Usa workspace atual
        },
    };

    // Configuração do cliente
    const clientOptions: LanguageClientOptions = {
        // Tipos de documentos que o servidor deve monitorar
        documentSelector: [
            { scheme: 'file', language: 'synesis' },
            { scheme: 'file', pattern: '**/*.syn' },
            { scheme: 'file', pattern: '**/*.synp' },
            { scheme: 'file', pattern: '**/*.synt' },
            { scheme: 'file', pattern: '**/*.syno' },
        ],

        // Synchronize settings para o servidor
        synchronize: {
            // Monitora mudanças em configurações synesis.*
            configurationSection: 'synesis',
            // Monitora arquivos que afetam contexto do workspace:
            // - .synp: Arquivos de projeto
            // - .synt: Templates
            // - .bib: Bibliografias
            fileEvents: [
                vscode.workspace.createFileSystemWatcher('**/*.synp'),
                vscode.workspace.createFileSystemWatcher('**/*.synt'),
                vscode.workspace.createFileSystemWatcher('**/*.bib'),
            ],
        },

        // Output channel para logs do servidor
        outputChannel: outputChannel,

        // Rastrear comunicação (útil para debug)
        // Controlado por synesisLanguageServer.trace.server no settings
        traceOutputChannel: outputChannel,
    };

    // Cria cliente
    const client = new LanguageClient(
        'synesisLanguageServer',
        'Synesis Language Server',
        serverOptions,
        clientOptions
    );

    return client;
}

/**
 * Obtém comando Python configurado.
 *
 * Primeiro tenta configuração do usuário, depois fallback para python3.
 *
 * @returns Caminho para Python interpreter
 */
function getPythonCommand(outputChannel: vscode.OutputChannel): string {
    const synesisConfig = vscode.workspace.getConfiguration('synesis');
    const pythonPath = synesisConfig.get<string>('pythonPath');

    if (pythonPath && pythonPath.trim() !== '') {
        const resolved = resolvePythonPath(pythonPath, outputChannel);
        outputChannel.appendLine(`Usando Python (synesis.pythonPath): ${resolved}`);
        return resolved;
    }

    const pythonConfig = vscode.workspace.getConfiguration('python');
    const defaultInterpreter =
        pythonConfig.get<string>('defaultInterpreterPath') ||
        pythonConfig.get<string>('pythonPath');

    if (defaultInterpreter && defaultInterpreter.trim() !== '') {
        outputChannel.appendLine(
            `Usando Python (python.defaultInterpreterPath): ${defaultInterpreter}`
        );
        return defaultInterpreter;
    }

    const fallback = process.platform === 'win32' ? 'python' : 'python3';
    outputChannel.appendLine(`Usando Python (fallback): ${fallback}`);
    return fallback;
}

function resolvePythonPath(rawPath: string, outputChannel: vscode.OutputChannel): string {
    let resolved = rawPath;
    if (rawPath.includes('${workspaceFolder}')) {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            outputChannel.appendLine(
                'Aviso: ${workspaceFolder} definido, mas nenhum workspace ativo.'
            );
            return rawPath;
        }
        resolved = rawPath.replace(
            /\$\{workspaceFolder\}/g,
            workspaceFolder.uri.fsPath
        );
    }

    if (!fs.existsSync(resolved)) {
        outputChannel.appendLine(`Aviso: Python path nao encontrado: ${resolved}`);
    }

    return resolved;
}
