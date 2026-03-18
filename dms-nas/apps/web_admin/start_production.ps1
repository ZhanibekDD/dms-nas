# Start DMS-NAS Web Admin in production mode (Windows)
# Run from dms-nas/ root: .\apps\web_admin\start_production.ps1

Set-Location $PSScriptRoot\..\..\

$env:DJANGO_SETTINGS_MODULE = "web_admin.settings"

Write-Host "Starting DMS-NAS Web Admin on http://0.0.0.0:8000" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow

Set-Location "apps\web_admin"
& "..\..\venv_web\Scripts\python.exe" serve_prod.py
