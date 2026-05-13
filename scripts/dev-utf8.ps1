$ErrorActionPreference = "Stop"

chcp 65001 > $null

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:NODE_OPTIONS = "--enable-source-maps"

Write-Host "UTF-8 developer shell is ready." -ForegroundColor Green
Write-Host "Current code page: $(chcp | Out-String | ForEach-Object { $_.Trim() })"
Write-Host "PYTHONUTF8=$env:PYTHONUTF8"
Write-Host "PYTHONIOENCODING=$env:PYTHONIOENCODING"
