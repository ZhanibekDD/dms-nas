# Start DMS-NAS Telegram Bot
# Run from dms-nas/ root

Set-Location $PSScriptRoot

if (-not (Test-Path "venv_bot")) {
    Write-Host "Creating bot virtual environment..." -ForegroundColor Yellow
    python -m venv venv_bot
    & ".\venv_bot\Scripts\pip.exe" install -r "apps\bot\requirements_bot.txt"
}

Write-Host "Starting DMS-NAS Telegram Bot..." -ForegroundColor Green
& ".\venv_bot\Scripts\python.exe" -m apps.bot.bot
