$ErrorActionPreference = "Stop"

$taskName = "ReelsAnalyzerWeeklyMarketWatch"
$runner = Join-Path $PSScriptRoot "run_weekly_market_watch.ps1"
$action = New-ScheduledTaskAction -Execute "pwsh.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Weekly reels market snapshot and alert run" -Force
Write-Host "Installed scheduled task: $taskName"
