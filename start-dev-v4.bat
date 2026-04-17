@echo off
cd /d "%~dp0bathroom-tool"

if not exist ".env" (
    echo .env bestand niet gevonden.
    echo Kopieer .env.example naar .env en vul je keys in.
    echo.
    pause
    exit /b 1
)

if not exist "venv\Scripts\activate.bat" (
    echo Virtuele omgeving aanmaken...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Dependencies installeren...
pip install -r requirements.txt --quiet

echo.
echo ================================
echo  Bathroom Tool draait op:
echo  http://localhost:8000
echo  Leads bekijken:
echo  http://localhost:8000/api/leads
echo ================================
echo.

start "" "http://localhost:8000"
uvicorn main:app --reload --port 8000

pause
