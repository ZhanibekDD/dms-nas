<#
.SYNOPSIS
    Проверяет свежесть, размер и SHA-256 последнего PG-дампа.

.DESCRIPTION
    Скрипт:
    1. Находит последний .sql.gz в папке BackupDir
    2. Проверяет дату создания (должен быть свежее MaxAgeHours)
    3. Проверяет размер (должен быть больше MinSizeKB)
    4. Вычисляет SHA-256 и выводит для сверки

.PARAMETER BackupDir
    Папка с дампами. По умолчанию: .\backups\pg

.PARAMETER MaxAgeHours
    Допустимый возраст дампа в часах. По умолчанию: 25 (1 сутки + 1 час).

.PARAMETER MinSizeKB
    Минимальный размер дампа в KB. По умолчанию: 10.

.EXAMPLE
    .\tools\backup_verify.ps1
    .\tools\backup_verify.ps1 -BackupDir "D:\backups" -MaxAgeHours 48
#>

param(
    [string]$BackupDir   = ".\backups\pg",
    [int]$MaxAgeHours    = 25,
    [int]$MinSizeKB      = 10
)

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  DMS-NAS  ·  Backup Verify" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan

$exitCode = 0

# ── Найти последний дамп ──────────────────────────────────────────────────────
if (-not (Test-Path $BackupDir)) {
    Write-Host "ERROR: Папка '$BackupDir' не существует." -ForegroundColor Red
    exit 1
}

$latest = Get-ChildItem -Path $BackupDir -Filter "*.sql.gz" |
          Sort-Object LastWriteTime -Descending |
          Select-Object -First 1

if ($null -eq $latest) {
    Write-Host "ERROR: Нет файлов *.sql.gz в $BackupDir" -ForegroundColor Red
    exit 1
}

Write-Host "Файл : $($latest.Name)" -ForegroundColor Yellow
Write-Host "Путь : $($latest.FullName)"

# ── Проверка возраста ─────────────────────────────────────────────────────────
$ageHours = [math]::Round(((Get-Date) - $latest.LastWriteTime).TotalHours, 1)
Write-Host "Возраст : $ageHours ч  (допустимо: ≤ $MaxAgeHours ч)"

if ($ageHours -gt $MaxAgeHours) {
    Write-Host "  [FAIL] Дамп устарел! Последний бэкап был $ageHours часов назад." -ForegroundColor Red
    $exitCode = 1
} else {
    Write-Host "  [OK]  Свежий дамп." -ForegroundColor Green
}

# ── Проверка размера ──────────────────────────────────────────────────────────
$sizeKB = [math]::Round($latest.Length / 1KB, 1)
Write-Host "Размер : $sizeKB KB  (минимум: $MinSizeKB KB)"

if ($sizeKB -lt $MinSizeKB) {
    Write-Host "  [FAIL] Файл слишком мал — возможно, дамп пустой или повреждённый." -ForegroundColor Red
    $exitCode = 1
} else {
    Write-Host "  [OK]  Размер в норме." -ForegroundColor Green
}

# ── SHA-256 ───────────────────────────────────────────────────────────────────
Write-Host "SHA-256 вычисляется ..."
try {
    $hash = (Get-FileHash -Path $latest.FullName -Algorithm SHA256).Hash
    Write-Host "SHA-256 : $hash" -ForegroundColor Cyan
    Write-Host "  (Сохраните этот хэш для ручной сверки при восстановлении)"
} catch {
    Write-Host "  WARN: Не удалось вычислить SHA-256: $_" -ForegroundColor Yellow
}

# ── Проверка читаемости (заголовок gz) ───────────────────────────────────────
Write-Host "Проверка читаемости (первые байты gz) ..."
try {
    $fs   = [System.IO.File]::OpenRead($latest.FullName)
    $gz   = New-Object System.IO.Compression.GZipStream($fs, [System.IO.Compression.CompressionMode]::Decompress)
    $buf  = New-Object byte[] 512
    $read = $gz.Read($buf, 0, 512)
    $gz.Close(); $fs.Close()
    if ($read -gt 0) {
        Write-Host "  [OK]  Файл читается, прочитано $read байт из gz-потока." -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] gz-файл пуст!" -ForegroundColor Red
        $exitCode = 1
    }
} catch {
    Write-Host "  [FAIL] Ошибка чтения gz: $_" -ForegroundColor Red
    $exitCode = 1
}

# ── Итог ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
if ($exitCode -eq 0) {
    Write-Host "  Бэкап в порядке." -ForegroundColor Green
} else {
    Write-Host "  ВНИМАНИЕ: есть проблемы с бэкапом! Проверьте выше." -ForegroundColor Red
}
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan

exit $exitCode
