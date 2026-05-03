param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"

function Get-ListeningPids {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        return @()
    }

    return @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Stop-ListeningProcesses {
    param([int]$Port)

    $pids = Get-ListeningPids -Port $Port
    foreach ($procId in $pids) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Write-Output "Stopped PID $procId on port ${Port}"
        }
        catch {
            Write-Output "Could not stop PID $procId on port ${Port}: $($_.Exception.Message)"
        }
    }

    if (-not $pids) {
        Write-Output "No listener on port ${Port}"
    }
}

function Show-PortStatus {
    param([int[]]$Ports)

    foreach ($port in $Ports) {
        $pids = Get-ListeningPids -Port $port
        if (-not $pids) {
            Write-Output "Port ${port}: free"
            continue
        }

        foreach ($procId in $pids) {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Output "Port ${port}: PID $procId ($($proc.ProcessName))"
            }
            else {
                Write-Output "Port ${port}: PID $procId"
            }
        }
    }
}

function Wait-PortReady {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 15
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ((Get-ListeningPids -Port $Port).Count -gt 0) {
            return $true
        }
    }

    return $false
}

switch ($Action) {
    "stop" {
        Stop-ListeningProcesses -Port 8000
        Stop-ListeningProcesses -Port 5173
        Show-PortStatus -Ports @(8000, 5173)
    }

    "status" {
        Show-PortStatus -Ports @(8000, 5173)
    }

    "start" {
        if (-not (Test-Path $PythonExe)) {
            throw "Python virtual environment not found at $PythonExe"
        }

        Stop-ListeningProcesses -Port 8000
        Stop-ListeningProcesses -Port 5173

        $backendCommand = "set PYTHONPATH=.&& `"$PythonExe`" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
        $backendProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $backendCommand -WorkingDirectory $BackendDir -PassThru

        $frontendProcess = Start-Process -FilePath "npx.cmd" -ArgumentList "vite", "--host", "127.0.0.1", "--port", "5173" -WorkingDirectory $FrontendDir -PassThru

        $backendReady = Wait-PortReady -Port 8000 -TimeoutSeconds 20
        $frontendReady = Wait-PortReady -Port 5173 -TimeoutSeconds 20

        Write-Output "Started backend PID $($backendProcess.Id) on 127.0.0.1:8000"
        Write-Output "Started frontend PID $($frontendProcess.Id) on 127.0.0.1:5173"
        Write-Output "Backend ready: $backendReady"
        Write-Output "Frontend ready: $frontendReady"
        Write-Output "Use: ./scripts/dev-server.ps1 status"
    }
}
