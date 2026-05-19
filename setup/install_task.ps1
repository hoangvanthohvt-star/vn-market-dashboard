# install_task.ps1 — Registers a Windows Task Scheduler task that runs
# run_daily.ps1 once at login (or at 06:45 ICT if you prefer a time trigger).
#
# Run once as Administrator:
#   powershell -ExecutionPolicy Bypass -File .\install_task.ps1
#
# To use a fixed-time trigger instead of "at login", change $trigger below.

param(
    [string]$RepoPath = "$env:USERPROFILE\vn-market-dashboard",
    [string]$TaskName = "VN-Market-Dashboard-Daily-Update"
)

$scriptPath = Join-Path $RepoPath "setup\run_daily.ps1"

# Trigger: run at logon (change to New-ScheduledTaskTrigger -Daily -At "06:45" for time-based)
$trigger = New-ScheduledTaskTrigger -AtLogOn

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -NonInteractive -File `"$scriptPath`" -RepoPath `"$RepoPath`"" `
    -WorkingDirectory $RepoPath

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Trigger $trigger `
    -Action $action `
    -Settings $settings `
    -Principal $principal `
    -Force

Write-Host ""
Write-Host "Task '$TaskName' registered successfully." -ForegroundColor Green
Write-Host "It will run run_daily.ps1 each time you log in to Windows." -ForegroundColor Green
Write-Host ""
Write-Host "To change to a fixed time (e.g. 06:45 daily), edit the `$trigger line in this script." -ForegroundColor Yellow
