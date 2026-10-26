$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed. Install Python 3.11 or newer.' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Push-Location frontend
try {
    npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
Write-Host 'Setup complete. Run: powershell -ExecutionPolicy Bypass -File .\start.ps1'
