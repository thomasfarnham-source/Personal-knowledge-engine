@echo off
set "PROJDIR=C:\Users\thoma\Documents\dev\Personal-knowledge-engine"
set "VAULT=C:\Users\thoma\OneDrive\Apps\New folder\Journal"
set "STATUS=%VAULT%\Pipeline Status.md"

cd /d "%PROJDIR%"
call venv\Scripts\activate.bat
git fetch origin main
git checkout origin/main -- scripts/content_agent/output/filtered/ scripts/content_agent/output/briefs/ scripts/content_agent/output/raw/
if errorlevel 1 echo **WARNING: Failed to fetch latest content from main** >> "%STATUS%"

REM Load environment variables from .env
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%PROJDIR%\.env") do (
    if not "%%a"=="" if not "%%b"=="" set "%%a=%%b"
)

REM Today's date in YYYY-MM-DD format for filename checks.
REM Uses Python because Windows date formatting is locale-dependent and
REM unreliable across machines; Python gives a consistent ISO format.
for /f "delims=" %%d in ('python -c "from datetime import datetime; print(datetime.now().strftime('%%Y-%%m-%%d'))"') do set "TODAY=%%d"

REM Paths to today's expected output files. If these exist, GitHub Actions
REM already ran the upstream agents and we can skip them.
set "SCOUT_FILE=%PROJDIR%\scripts\content_agent\output\raw\scout_raw_%TODAY%.json"
set "EDITOR_FILE=%PROJDIR%\scripts\content_agent\output\filtered\editor_filtered_%TODAY%.json"

REM Initialize the Pipeline Status file
echo # Pipeline Status > "%STATUS%"
echo *Started: %date% %time%* >> "%STATUS%"
echo. >> "%STATUS%"
echo --- >> "%STATUS%"
echo. >> "%STATUS%"
echo ## Daily Enrichment >> "%STATUS%"
echo. >> "%STATUS%"

REM ---------------------------------------------------------------------------
REM Scout — scan RSS feeds and NewsAPI
REM Skip if today's output already exists (typically from GitHub Actions).
REM ---------------------------------------------------------------------------
if exist "%SCOUT_FILE%" (
    echo Scout skipped — today's output already exists >> "%STATUS%"
) else (
    echo Running Scout... >> "%STATUS%"
    python scripts/content_agent/scout.py
    if errorlevel 1 (
        echo **Scout FAILED** at %time% >> "%STATUS%"
    ) else (
        echo Scout complete >> "%STATUS%"
    )
)
echo. >> "%STATUS%"

REM Surface Scout feed errors into the Status file so they're visible in Obsidian.
echo ### Scout Feed Errors >> "%STATUS%"
python -c "import json, glob, os; files = sorted(glob.glob(os.path.join(r'%PROJDIR%', 'scripts', 'content_agent', 'output', 'raw', 'scout_raw_*.json'))); data = json.load(open(files[-1], encoding='utf-8')) if files else {}; errors = data.get('feed_errors', []); print('\n'.join(f'- **{e[\"name\"]}** ({e[\"pillar\"]}, {e[\"origin\"]}): {e[\"error\"]}' for e in errors) if errors else 'No feed errors')" >> "%STATUS%"
echo. >> "%STATUS%"

REM ---------------------------------------------------------------------------
REM Editor — apply editorial mandate to Scout output
REM Skip if today's filtered output already exists.
REM ---------------------------------------------------------------------------
if exist "%EDITOR_FILE%" (
    echo Editor skipped — today's output already exists >> "%STATUS%"
) else (
    echo Running Editor... >> "%STATUS%"
    python scripts/content_agent/editor.py
    if errorlevel 1 (
        echo **Editor FAILED** at %time% >> "%STATUS%"
    ) else (
        echo Editor complete >> "%STATUS%"
    )
)
echo. >> "%STATUS%"

REM Surface Editor chunk failures into the Status file.
echo ### Editor Chunk Failures >> "%STATUS%"
python -c "import json, glob, os; files = sorted(glob.glob(os.path.join(r'%PROJDIR%', 'scripts', 'content_agent', 'output', 'filtered', 'editor_filtered_*.json'))); data = json.load(open(files[-1], encoding='utf-8')) if files else {}; errors = data.get('report', {}).get('chunk_errors', []); print('\n'.join(f'- Chunk {e[\"chunk_index\"] + 1}: {e[\"item_count\"]} items lost — {e[\"error\"]}' for e in errors) if errors else 'No chunk failures')" >> "%STATUS%"
echo. >> "%STATUS%"

