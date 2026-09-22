$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\JEONGMIN\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$port = if ($args.Count -ge 1) { $args[0] } else { "8501" }
$coachPort = "8502"

$env:PYTHONPATH = "$root\.python-test-packages;$root"
$env:PYTHONDONTWRITEBYTECODE = "1"

Set-Location $root

$coachListening = Get-NetTCPConnection -LocalPort $coachPort -State Listen -ErrorAction SilentlyContinue
if (-not $coachListening) {
    Start-Process -FilePath $python `
        -ArgumentList @("-m", "http.server", $coachPort, "--bind", "0.0.0.0", "--directory", "$root\mobile_coach") `
        -WorkingDirectory $root `
        -WindowStyle Hidden
}

$workerRunning = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -like "*scripts\run_job_worker.py*"
    } |
    Select-Object -First 1
if (-not $workerRunning) {
    Start-Process -FilePath $python `
        -ArgumentList @("scripts\run_job_worker.py") `
        -WorkingDirectory $root `
        -WindowStyle Hidden
}

& $python -m streamlit run main.py --global.developmentMode false --server.address 0.0.0.0 --server.port $port --server.headless true
