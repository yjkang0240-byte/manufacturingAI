@echo off
setlocal
cd /d "%~dp0\.."
if not exist "storage\logs" mkdir "storage\logs"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> "storage\logs\uvicorn.run.log" 2>&1
