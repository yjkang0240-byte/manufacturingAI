@echo off
setlocal
cd /d "%~dp0\..\.."
if not exist "ai_server\storage\logs" mkdir "ai_server\storage\logs"
"ai_server\.venv\Scripts\python.exe" -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false >> "ai_server\storage\logs\streamlit.run.log" 2>&1
