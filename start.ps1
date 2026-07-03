# DocuTrust Startup Script (Windows PowerShell)
# Run this from the "EduExpose prj" directory

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ████████████████████████████████████████" -ForegroundColor DarkBlue
Write-Host "  ██                                    ██" -ForegroundColor DarkBlue
Write-Host "  ██   DocuTrust — Enterprise RAG       ██" -ForegroundColor Cyan
Write-Host "  ██   Advanced CRAG Platform v1.0      ██" -ForegroundColor Cyan
Write-Host "  ██                                    ██" -ForegroundColor DarkBlue
Write-Host "  ████████████████████████████████████████" -ForegroundColor DarkBlue
Write-Host ""

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $Root ".venv"
$BackendPath = Join-Path $Root "docutrust\backend"
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"

# ─── Check virtual environment ───
if (-not (Test-Path $PythonExe)) {
    Write-Host "  [!] Virtual environment not found. Creating it now..." -ForegroundColor Yellow
    python -m venv "$VenvPath"
    Write-Host "  [+] Virtual environment created." -ForegroundColor Green
    
    Write-Host "  [>] Installing dependencies (this may take a few minutes)..." -ForegroundColor Cyan
    & "$PythonExe" -m pip install --quiet --upgrade pip
    & "$PythonExe" -m pip install --quiet -r "$BackendPath\requirements.txt"
    Write-Host "  [+] Dependencies installed." -ForegroundColor Green
} else {
    Write-Host "  [+] Virtual environment found." -ForegroundColor Green
}

# ─── Check MongoDB ───
Write-Host "  [>] Checking MongoDB connection..." -ForegroundColor Cyan
try {
    $mongoTest = & "$PythonExe" -c "
import asyncio, motor.motor_asyncio
async def check():
    c = motor.motor_asyncio.AsyncIOMotorClient('mongodb://localhost:27017', serverSelectionTimeoutMS=2000)
    await c.admin.command('ping')
    print('OK')
asyncio.run(check())
" 2>&1
    if ($mongoTest -match "OK") {
        Write-Host "  [+] MongoDB is running." -ForegroundColor Green
    } else {
        Write-Host "  [!] MongoDB is not running. Start MongoDB first!" -ForegroundColor Red
        Write-Host "      Run: mongod --dbpath C:\data\db" -ForegroundColor DarkYellow
        Write-Host "      Or install from: https://www.mongodb.com/try/download/community" -ForegroundColor DarkYellow
        Write-Host ""
        Write-Host "  Press any key to continue anyway (uploads will fail)..." -ForegroundColor DarkGray
        $null = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    }
} catch {
    Write-Host "  [!] Could not check MongoDB: $_" -ForegroundColor Yellow
}

# ─── Check .env ───
$EnvFile = Join-Path $BackendPath ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "  [!] .env file not found. Copying from .env.example..." -ForegroundColor Yellow
    Copy-Item (Join-Path $BackendPath ".env.example") $EnvFile
    Write-Host "  [+] Created .env — edit it to add your API keys." -ForegroundColor Green
}

# ─── Check API key ───
$envContent = Get-Content $EnvFile -Raw
if ($envContent -match "your-google-api-key-here" -or $envContent -match "your-openai") {
    Write-Host ""
    Write-Host "  [i] No API key configured. Running in Local Extractive Mode." -ForegroundColor Yellow
    Write-Host "      To enable AI generation, edit: docutrust\backend\.env" -ForegroundColor DarkYellow
    Write-Host "      and add your Google API key from: https://aistudio.google.com/apikey" -ForegroundColor DarkYellow
}

# ─── Start server ───
Write-Host ""
Write-Host "  [>] Starting DocuTrust server..." -ForegroundColor Cyan
Write-Host "  [>] Open browser at: http://localhost:8000" -ForegroundColor White
Write-Host "  [>] API docs at:     http://localhost:8000/docs" -ForegroundColor White
Write-Host "  [>] Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

Set-Location $BackendPath
& "$PythonExe" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
