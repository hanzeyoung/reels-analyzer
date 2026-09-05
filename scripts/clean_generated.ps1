$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$targets = @(
    "reports",
    "videos_verify_keyword",
    "videos_verify_keyword_after_fix",
    "videos_verify_keyword_logged",
    "videos_verify_keyword_strict",
    "videos_verify_keyword_final",
    "__pycache__",
    "app\__pycache__",
    "app\api\__pycache__",
    "app\core\__pycache__",
    "app\db\__pycache__",
    "files\__pycache__"
)

foreach ($relative in $targets) {
    $path = Join-Path $root $relative
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
        Write-Host "removed $relative"
    }
}

Write-Host "generated artifacts cleaned"