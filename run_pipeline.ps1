param(
    [string]$Keyword = "",
    [string]$BusinessType = "",
    [int]$TopN = 5,
    [int]$MaxItems = 20,
    [int]$CandidateMultiplier = 3,
    [string]$SaveDir = "videos",
    [switch]$SkipReport
)

$ErrorActionPreference = "Stop"

$python = "C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.11_3.11.2544.0_x64__qbz5n2kfra8p0\python3.11.exe"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location $root
$env:PYTHONPATH = "$root\.python-packages;$root;$root\files"
$env:PYTHONUTF8 = "1"

if ([string]::IsNullOrWhiteSpace($Keyword)) {
    $Keyword = Read-Host "검색 키워드를 입력하세요 (예: 성수동카페)"
}
if ([string]::IsNullOrWhiteSpace($Keyword)) {
    throw "검색 키워드가 필요합니다."
}

if ([string]::IsNullOrWhiteSpace($BusinessType)) {
    $BusinessType = Read-Host "업종을 입력하세요 (Enter: 카페)"
}
if ([string]::IsNullOrWhiteSpace($BusinessType)) {
    $BusinessType = "카페"
}

$argsList = @(
    "run_pipeline.py",
    "--keyword", $Keyword,
    "--business-type", $BusinessType,
    "--top-n", $TopN,
    "--max-items", $MaxItems,
    "--candidate-multiplier", $CandidateMultiplier,
    "--save-dir", $SaveDir
)

if ($SkipReport) {
    $argsList += "--skip-report"
}

& $python @argsList