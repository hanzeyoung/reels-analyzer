$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\JEONGMIN\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

$env:PYTHONPATH = "$root\.python-test-packages;$root"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:TMP = "$root\.tmp"
$env:TEMP = "$root\.tmp"

New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null

& $python -m pytest -q
exit $LASTEXITCODE