REM ---------------------------------------------------------------------------
REM PKE API — needed by the Connector to query personal corpus
REM ---------------------------------------------------------------------------
echo Starting PKE API... >> "%STATUS%"
start /B python -m uvicorn pke.api.main:app --host 127.0.0.1 --port 8000 > nul 2>&1
timeout /t 5 /nobreak > nul
echo PKE API running >> "%STATUS%"
echo. >> "%STATUS%"

REM ---------------------------------------------------------------------------
REM Connector — find personal corpus and book connections
REM Always runs — needs the local PKE API which only runs on this machine.
REM ---------------------------------------------------------------------------
echo Fetching articles and finding connections... >> "%STATUS%"
python scripts/content_agent/connector.py
if errorlevel 1 (
    echo **Connector FAILED** at %time% >> "%STATUS%"
) else (
    echo Connector complete >> "%STATUS%"
)
echo. >> "%STATUS%"

REM Surface Connector errors into the Status file.
echo ### Connector Errors >> "%STATUS%"
python -c "import json, glob, os; files = sorted(glob.glob(os.path.join(r'%PROJDIR%', 'scripts', 'content_agent', 'output', 'connected', 'connected_*.json'))); data = json.load(open(files[-1], encoding='utf-8')) if files else {}; errs = data.get('connector_errors', {}); lines = []; lines.append(f'- PKE queries failed for {errs[\"pke_items_failed\"]}/{errs[\"pke_total_items\"]} items — {errs[\"pke_sample_error\"]}') if errs.get('pke_items_failed') else None; lines.append(f'- Book matching API failed: {errs[\"book_matching_error\"]}') if errs.get('book_matching_error') else None; lines.append(f'- PKE synthesis API failed: {errs[\"synthesis_error\"]}') if errs.get('synthesis_error') else None; print('\n'.join(lines) if lines else 'No connector errors')" >> "%STATUS%"
echo. >> "%STATUS%"

REM ---------------------------------------------------------------------------
REM Composer — write the daily drop to the Obsidian vault
REM Always runs — needs to write to the local vault.
REM Now exits non-zero on fatal errors (empty input, write failures), so the
REM `if errorlevel 1` check below actually fires when something material breaks.
REM ---------------------------------------------------------------------------
echo Composing daily drop... >> "%STATUS%"
python scripts/content_agent/composer.py --daily --vault-path "%VAULT%"
if errorlevel 1 (
    echo **Composer FAILED** at %time% >> "%STATUS%"
) else (
    echo Composer complete >> "%STATUS%"
)
echo. >> "%STATUS%"

REM Surface Composer errors into the Status file. Composer writes a
REM composer_errors_*.json file alongside the briefs that lists all
REM failure modes encountered during the run.
echo ### Composer Errors >> "%STATUS%"
python -c "import json, glob, os; files = sorted(glob.glob(os.path.join(r'%PROJDIR%', 'scripts', 'content_agent', 'output', 'briefs', 'composer_errors_*.json'))); errs = json.load(open(files[-1], encoding='utf-8')) if files else {}; lines = []; lines.append('- No Connector output found') if errs.get('no_connector_output') else None; lines.append('- Connector output had 0 valid items — upstream pipeline failed') if errs.get('empty_connector_input') else None; lines.append(f'- Skipped {errs[\"malformed_items_skipped\"]} malformed items') if errs.get('malformed_items_skipped') else None; lines.append(f'- Daily vault write failed: {errs[\"daily_vault_write_error\"]}') if errs.get('daily_vault_write_error') else None; lines.append(f'- Daily output write failed: {errs[\"daily_output_write_error\"]}') if errs.get('daily_output_write_error') else None; lines.append('- Weekly synthesis found no items in past 7 days') if errs.get('no_weekly_items') else None; lines.append(f'- Weekly synthesis API failed: {errs[\"weekly_api_error\"]}') if errs.get('weekly_api_error') else None; lines.append('- Weekly synthesis API returned empty text') if errs.get('weekly_empty_response') else None; lines.append(f'- Weekly vault write failed: {errs[\"weekly_vault_write_error\"]}') if errs.get('weekly_vault_write_error') else None; lines.append(f'- Weekly output write failed: {errs[\"weekly_output_write_error\"]}') if errs.get('weekly_output_write_error') else None; print('\n'.join(lines) if lines else 'No composer errors')" >> "%STATUS%"
echo. >> "%STATUS%"

REM ---------------------------------------------------------------------------
REM Cleanup — stop the PKE API
REM ---------------------------------------------------------------------------
echo Stopping PKE API... >> "%STATUS%"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /PID %%a /F > nul 2>&1

echo. >> "%STATUS%"
echo **Complete** — enrichment finished at %time% >> "%STATUS%"