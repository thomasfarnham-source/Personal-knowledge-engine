@echo off
cd /d C:\Users\thoma\Documents\dev\Personal-knowledge-engine
call venv\Scripts\activate.bat
echo PKE Retrieval API starting on http://localhost:8000
echo Close this window to stop the API
echo.
python -m uvicorn pke.api.main:app --host 127.0.0.1 --port 8000