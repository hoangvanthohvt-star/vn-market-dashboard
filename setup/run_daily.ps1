# run_daily.ps1 — Runs the VN Market Dashboard daily update via Claude Code.
# Intended to be called by Windows Task Scheduler at login or on a schedule.
#
# Usage:
#   .\run_daily.ps1
#   .\run_daily.ps1 -RepoPath "D:\projects\vn-market-dashboard"

param(
    [string]$RepoPath = "$env:USERPROFILE\vn-market-dashboard"
)

Set-Location $RepoPath

# Pull latest changes before running
git pull --ff-only origin main 2>&1 | Out-Null

# Run the daily update headlessly.
# Claude will read CLAUDE.md and execute steps 1-8 automatically.
claude --dangerously-skip-permissions -p "Run the daily update as described in CLAUDE.md, steps 1 through 8. Today's date is $(Get-Date -Format 'yyyy-MM-dd')."
