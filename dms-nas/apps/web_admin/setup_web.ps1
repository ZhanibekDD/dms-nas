# DMS-NAS Web Admin — Setup Script (Windows PowerShell)
# Run from dms-nas/ root:  .\apps\web_admin\setup_web.ps1

Set-Location $PSScriptRoot\..\..\

Write-Host "=== DMS-NAS Web Admin Setup ===" -ForegroundColor Cyan

# Create venv if needed
if (-not (Test-Path "venv_web")) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv venv_web
}

# Activate and install
Write-Host "Installing web dependencies..." -ForegroundColor Yellow
& ".\venv_web\Scripts\pip.exe" install -r "apps\web_admin\requirements_web.txt"
& ".\venv_web\Scripts\pip.exe" install waitress  # Windows WSGI server

# Set DJANGO_SETTINGS_MODULE and run migrations (only Django auth tables)
$env:DJANGO_SETTINGS_MODULE = "web_admin.settings"

Set-Location "apps\web_admin"

Write-Host "Running Django migrations (auth only)..." -ForegroundColor Yellow
& "..\..\venv_web\Scripts\python.exe" manage.py migrate --run-syncdb

Write-Host "Collecting static files..." -ForegroundColor Yellow
& "..\..\venv_web\Scripts\python.exe" manage.py collectstatic --noinput

Write-Host ""
Write-Host "Creating superuser (login: admin / password from config)..." -ForegroundColor Yellow
& "..\..\venv_web\Scripts\python.exe" manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@dms.local', 'Lytgh8989.')
    print('Superuser created: admin / Lytgh8989.')
else:
    print('Superuser already exists')
"

# Create Django auth groups
& "..\..\venv_web\Scripts\python.exe" manage.py shell -c "
from django.contrib.auth.models import Group
for name in ['admin','pto','tb','buh','prorab','viewer']:
    Group.objects.get_or_create(name=name)
    print(f'Group: {name}')
"

Set-Location ..\..

Write-Host ""
Write-Host "=== Setup complete! ===" -ForegroundColor Green
Write-Host "Run web admin:  .\apps\web_admin\start_production.ps1" -ForegroundColor Cyan
