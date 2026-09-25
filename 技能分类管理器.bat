@echo off
cd /d "%~dp0"
for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do taskkill /F /PID %%i >nul 2>nul
timeout /t 1 /nobreak >nul
python server.py
