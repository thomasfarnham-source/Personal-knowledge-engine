@echo off
set "PROJDIR=C:\Users\thoma\Documents\dev\Personal-knowledge-engine"
set "VAULT=C:\Users\thoma\OneDrive\Apps\New folder\Journal"
set "STATUS=%VAULT%\Pipeline Status.md"

cd /d "%PROJDIR%"
call venv\Scripts\activate.bat
git pull

REM Load environment variables from .env
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%PROJDIR%\.env") do (
    if not "%%a"=="" if not "%%b"=="" set "%%a=%%b"
)

echo # Pipeline Status > "%STATUS%"
echo *Started: %date% %time%* >> "%STATUS%"
echo. >> "%STATUS%"
echo --- >> "%STATUS%"
echo. >> "%STATUS%"
echo ## Daily Enrichment >> "%STATUS%"
echo. >> "%STATUS%"

echo Starting PKE API... >> "%STATUS%"
start /B python -m uvicorn pke.api.main:app --host 127.0.0.1 --port 8000 > nul 2>&1
timeout /t 5 /nobreak > nul
echo PKE API running >> "%STATUS%"
echo. >> "%STATUS%"

echo Fetching articles and finding connections... >> "%STATUS%"
python scripts/content_agent/connector.py
if errorlevel 1 (
    echo **Connector FAILED** at %time% >> "%STATUS%"
) else (
    echo Connector complete >> "%STATUS%"
)
echo. >> "%STATUS%"

echo Composing daily drop... >> "%STATUS%"
python scripts/content_agent/composer.py --daily --vault-path "%VAULT%"
if errorlevel 1 (
    echo **Composer FAILED** at %time% >> "%STATUS%"
) else (
    echo Composer complete >> "%STATUS%"
)
echo. >> "%STATUS%"

echo Stopping PKE API... >> "%STATUS%"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /PID %%a /F > nul 2>&1

echo. >> "%STATUS%"
echo **Complete** — enrichment finished at %time% >> "%STATUS%"