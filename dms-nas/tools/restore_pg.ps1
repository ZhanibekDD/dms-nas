<#
.SYNOPSIS
    Восстановление PostgreSQL из дампа (pg_dump .sql.gz).

.DESCRIPTION
    Скрипт:
    1. Находит последний дамп в указанной папке (или принимает путь явно)
    2. Распаковывает .gz → временный .sql
    3. Пересоздаёт базу dms (DROP + CREATE DATABASE + psql -f dump.sql)
    4. Проверяет количество таблиц после восстановления

.PARAMETER DumpPath
    Путь к .sql.gz файлу. Если не указан — ищет последний в $BackupDir.

.PARAMETER BackupDir
    Папка с дампами. По умолчанию: .\backups\pg

.EXAMPLE
    .\tools\restore_pg.ps1
    .\tools\restore_pg.ps1 -DumpPath "C:\backups\dms_20250310.sql.gz"
#>

param(
    [string]$DumpPath    = "",
    [string]$BackupDir   = ".\backups\pg"
)

# ── Конфигурация (должна совпадать с core/config.py) ─────────────────────────
$PG_HOST = "localhost"
$PG_PORT = "5432"
$PG_DB   = "dms"
$PG_USER = "dms_user"
$PG_PASS = "dms_pass_2025"

$env:PGPASSWORD = $PG_PASS

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  DMS-NAS  ·  PostgreSQL Restore" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan

# ── Найти дамп ───────────────────────────────────────────────────────────────
if ($DumpPath -eq "") {
    if (-not (Test-Path $BackupDir)) {
        Write-Host "ERROR: Папка $BackupDir не найдена." -ForegroundColor Red
        exit 1
    }
    $latest = Get-ChildItem -Path $BackupDir -Filter "*.sql.gz" |
              Sort-Object LastWriteTime -Descending |
              Select-Object -First 1
    if ($null -eq $latest) {
        Write-Host "ERROR: Файлы *.sql.gz не найдены в $BackupDir" -ForegroundColor Red
        exit 1
    }
    $DumpPath = $latest.FullName
}

if (-not (Test-Path $DumpPath)) {
    Write-Host "ERROR: Файл не найден: $DumpPath" -ForegroundColor Red
    exit 1
}

Write-Host "Дамп: $DumpPath" -ForegroundColor Yellow
$fileSize = (Get-Item $DumpPath).Length
Write-Host "Размер: $([math]::Round($fileSize/1KB, 1)) KB"

# ── Распаковать .gz → временный .sql ─────────────────────────────────────────
$TmpSql = [System.IO.Path]::GetTempFileName() + ".sql"
Write-Host "Распаковка в $TmpSql ..."

try {
    $inStream  = [System.IO.File]::OpenRead($DumpPath)
    $gzStream  = New-Object System.IO.Compression.GZipStream($inStream, [System.IO.Compression.CompressionMode]::Decompress)
    $outStream = [System.IO.File]::Create($TmpSql)
    $gzStream.CopyTo($outStream)
    $outStream.Close()
    $gzStream.Close()
    $inStream.Close()
    Write-Host "OK — $(([math]::Round((Get-Item $TmpSql).Length/1MB, 2))) MB SQL" -ForegroundColor Green
} catch {
    Write-Host "ERROR при распаковке: $_" -ForegroundColor Red
    exit 1
}

# ── Пересоздать базу ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "ВНИМАНИЕ: База '$PG_DB' будет удалена и пересоздана!" -ForegroundColor Red
$confirm = Read-Host "Введите YES для продолжения"
if ($confirm -ne "YES") {
    Write-Host "Отменено." -ForegroundColor Yellow
    Remove-Item $TmpSql -ErrorAction SilentlyContinue
    exit 0
}

Write-Host "Пересоздаю базу $PG_DB ..."

# Завершить все соединения
& psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d postgres -c `
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$PG_DB' AND pid <> pg_backend_pid();" `
    | Out-Null

& psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d postgres -c "DROP DATABASE IF EXISTS $PG_DB;" 2>&1
& psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d postgres -c "CREATE DATABASE $PG_DB OWNER $PG_USER ENCODING 'UTF8';" 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: не удалось создать базу." -ForegroundColor Red
    Remove-Item $TmpSql -ErrorAction SilentlyContinue
    exit 1
}

# ── Восстановить данные ───────────────────────────────────────────────────────
Write-Host "Восстановление из дампа ..."
& psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d $PG_DB -f $TmpSql 2>&1
$restoreCode = $LASTEXITCODE

Remove-Item $TmpSql -ErrorAction SilentlyContinue

if ($restoreCode -ne 0) {
    Write-Host "ОШИБКА psql (код $restoreCode). Проверьте вывод выше." -ForegroundColor Red
    exit 1
}

# ── Проверка ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Проверка таблиц ..." -ForegroundColor Cyan
$tables = & psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d $PG_DB -t -c `
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';"
$tables = $tables.Trim()

Write-Host "Таблиц в базе: $tables"

if ([int]$tables -lt 5) {
    Write-Host "ПРЕДУПРЕЖДЕНИЕ: мало таблиц ($tables) — возможно схема не восстановлена." -ForegroundColor Yellow
} else {
    Write-Host "Восстановление завершено успешно!" -ForegroundColor Green
}

Write-Host ""
Write-Host "Следующий шаг — запустить verify:" -ForegroundColor Cyan
Write-Host "  python tools/verify_pg.py"

$env:PGPASSWORD = ""
