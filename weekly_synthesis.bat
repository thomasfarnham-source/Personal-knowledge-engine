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
python -c "import os; k=os.environ.get('ANTHROPIC_API_KEY',''); print(f'Key loaded: {len(k)} chars')" >> "%STATUS%"
echo. >> "%STATUS%"
echo. >> "%STATUS%"
echo ## Weekly Synthesis >> "%STATUS%"
echo. >> "%STATUS%"
echo Phase 1: Selecting strongest items... >> "%STATUS%"
echo Phase 2: Fetching full articles for deep reading... >> "%STATUS%"
echo Phase 3: Generating synthesis... >> "%STATUS%"
echo. >> "%STATUS%"
echo *(this takes 2-4 minutes)* >> "%STATUS%"

python scripts/content_agent/composer.py --weekly --vault-path "%VAULT%"

if errorlevel 1 (
    echo. >> "%STATUS%"
    echo **FAILED** at %time% >> "%STATUS%"
) else (
    echo. >> "%STATUS%"
    echo **Complete** at %time% >> "%STATUS%"
)
