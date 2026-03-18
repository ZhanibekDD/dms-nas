# DMS-NAS — Autostart via Windows Task Scheduler
# Run as Administrator: .\autostart\install_windows_tasks.ps1
# Creates two tasks: DMS-Bot and DMS-Web (start at logon, restart on failure)

param(
    [string]$DmsRoot = $PSScriptRoot + "\..",
    [string]$UserName = $env:USERNAME
)

$DmsRoot = Resolve-Path $DmsRoot

Write-Host "=== DMS-NAS Windows Task Scheduler Setup ===" -ForegroundColor Cyan
Write-Host "Root: $DmsRoot" -ForegroundColor Gray

# ── Helper ────────────────────────────────────────────────────────────────────
function Register-DmsTask {
    param($TaskName, $ScriptPath, $WorkDir, $Description)

    $action  = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-WindowStyle Hidden -NonInteractive -File `"$ScriptPath`"" `
        -WorkingDirectory $WorkDir

    # At system startup + at logon
    $trigger = @(
        New-ScheduledTaskTrigger -AtStartup,
        New-ScheduledTaskTrigger -AtLogOn -User $UserName
    )

    $settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -RestartCount 5 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Hours 0)  # no limit

    $principal = New-ScheduledTaskPrincipal `
        -UserId $UserName `
        -LogonType Interactive `
        -RunLevel Highest

    # Remove existing task if present
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $Description | Out-Null

    Write-Host "  ✅ Registered: $TaskName" -ForegroundColor Green
}

# ── Bot task ──────────────────────────────────────────────────────────────────
$botScript = Join-Path $DmsRoot "start_bot.ps1"
Register-DmsTask `
    -TaskName   "DMS-Bot" `
    -ScriptPath $botScript `
    -WorkDir    $DmsRoot `
    -Description "DMS-NAS Telegram Bot"

# ── Web Admin task ────────────────────────────────────────────────────────────
$webScript = Join-Path $DmsRoot "apps\web_admin\start_production.ps1"
Register-DmsTask `
    -TaskName   "DMS-Web" `
    -ScriptPath $webScript `
    -WorkDir    (Join-Path $DmsRoot "apps\web_admin") `
    -Description "DMS-NAS Django Web Admin"

Write-Host ""
Write-Host "=== Done! ===" -ForegroundColor Green
Write-Host "Check Task Scheduler → Task Scheduler Library for DMS-Bot and DMS-Web"
Write-Host "Start now: Start-ScheduledTask -TaskName DMS-Bot"
Write-Host "           Start-ScheduledTask -TaskName DMS-Web"
