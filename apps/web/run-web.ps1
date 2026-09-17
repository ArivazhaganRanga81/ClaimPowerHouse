param(
    [int]$Port = 8000,
    [string]$Model = "",
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$webRoot = Join-Path $PSScriptRoot "dist"

if (-not (Test-Path -LiteralPath (Join-Path $webRoot "index.html"))) {
    throw "Web UI is not built. Run 'npm run build' from apps\web."
}

function Import-DotEnv([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') { continue }
        $name = $Matches[1]
        $value = $Matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ([string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($name, "Process"))) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

Import-DotEnv (Join-Path $repoRoot ".env")
Import-DotEnv (Join-Path $PSScriptRoot ".env")

$apiKey = if ($env:CPH_LLM_API_KEY) { $env:CPH_LLM_API_KEY } else { $env:OPENAI_API_KEY }
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    throw "Set CPH_LLM_API_KEY or OPENAI_API_KEY in $repoRoot\.env"
}

$dataRoot = Join-Path $repoRoot "data\runtime-web"
$databasePath = (Join-Path $dataRoot "db\claim_powerhouse.db").Replace("\", "/")

$env:CPH_DATA_ROOT = $dataRoot
$env:CPH_DATABASE_URL = "sqlite:///$databasePath"
$env:CPH_CHROMA_PATH = Join-Path $dataRoot "chroma"
$env:CPH_WEB_ROOT = $webRoot
$env:CPH_LLM_PROVIDER = "openai"
$env:CPH_LLM_MODEL = if ($Model) { $Model } elseif ($env:CPH_LLM_MODEL) { $env:CPH_LLM_MODEL } else { "gpt-4.1-mini" }
$env:CPH_LLM_API_KEY = $apiKey
$env:CPH_AUTO_SEED = "true"
$env:CPH_DEMO_MODE = "true"
Remove-Item Env:CPH_SIDECAR_TOKEN -ErrorAction SilentlyContinue

$url = "http://127.0.0.1:$Port/app/"
Write-Host "Claim Power House web app: $url"
Write-Host "LLM: OpenAI / $env:CPH_LLM_MODEL"
Write-Host "Press Ctrl+C to stop."

Push-Location $repoRoot
try {
    & $PythonPath -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
}
exit $LASTEXITCODE
