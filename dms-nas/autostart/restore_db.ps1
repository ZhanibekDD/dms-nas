# DMS-NAS — DB Restore from NAS backup
# Usage: .\autostart\restore_db.ps1 -BackupFile dms_20251231.db
# Downloads backup from NAS and replaces current dms.db

param(
    [string]$BackupFile = "",
    [string]$DmsRoot    = $PSScriptRoot + "\.."
)

$DmsRoot = Resolve-Path $DmsRoot

if (-not $BackupFile) {
    Write-Host "Usage: .\restore_db.ps1 -BackupFile dms_20251231.db" -ForegroundColor Red
    exit 1
}

$NasUrl  = "https://stroydnepr.synology.me:5001/webapi/entry.cgi"
$NasUser = "Administrator"
$NasPass = "Lytgh8989."
$BackupPath = "/Backup/db/$BackupFile"
$LocalDb    = Join-Path $DmsRoot "dms.db"

Write-Host "=== DMS-NAS DB Restore ===" -ForegroundColor Cyan
Write-Host "Backup: $BackupPath" -ForegroundColor Gray
Write-Host "Target: $LocalDb" -ForegroundColor Gray

# Step 1: Login
Write-Host "`nAuthenticating with NAS..." -ForegroundColor Yellow
$authResp = Invoke-RestMethod -Method GET -Uri $NasUrl `
    -SkipCertificateCheck `
    -Body @{
        api="SYNO.API.Auth"; version=3; method="login"
        account=$NasUser; passwd=$NasPass
        session="FileStation"; format="sid"
    }

if (-not $authResp.success) {
    Write-Host "NAS login failed!" -ForegroundColor Red; exit 1
}
$sid   = $authResp.data.sid
$token = $authResp.data.synotoken
Write-Host "Login OK (sid=...$(($sid)[-6..-1] -join ''))" -ForegroundColor Green

# Step 2: Download backup
Write-Host "Downloading backup..." -ForegroundColor Yellow
$downloadUrl = "$NasUrl`?api=SYNO.FileStation.Download&version=2&method=download&path=$BackupPath&mode=download&_sid=$sid&SynoToken=$token"

$tmpFile = "$LocalDb.restore_tmp"
Invoke-WebRequest -Uri $downloadUrl -OutFile $tmpFile -SkipCertificateCheck

if (-not (Test-Path $tmpFile)) {
    Write-Host "Download failed!" -ForegroundColor Red; exit 1
}

$size = (Get-Item $tmpFile).Length
Write-Host "Downloaded: $size bytes" -ForegroundColor Green

# Step 3: Stop services if running
Write-Host "`nStopping DMS tasks..." -ForegroundColor Yellow
Stop-ScheduledTask -TaskName "DMS-Bot" -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName "DMS-Web" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

# Step 4: Backup current DB
$backupLocal = "$LocalDb.$(Get-Date -Format 'yyyyMMdd_HHmmss').bak"
if (Test-Path $LocalDb) {
    Copy-Item $LocalDb $backupLocal
    Write-Host "Current DB backed up to: $backupLocal" -ForegroundColor Gray
}

# Step 5: Replace
Move-Item -Force $tmpFile $LocalDb
Write-Host "✅ DB restored from $BackupFile" -ForegroundColor Green

# Step 6: Restart
Write-Host "`nRestarting DMS tasks..." -ForegroundColor Yellow
Start-ScheduledTask -TaskName "DMS-Bot" -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName "DMS-Web" -ErrorAction SilentlyContinue

Write-Host "`n=== Restore complete! ===" -ForegroundColor Green
