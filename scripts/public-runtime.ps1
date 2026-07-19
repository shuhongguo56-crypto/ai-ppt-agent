param(
  [string]$ApiOrigin = "",
  [string]$Repository = "shuhongguo56-crypto/ai-ppt-agent",
  [string]$PagesBranch = "main"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = "D:\Codex\Workspaces\ai-ppt-public-runtime"
$StatePath = Join-Path $RuntimeRoot "state.json"
$ApiOutLog = Join-Path $RuntimeRoot "api.out.log"
$ApiErrLog = Join-Path $RuntimeRoot "api.err.log"
$TunnelOutLog = Join-Path $RuntimeRoot "cloudflared.out.log"
$TunnelErrLog = Join-Path $RuntimeRoot "cloudflared.err.log"
$PublicEntry = "https://shuhongguo56-crypto.github.io/ai-ppt-agent/live/"
$LocalRuntimeStatus = "http://127.0.0.1:8000/api/runtime/status"

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null

function Test-Endpoint([string]$Url) {
  if (-not $Url) { return $false }
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 12
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Normalize-Origin([string]$Value) {
  return $Value.Trim().TrimEnd("/") -replace "/api$", ""
}

function Start-LocalApi {
  if (Test-Endpoint $LocalRuntimeStatus) { return }

  $python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
  if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
  }

  $env:PYTHONPATH = @(
    (Join-Path $RepoRoot "apps\api"),
    (Join-Path $RepoRoot "packages\contracts\python"),
    (Join-Path $RepoRoot "packages\skills\python")
  ) -join ";"
  # Keep the public runtime on the repository's established database and asset
  # store so a supervisor restart never makes an in-progress customer project
  # appear to disappear.
  $env:AI_PPT_DATABASE_PATH = Join-Path $RepoRoot ".local\ai-ppt.db"
  $env:AI_PPT_ASSET_PATH = Join-Path $RepoRoot ".local\assets"
  $env:AI_PPT_MODEL_BACKEND = "cascade"
  $env:AI_PPT_IMAGE_SEARCH_ENABLED = "true"
  $env:AI_PPT_POLLINATIONS_IMAGE_ENABLED = "true"
  $env:AI_PPT_POLLINATIONS_IMAGE_MODEL = "flux"
  # Pollinations' free endpoint is materially more reliable when requests are
  # serialized; research mode favors completion quality over one-minute speed.
  $env:AI_PPT_IMAGE_RESOLUTION_WORKERS = "1"
  $env:AI_PPT_IMAGE_GENERATION_RETRY_ROUNDS = "3"
  $env:AI_PPT_EXPERT_IMAGE_MIN_LONG_EDGE = "1920"
  $env:AI_PPT_EXPERT_IMAGE_MIN_SHORT_EDGE = "1080"
  $env:AI_PPT_EXPERT_KEY_IMAGE_MIN_LONG_EDGE = "3840"
  $env:AI_PPT_EXPERT_KEY_IMAGE_MIN_SHORT_EDGE = "2160"
  $realEsrgan = "D:\Codex\Workspaces\ai-ppt-tools\realesrgan-ncnn-vulkan-20220424-windows\realesrgan-ncnn-vulkan.exe"
  if (Test-Path -LiteralPath $realEsrgan) {
    $env:AI_PPT_REALESRGAN_ENABLED = "true"
    $env:AI_PPT_REALESRGAN_EXECUTABLE = $realEsrgan
    $env:AI_PPT_REALESRGAN_MODEL = "realesrgan-x4plus"
    $env:AI_PPT_REALESRGAN_TIMEOUT_SECONDS = "180"
  }
  $env:AI_PPT_TESSDATA_PATH = "D:\Codex\Downloads\tessdata"
  $env:AI_PPT_ALLOWED_ORIGINS = '["https://shuhongguo56-crypto.github.io","https://humanizeppt-studio.almond-gleam-4876.chatgpt.site","http://localhost:3001","http://127.0.0.1:3001"]'

  Start-Process -FilePath $python -WorkingDirectory $RepoRoot -WindowStyle Hidden `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "127.0.0.1", "--port", "8000") `
    -RedirectStandardOutput $ApiOutLog -RedirectStandardError $ApiErrLog | Out-Null

  for ($attempt = 0; $attempt -lt 30; $attempt += 1) {
    Start-Sleep -Seconds 1
    if (Test-Endpoint $LocalRuntimeStatus) { return }
  }
  throw "Local AI PPT API did not become ready. See $ApiErrLog"
}

function Read-StateOrigin {
  if (-not (Test-Path -LiteralPath $StatePath)) { return "" }
  try {
    return Normalize-Origin ((Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json).apiOrigin)
  } catch {
    return ""
  }
}

function Start-QuickTunnel {
  $cloudflared = (Get-Command cloudflared -ErrorAction Stop).Source
  Remove-Item -LiteralPath $TunnelOutLog, $TunnelErrLog -Force -ErrorAction SilentlyContinue
  Start-Process -FilePath $cloudflared -WindowStyle Hidden `
    -ArgumentList @("tunnel", "--url", "http://127.0.0.1:8000", "--no-autoupdate") `
    -RedirectStandardOutput $TunnelOutLog -RedirectStandardError $TunnelErrLog | Out-Null

  for ($attempt = 0; $attempt -lt 45; $attempt += 1) {
    Start-Sleep -Seconds 1
    $combined = @(
      (Get-Content -LiteralPath $TunnelOutLog -Raw -ErrorAction SilentlyContinue),
      (Get-Content -LiteralPath $TunnelErrLog -Raw -ErrorAction SilentlyContinue)
    ) -join "`n"
    $match = [regex]::Match($combined, "https://[a-z0-9-]+\.trycloudflare\.com")
    if ($match.Success) {
      $origin = Normalize-Origin $match.Value
      if (Test-Endpoint "$origin/api/runtime/status") { return $origin }
    }
  }
  throw "Cloudflare tunnel did not become ready. See $TunnelErrLog"
}

function Publish-PagesEntry([string]$Origin) {
  $encodedOrigin = [uri]::EscapeDataString($Origin)
  $target = "/ai-ppt-agent/workflow/?api=$encodedOrigin"
  $html = @"
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta http-equiv="refresh" content="0; url=$target" />
    <link rel="canonical" href="$PublicEntry" />
    <title>HumanizePPT</title>
  </head>
  <body>
    <p>正在打开 HumanizePPT：<a href="$target">进入网站</a></p>
  </body>
</html>
"@

  # Keep the redirect fallback readable even when this script is opened by a
  # legacy Windows host that interprets the here-string with the wrong codepage.
  $html = [regex]::Replace(
    $html,
    "(?s)<body>.*?</body>",
    ('<body><p>&#27491;&#22312;&#25171;&#24320; HumanizePPT&#65307;<a href="{0}">&#36827;&#20837;&#32593;&#31449;</a></p></body>' -f $target)
  )

  $content = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($html))
  $metadata = gh api "repos/$Repository/contents/live/index.html?ref=$PagesBranch" | ConvertFrom-Json
  $remoteHtml = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($metadata.content -replace "\s", "")))
  if ($remoteHtml -eq $html) { return }

  gh api --method PUT "repos/$Repository/contents/live/index.html" `
    -f "message=chore: refresh public AI PPT endpoint" `
    -f "content=$content" `
    -f "sha=$($metadata.sha)" `
    -f "branch=$PagesBranch" | Out-Null
}

Start-LocalApi

$origin = if ($ApiOrigin) { Normalize-Origin $ApiOrigin } else { Read-StateOrigin }
if (-not (Test-Endpoint "$origin/api/runtime/status")) {
  $origin = Start-QuickTunnel
}

Publish-PagesEntry $origin
[ordered]@{
  apiOrigin = $origin
  publicEntry = $PublicEntry
  updatedAt = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding utf8

Write-Output "Public entry: $PublicEntry"
Write-Output "Active API: $origin"
