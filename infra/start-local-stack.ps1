# Starts the FaithBridge local stack: API (8000), AI service (8200), web (3000).
# Idempotent - anything already listening is left alone, so it is safe to re-run.
#
#   powershell -ExecutionPolicy Bypass -File infra\start-local-stack.ps1
#
# Logs land in infra\logs\. Run it from a normal terminal; the services are
# independent processes and keep running after this script exits.

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Start-IfDown {
    param([int]$Port, [string]$Name, [string]$WorkDir, [string]$File, [string[]]$FileArgs)

    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        Write-Host "[ok] $Name already listening on :$Port"
        return
    }
    Start-Process -FilePath $File `
        -ArgumentList $FileArgs `
        -WorkingDirectory $WorkDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir "$Name.out.log") `
        -RedirectStandardError (Join-Path $logDir "$Name.err.log")
    Write-Host "[start] $Name -> :$Port"
}

Start-IfDown -Port 8000 -Name "api" -WorkDir (Join-Path $root "apps\api") `
    -File $py -FileArgs @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000")

Start-IfDown -Port 8200 -Name "ai" -WorkDir (Join-Path $root "apps\ai") `
    -File $py -FileArgs @("-m", "uvicorn", "faithbridge_ai.main:app", "--host", "127.0.0.1", "--port", "8200")

Start-IfDown -Port 3000 -Name "web" -WorkDir (Join-Path $root "apps\web") `
    -File "npm.cmd" -FileArgs @("run", "dev")

# Give the servers a moment, then report.
$deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Seconds 5
    $up = @(3000, 8000, 8200) | Where-Object {
        Get-NetTCPConnection -State Listen -LocalPort $_ -ErrorAction SilentlyContinue
    }
} until ($up.Count -eq 3 -or (Get-Date) -gt $deadline)

if ($up.Count -eq 3) {
    Write-Host "[ok] all three services listening (http://localhost:3000)"
} else {
    $missing = @(3000, 8000, 8200) | Where-Object { $up -notcontains $_ }
    Write-Warning "not up yet: $($missing -join ', ') - check infra\logs\*.err.log"
}
