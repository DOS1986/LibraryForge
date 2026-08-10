$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $repoRoot "backend"
$frontendRoot = Join-Path $repoRoot "frontend"
$runtimeRoot = Join-Path $repoRoot "runtime"
$restartFile = Join-Path $runtimeRoot "restart.request"

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
Remove-Item -Force $restartFile -ErrorAction SilentlyContinue

$env:LIBRARYFORGE_RESTART_ENABLED = "true"
$env:LIBRARYFORGE_RESTART_FILE = $restartFile

function Start-LibraryForgeBackend {
    Write-Host "[LibraryForge] Starting Django..." -ForegroundColor Cyan
    return Start-Process -FilePath "uv" -ArgumentList @(
        "run", "python", "manage.py", "runserver", "127.0.0.1:8000"
    ) -WorkingDirectory $backendRoot -PassThru
}

function Start-LibraryForgeWorker {
    Write-Host "[LibraryForge] Starting scan worker..." -ForegroundColor Cyan
    return Start-Process -FilePath "uv" -ArgumentList @(
        "run", "python", "manage.py", "run_scan_worker"
    ) -WorkingDirectory $backendRoot -PassThru
}

function Start-LibraryForgeFrontend {
    Write-Host "[LibraryForge] Starting Vite..." -ForegroundColor Cyan
    return Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") `
        -WorkingDirectory $frontendRoot -PassThru
}

function Stop-LibraryForgeProcess {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$Name
    )

    if ($null -eq $Process) { return }

    try {
        $Process.Refresh()
        if (-not $Process.HasExited) {
            Write-Host "[LibraryForge] Stopping $Name..." -ForegroundColor Yellow
            & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
        }
    }
    catch {
        Write-Host "[LibraryForge] $Name was already stopped." -ForegroundColor DarkGray
    }
}

function Wait-LibraryForgeWorkerForRestart {
    param([System.Diagnostics.Process]$Worker)

    if ($null -eq $Worker) { return }

    $announced = $false
    while ($true) {
        try {
            $Worker.Refresh()
            if ($Worker.HasExited) { break }
        }
        catch { break }

        if (-not $announced) {
            Write-Host "[LibraryForge] Waiting for the scan worker to finish its current scan..." -ForegroundColor Magenta
            $announced = $true
        }

        Start-Sleep -Milliseconds 250
    }
}

function Restart-LibraryForge {
    param(
        [System.Diagnostics.Process]$Backend,
        [System.Diagnostics.Process]$Frontend,
        [System.Diagnostics.Process]$Worker
    )

    # The worker watches restart.request itself. Leave the file in place until
    # the worker has finished any current scan and exited cleanly.
    Wait-LibraryForgeWorkerForRestart -Worker $Worker

    Stop-LibraryForgeProcess -Process $Frontend -Name "Vite"
    Stop-LibraryForgeProcess -Process $Backend -Name "Django"

    Remove-Item -Force $restartFile -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 750

    $newBackend = Start-LibraryForgeBackend
    $newWorker = Start-LibraryForgeWorker
    $newFrontend = Start-LibraryForgeFrontend

    return @($newBackend, $newFrontend, $newWorker)
}

$backend = $null
$frontend = $null
$worker = $null

try {
    $backend = Start-LibraryForgeBackend
    $worker = Start-LibraryForgeWorker
    $frontend = Start-LibraryForgeFrontend

    Write-Host ""
    Write-Host "LibraryForge development supervisor is running." -ForegroundColor Green
    Write-Host "Backend:     http://127.0.0.1:8000"
    Write-Host "Frontend:    http://127.0.0.1:5173"
    Write-Host "Scan worker: supervised"
    Write-Host "Restart requests: $restartFile"
    Write-Host "Press Ctrl+C here to stop the development stack."
    Write-Host ""

    while ($true) {
        if (Test-Path $restartFile) {
            Write-Host "[LibraryForge] Restart requested from the web UI." -ForegroundColor Magenta

            $processes = Restart-LibraryForge `
                -Backend $backend `
                -Frontend $frontend `
                -Worker $worker

            $backend = $processes[0]
            $frontend = $processes[1]
            $worker = $processes[2]
            continue
        }

        $backend.Refresh()
        if ($backend.HasExited) {
            Write-Host "[LibraryForge] Django exited; starting it again." -ForegroundColor Yellow
            $backend = Start-LibraryForgeBackend
        }

        $frontend.Refresh()
        if ($frontend.HasExited) {
            Write-Host "[LibraryForge] Vite exited; starting it again." -ForegroundColor Yellow
            $frontend = Start-LibraryForgeFrontend
        }

        $worker.Refresh()
        if ($worker.HasExited) {
            Write-Host "[LibraryForge] Scan worker exited; starting it again." -ForegroundColor Yellow
            $worker = Start-LibraryForgeWorker
        }

        Start-Sleep -Milliseconds 500
    }
}
finally {
    Stop-LibraryForgeProcess -Process $frontend -Name "Vite"
    Stop-LibraryForgeProcess -Process $backend -Name "Django"
    Stop-LibraryForgeProcess -Process $worker -Name "Scan worker"
    Remove-Item -Force $restartFile -ErrorAction SilentlyContinue
}
