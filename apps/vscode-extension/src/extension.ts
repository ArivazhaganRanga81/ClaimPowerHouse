import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as http from "node:http";
import * as net from "node:net";
import * as path from "node:path";
import { ChildProcess, spawn } from "node:child_process";
import * as vscode from "vscode";

interface ClaimItem {
  id: string;
  external_claim_id: string;
  status: string;
  risk_score: number;
  billed_amount_minor: number;
  currency: string;
}

interface ClaimPage {
  items: ClaimItem[];
  total: number;
}

class RuntimeManager implements vscode.Disposable {
  private process: ChildProcess | undefined;
  private port: number | undefined;
  private token: string | undefined;
  private starting: Promise<void> | undefined;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly output: vscode.OutputChannel,
    private readonly status: vscode.StatusBarItem
  ) {}

  get baseUrl(): string | undefined {
    return this.port ? `http://127.0.0.1:${this.port}` : undefined;
  }

  get bearerToken(): string | undefined {
    return this.token;
  }

  async start(): Promise<void> {
    if (this.baseUrl && await this.isHealthy()) return;
    if (this.starting) return this.starting;
    this.starting = this.startInternal();
    try {
      await this.starting;
    } finally {
      this.starting = undefined;
    }
  }

  private async startInternal(): Promise<void> {
    this.status.text = "$(sync~spin) CPH starting";
    this.status.show();
    await vscode.workspace.fs.createDirectory(this.context.globalStorageUri);
    this.port = await this.choosePort();
    this.token = crypto.randomBytes(32).toString("hex");
    const dataRoot = this.context.globalStorageUri.fsPath;
    const packagedWebRoot = path.join(this.context.extensionPath, "media", "web");
    const webRoot = fs.existsSync(packagedWebRoot)
      ? packagedWebRoot
      : path.resolve(this.context.extensionPath, "..", "web", "dist");
    const runtime = this.runtimeCommand();
    const codexPath = this.codexExecutable();
    const databasePath = path.join(dataRoot, "db", "claim_powerhouse.db").replaceAll("\\", "/");
    const environment = {
      ...process.env,
      CPH_DATA_ROOT: dataRoot,
      CPH_DATABASE_URL: `sqlite:///${databasePath}`,
      CPH_CHROMA_PATH: path.join(dataRoot, "chroma"),
      CPH_WEB_ROOT: webRoot,
      CPH_SIDECAR_TOKEN: this.token,
      CPH_LLM_PROVIDER: "codex",
      CPH_LLM_MODEL: "default",
      CPH_CODEX_PATH: codexPath,
      CPH_AUTO_SEED: "true",
      CPH_DEMO_MODE: "true",
      PYTHONUNBUFFERED: "1"
    };
    this.output.appendLine(`Starting local runtime on 127.0.0.1:${this.port}`);
    this.output.appendLine(`Codex runtime: ${codexPath}`);
    this.process = spawn(runtime.command, runtime.args(this.port), {
      cwd: runtime.cwd,
      env: environment,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"]
    });
    this.process.stdout?.on("data", (data: Buffer) => this.output.append(data.toString()));
    this.process.stderr?.on("data", (data: Buffer) => this.output.append(data.toString()));
    this.process.on("exit", (code) => {
      this.output.appendLine(`Local runtime exited with code ${String(code)}.`);
      this.process = undefined;
      this.status.text = "$(error) CPH stopped";
      this.status.tooltip = "Claim Power House local runtime is stopped";
    });
    this.process.on("error", (error) => this.output.appendLine(`Runtime error: ${error.message}`));

    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline) {
      if (await this.isHealthy()) {
        this.status.text = "$(shield) CPH ready";
        this.status.tooltip = "Claim Power House local runtime is ready";
        return;
      }
      if (this.process.exitCode !== null) break;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    this.stop();
    throw new Error("Claim Power House runtime did not become ready. Open logs for details.");
  }

  private runtimeCommand(): { command: string; cwd: string; args: (port: number) => string[] } {
    const platformName = `${process.platform}-${process.arch}`;
    const executableName = process.platform === "win32" ? "claim-power-house-backend.exe" : "claim-power-house-backend";
    const bundled = path.join(this.context.extensionPath, "runtime", platformName, executableName);
    if (fs.existsSync(bundled)) {
      return {
        command: bundled,
        cwd: path.dirname(bundled),
        args: (port) => ["serve", "--host", "127.0.0.1", "--port", String(port)]
      };
    }
    const python = vscode.workspace.getConfiguration("claimPowerHouse").get<string>("pythonPath", "python");
    const workspaceApiRoot = vscode.workspace.workspaceFolders?.[0]
      ? path.join(vscode.workspace.workspaceFolders[0].uri.fsPath, "apps", "api")
      : undefined;
    const packagedApiRoot = path.join(this.context.extensionPath, "runtime", "api");
    const apiRoot = workspaceApiRoot && fs.existsSync(path.join(workspaceApiRoot, "app"))
      ? workspaceApiRoot
      : packagedApiRoot;
    this.output.appendLine("Bundled runtime not found; using the development Python runtime.");
    return {
      command: python,
      cwd: apiRoot,
      args: (port) => [
        "-m", "uvicorn", "app.main:app", "--app-dir", apiRoot,
        "--host", "127.0.0.1", "--port", String(port)
      ]
    };
  }

  private codexExecutable(): string {
    const codexExtension = vscode.extensions.getExtension("openai.chatgpt");
    if (!codexExtension) return "codex";
    const architecture = process.arch === "arm64" ? "aarch64" : "x86_64";
    const platform = process.platform === "win32"
      ? `windows-${architecture}`
      : process.platform === "darwin"
        ? `macos-${architecture}`
        : `linux-${architecture}`;
    const executable = process.platform === "win32" ? "codex.exe" : "codex";
    const candidate = path.join(codexExtension.extensionPath, "bin", platform, executable);
    return fs.existsSync(candidate) ? candidate : "codex";
  }

  private async choosePort(): Promise<number> {
    const configured = vscode.workspace.getConfiguration("claimPowerHouse").get<number>("backendPort", 0);
    if (configured) return configured;
    return new Promise((resolve, reject) => {
      const server = net.createServer();
      server.once("error", reject);
      server.listen(0, "127.0.0.1", () => {
        const address = server.address();
        const selected = typeof address === "object" && address ? address.port : 0;
        server.close((error) => error ? reject(error) : resolve(selected));
      });
    });
  }

  private async isHealthy(): Promise<boolean> {
    if (!this.baseUrl) return false;
    try {
      const response = await fetch(`${this.baseUrl}/health/ready`, { signal: AbortSignal.timeout(800) });
      return response.ok;
    } catch {
      return false;
    }
  }

  async api<T>(pathName: string): Promise<T> {
    await this.start();
    const response = await fetch(`${this.baseUrl}${pathName}`, {
      headers: { Authorization: `Bearer ${this.token}` }
    });
    if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
    return response.json() as Promise<T>;
  }

  bootstrapUrl(claimId?: string): string {
    if (!this.baseUrl || !this.token) throw new Error("Runtime is not started");
    const claim = claimId ? `&claim_id=${encodeURIComponent(claimId)}` : "";
    return `${this.baseUrl}/sidecar-bootstrap?token=${encodeURIComponent(this.token)}${claim}`;
  }

  stop(): void {
    if (this.process && this.process.exitCode === null) this.process.kill();
    this.process = undefined;
    this.port = undefined;
    this.token = undefined;
    this.status.text = "$(circle-slash) CPH stopped";
  }

  dispose(): void { this.stop(); }
}

