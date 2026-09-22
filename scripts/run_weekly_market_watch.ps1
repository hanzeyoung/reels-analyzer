$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\JEONGMIN\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

$env:PYTHONPATH = "$root\.python-test-packages;$root"
$env:PYTHONDONTWRITEBYTECODE = "1"

Set-Location $root
& $python "$PSScriptRoot\run_weekly_market_watch.py"
