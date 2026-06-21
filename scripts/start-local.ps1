$ErrorActionPreference = "Stop"

Write-Host "Starting AI PPT Agent local API and Web..." -ForegroundColor Cyan
Write-Host "API: http://127.0.0.1:8000" -ForegroundColor Gray
Write-Host "Web: http://localhost:3000/workflow" -ForegroundColor Gray

$api = Start-Process -PassThru -NoNewWindow powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "python -m uvicorn app.main:app --app-dir apps/api --reload"
)
$web = Start-Process -PassThru -NoNewWindow powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "pnpm --filter @ai-ppt/web dev"
)

Write-Host "Started API PID $($api.Id), Web PID $($web.Id). Close their shells to stop." -ForegroundColor Green