class ClaimsProvider implements vscode.TreeDataProvider<ClaimItem> {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;

  constructor(private readonly runtime: RuntimeManager) {}
  refresh(): void { this.changed.fire(); }
  getTreeItem(item: ClaimItem): vscode.TreeItem {
    const treeItem = new vscode.TreeItem(item.external_claim_id, vscode.TreeItemCollapsibleState.None);
    treeItem.description = `${item.status.replaceAll("_", " ")} · ${new Intl.NumberFormat("en-US", {
      style: "currency", currency: item.currency
    }).format(item.billed_amount_minor / 100)}`;
    treeItem.tooltip = `Risk ${item.risk_score}/100`;
    treeItem.command = { command: "claimPowerHouse.open", title: "Open Claim", arguments: [item.id] };
    treeItem.iconPath = new vscode.ThemeIcon(item.risk_score >= 70 ? "warning" : "file");
    return treeItem;
  }
  async getChildren(): Promise<ClaimItem[]> {
    try {
      return (await this.runtime.api<ClaimPage>("/api/v1/claims?limit=50")).items;
    } catch (error) {
      void vscode.window.showErrorMessage(`Claim Power House: ${String(error)}`);
      return [];
    }
  }
}

function workbenchHtml(url: string): string {
  const nonce = crypto.randomBytes(16).toString("base64");
  const origin = new URL(url).origin;
  return `<!doctype html>
<html><head><meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src ${origin}; child-src ${origin}; connect-src ${origin}; style-src 'nonce-${nonce}';">
<style nonce="${nonce}">html,body,iframe{width:100%;height:100%;margin:0;border:0;background:var(--vscode-editor-background)}</style>
</head><body><iframe title="Claim Power House Workbench" src="${url}" sandbox="allow-scripts allow-same-origin allow-forms allow-modals" allow="clipboard-write"></iframe></body></html>`;
}

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel("Claim Power House", { log: true });
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  status.command = "claimPowerHouse.open";
  status.text = "$(circle-slash) CPH stopped";
  status.show();
  const runtime = new RuntimeManager(context, output, status);
  const claims = new ClaimsProvider(runtime);
  vscode.window.registerTreeDataProvider("claimPowerHouse.queue", claims);

  context.subscriptions.push(
    output, status, runtime,
    vscode.commands.registerCommand("claimPowerHouse.start", async () => {
      await runtime.start();
      claims.refresh();
    }),
    vscode.commands.registerCommand("claimPowerHouse.stop", () => runtime.stop()),
    vscode.commands.registerCommand("claimPowerHouse.showLogs", () => output.show()),
    vscode.commands.registerCommand("claimPowerHouse.open", async (claimId?: string) => {
      try {
        await runtime.start();
        // Open the local workbench in the system browser. This avoids VS Code
        // webview iframe restrictions while preserving the authenticated sidecar.
        await vscode.env.openExternal(vscode.Uri.parse(runtime.bootstrapUrl(claimId)));
        claims.refresh();
      } catch (error) {
        output.show();
        void vscode.window.showErrorMessage(`Claim Power House failed to start: ${String(error)}`);
      }
    })
  );
}

export function deactivate(): void {}
