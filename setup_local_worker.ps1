$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path '.venv-ml')) {
    py -m venv .venv-ml
}

& .\.venv-ml\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-ml\Scripts\python.exe -m pip install -r requirements-local.txt

if (-not $env:DATABASE_URL) {
    Write-Host ''
    Write-Host 'DATABASE_URL saknas. Koppla först den permanenta Postgres/Supabase-databasen.' -ForegroundColor Yellow
    Write-Host 'När DATABASE_URL finns kan samma script starta V5 local intelligence automatiskt.' -ForegroundColor Yellow
    exit 1
}

Write-Host ''
Write-Host 'PRODUCT HUNTER V5 Local Intelligence startar...' -ForegroundColor Green
& .\.venv-ml\Scripts\python.exe local_worker.py --watch --interval 20
