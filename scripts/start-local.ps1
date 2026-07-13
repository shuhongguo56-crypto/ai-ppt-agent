param(
  [ValidateSet("fake", "ollama", "openai", "cascade")]
  [string]$ModelBackend = $(if ($env:AI_PPT_MODEL_BACKEND) { $env:AI_PPT_MODEL_BACKEND } else { "cascade" }),
  [string]$OllamaTextModel = $(if ($env:AI_PPT_OLLAMA_TEXT_MODEL) { $env:AI_PPT_OLLAMA_TEXT_MODEL } else { "qwen2.5:7b" }),
  [string]$OpenAIApiKey = $env:AI_PPT_OPENAI_API_KEY,
  [string]$GeminiApiKey = $env:AI_PPT_GEMINI_API_KEY,
  [string]$OpenRouterApiKey = $env:AI_PPT_OPENROUTER_API_KEY,
  [string]$GroqApiKey = $env:AI_PPT_GROQ_API_KEY,
  [string]$CompatibleBaseUrl = $(if ($env:AI_PPT_COMPATIBLE_BASE_URL) { $env:AI_PPT_COMPATIBLE_BASE_URL } else { "http://127.0.0.1:1234/v1" }),
  [string]$CompatibleTextModel = $(if ($env:AI_PPT_COMPATIBLE_TEXT_MODEL) { $env:AI_PPT_COMPATIBLE_TEXT_MODEL } else { "local-model" })
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$CodexRuntime = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies"
if (Test-Path -LiteralPath $CodexRuntime) {
  $runtimePaths = @(
    (Join-Path $CodexRuntime "python"),
    (Join-Path $CodexRuntime "node\bin"),
    (Join-Path $CodexRuntime "bin")
  ) | Where-Object { Test-Path -LiteralPath $_ }
  $env:Path = (($runtimePaths + @($env:Path)) -join ";")
}

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
$PnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
  throw "Python was not found. Install Python or run this from Codex Desktop where the bundled runtime is available."
}
if (-not $PnpmCommand) {
  throw "pnpm was not found. Install pnpm or run this from Codex Desktop where the bundled runtime is available."
}

function Quote-PowerShellPath([string]$Path) {
  return "'" + $Path.Replace("'", "''") + "'"
}

Write-Host "Starting AI PPT Agent local API and Web..." -ForegroundColor Cyan
Write-Host "API: http://127.0.0.1:8000" -ForegroundColor Gray
Write-Host "Web: http://localhost:3001/workflow" -ForegroundColor Gray
Write-Host "Model backend: $ModelBackend" -ForegroundColor Gray

$env:PYTHONPATH = "apps/api;packages/contracts/python;packages/skills/python"
$env:AI_PPT_DATABASE_PATH = "D:\Codex\Workspaces\ai-ppt-agent-runtime\ai-ppt-runtime.db"
$env:AI_PPT_ASSET_PATH = "D:\Codex\Workspaces\ai-ppt-agent-runtime\assets"
$env:AI_PPT_MODEL_BACKEND = $ModelBackend
$env:AI_PPT_OLLAMA_TEXT_MODEL = $OllamaTextModel
$env:AI_PPT_COMPATIBLE_BASE_URL = $CompatibleBaseUrl
$env:AI_PPT_COMPATIBLE_TEXT_MODEL = $CompatibleTextModel
$env:AI_PPT_IMAGE_SEARCH_ENABLED = $(if ($env:AI_PPT_IMAGE_SEARCH_ENABLED) { $env:AI_PPT_IMAGE_SEARCH_ENABLED } else { "true" })
$env:AI_PPT_POLLINATIONS_IMAGE_ENABLED = $(if ($env:AI_PPT_POLLINATIONS_IMAGE_ENABLED) { $env:AI_PPT_POLLINATIONS_IMAGE_ENABLED } else { "true" })
$env:AI_PPT_POLLINATIONS_IMAGE_MODEL = $(if ($env:AI_PPT_POLLINATIONS_IMAGE_MODEL) { $env:AI_PPT_POLLINATIONS_IMAGE_MODEL } else { "flux" })
if ($OpenAIApiKey) {
  $env:AI_PPT_OPENAI_API_KEY = $OpenAIApiKey
}
if ($GeminiApiKey) {
  $env:AI_PPT_GEMINI_API_KEY = $GeminiApiKey
}
if ($OpenRouterApiKey) {
  $env:AI_PPT_OPENROUTER_API_KEY = $OpenRouterApiKey
}
if ($GroqApiKey) {
  $env:AI_PPT_GROQ_API_KEY = $GroqApiKey
}
$env:AI_PPT_ALLOWED_ORIGINS = '["http://localhost:3000","http://127.0.0.1:3000","http://localhost:3001","http://127.0.0.1:3001"]'
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000/api"

if ($ModelBackend -eq "ollama" -and -not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  Write-Warning "Ollama command was not found. Install Ollama and run: ollama pull $OllamaTextModel"
}
if ($ModelBackend -eq "cascade") {
  Write-Host "Cascade order: OpenAI key -> Gemini key -> OpenRouter key -> Groq key -> OpenAI-compatible local -> Ollama -> enhanced local fallback" -ForegroundColor Gray
  Write-Host "Image order: open web search -> OpenAI Image if keyed -> Pollinations FLUX free fallback -> local PNG fallback" -ForegroundColor Gray
  if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Warning "Ollama command was not found. Cascade can still use keys, LM Studio, or fallback mode."
  }
}
if ($ModelBackend -eq "openai" -and -not $env:AI_PPT_OPENAI_API_KEY -and -not $env:OPENAI_API_KEY) {
  Write-Warning "OpenAI mode is selected but no API key is configured."
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $env:AI_PPT_DATABASE_PATH) | Out-Null
New-Item -ItemType Directory -Force -Path $env:AI_PPT_ASSET_PATH | Out-Null

$pythonExe = Quote-PowerShellPath $PythonCommand.Source
$pnpmExe = Quote-PowerShellPath $PnpmCommand.Source
$api = Start-Process -PassThru -NoNewWindow powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "& $pythonExe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000"
)
$web = Start-Process -PassThru -NoNewWindow powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "& $pnpmExe --filter @ai-ppt/web dev --hostname 127.0.0.1 --port 3001"
)

Write-Host "Started API PID $($api.Id), Web PID $($web.Id). Close their shells to stop." -ForegroundColor Green
