$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Run setup.ps1 first.' }
if (-not (Test-Path 'frontend\dist\index.html')) { throw 'Build the frontend using setup.ps1 first.' }
Write-Host 'Open http://127.0.0.1:8002 - press Ctrl+C to stop.'
& $projectPython -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8002
