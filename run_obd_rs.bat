@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE="

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PYTHON_EXE=py"
    ) else (
        set "PYTHON_EXE=python"
    )
)

echo Starting obd_rs with %PYTHON_EXE%...
%PYTHON_EXE% main.py

if errorlevel 1 (
    echo.
    echo App exited with an error. Press any key to close.
    pause >nul
)

endlocal
