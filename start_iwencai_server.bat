@echo off
setlocal

title iwencai-py server
cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8765"
set "MIN_QUERY_INTERVAL=5"
set "MAX_QUERY_QUEUE=50"

where python >nul 2>nul
if "%ERRORLEVEL%"=="0" (
    set "PYTHON_CMD=python"
) else (
    where py >nul 2>nul
    if "%ERRORLEVEL%"=="0" (
        set "PYTHON_CMD=py -3"
    ) else (
        echo Python was not found. Please install Python 3.9+ or add it to PATH.
        pause
        exit /b 1
    )
)

echo Starting iwencai-py server...
echo Loading account configuration before starting the API...
echo URL: http://%HOST%:%PORT%
echo Account manager: http://%HOST%:%PORT%/
echo Press Ctrl+C to stop.
echo.

%PYTHON_CMD% -m iwencai_cli.server --host %HOST% --port %PORT% --min-query-interval %MIN_QUERY_INTERVAL% --max-query-queue %MAX_QUERY_QUEUE%

echo.
echo Server stopped.
pause
