$projectDir = "C:\Programming\HardwareScraper"
$logFile    = "$projectDir\data\notify.log"
$python     = "$projectDir\.venv\Scripts\python.exe"

Set-Location $projectDir

# Rotate log if over 5MB
if ((Test-Path $logFile) -and (Get-Item $logFile).Length -gt 5MB) {
    Move-Item $logFile "$logFile.old" -Force
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content $logFile "[$timestamp] === scan-and-notify started ==="

& $python -m hardware_scraper.cli scan-and-notify 2>&1 |
    ForEach-Object { Add-Content $logFile "[$((Get-Date -Format 'HH:mm:ss'))] $_" }

Add-Content $logFile "[$((Get-Date -Format 'HH:mm:ss'))] === done ==="
