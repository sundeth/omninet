@echo off
REM Omninet Development Launcher for Windows

echo Starting Omninet Development Server...
echo.

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Set environment to dev
set ENVIRONMENT=dev

REM Run the server
python -m omninet.main

pause
