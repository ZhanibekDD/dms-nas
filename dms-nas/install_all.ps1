# DMS-NAS — Full installation script
# Run once from dms-nas/ root: .\install_all.ps1

Set-Location $PSScriptRoot
Write-Host "=== DMS-NAS Full Install ===" -ForegroundColor Cyan

# ── Bot venv ──────────────────────────────────────────────────────────────────
Write-Host "`n[1/3] Setting up Bot environment..." -ForegroundColor Yellow
if (-not (Test-Path "venv_bot")) {
    python -m venv venv_bot
}
& ".\venv_bot\Scripts\pip.exe" install --upgrade pip | Out-Null
& ".\venv_bot\Scripts\pip.exe" install -r "apps\bot\requirements_bot.txt"

# ── Web venv ──────────────────────────────────────────────────────────────────
Write-Host "`n[2/3] Setting up Web Admin environment..." -ForegroundColor Yellow
if (-not (Test-Path "venv_web")) {
    python -m venv venv_web
}
& ".\venv_web\Scripts\pip.exe" install --upgrade pip | Out-Null
& ".\venv_web\Scripts\pip.exe" install -r "apps\web_admin\requirements_web.txt"

# ── Django setup ──────────────────────────────────────────────────────────────
Write-Host "`n[3/3] Setting up Django..." -ForegroundColor Yellow
$env:DJANGO_SETTINGS_MODULE = "web_admin.settings"
Set-Location "apps\web_admin"

& "..\..\venv_web\Scripts\python.exe" manage.py migrate --run-syncdb
& "..\..\venv_web\Scripts\python.exe" manage.py collectstatic --noinput

& "..\..\venv_web\Scripts\python.exe" manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@dms.local', 'Lytgh8989.')
    print('Superuser created: admin / Lytgh8989.')
else:
    print('Superuser already exists.')

from django.contrib.auth.models import Group
for name in ['admin','pto','tb','buh','prorab','viewer']:
    g, created = Group.objects.get_or_create(name=name)
    print(f'Group {name}: {\"created\" if created else \"exists\"}')
"

Set-Location ..\..

Write-Host "`n=== Installation complete! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Start Bot:      .\start_bot.ps1" -ForegroundColor Cyan
Write-Host "Start Web:      .\apps\web_admin\start_production.ps1" -ForegroundColor Cyan
Write-Host "Web Admin URL:  http://localhost:8000/admin" -ForegroundColor Cyan
Write-Host "Login:          admin / Lytgh8989." -ForegroundColor Cyan
Write-Host ""
Write-Host "Sprint 10 — Postgres migration:" -ForegroundColor Yellow
Write-Host "  1. docker compose up -d" -ForegroundColor White
Write-Host "  2. python migrate_sqlite_to_postgres.py" -ForegroundColor White
Write-Host "  3. set DMS_DB_MODE=postgres" -ForegroundColor White
Write-Host "  4. Restart bot and web" -ForegroundColor White
