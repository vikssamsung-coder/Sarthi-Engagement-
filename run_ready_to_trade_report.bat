@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo Bigul Sarthi Engagement - Ready To Trade Last Trade Report
echo ============================================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set PY_CMD=py -3
) else (
    set PY_CMD=python
)

echo Python command: %PY_CMD%
%PY_CMD% --version
if errorlevel 1 (
    echo ERROR: Python is not available.
    pause
    exit /b 1
)

echo.
echo Checking dependencies...
%PY_CMD% -c "import pandas, openpyxl, sqlalchemy, pymysql, dotenv" >nul 2>nul
if errorlevel 1 (
    echo Installing dependencies from requirements.txt...
    %PY_CMD% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Dependency installation failed.
        pause
        exit /b 1
    )
)

echo.
echo Starting report...
%PY_CMD% src\ready_to_trade_last_trade_report.py %*
set EXIT_CODE=%errorlevel%

echo.
if not "%EXIT_CODE%"=="0" (
    echo Report failed with exit code %EXIT_CODE%.
) else (
    echo Report completed successfully.
)
pause
exit /b %EXIT_CODE%
