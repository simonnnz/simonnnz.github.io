@echo off
REM Rebuilds every wireframe listed in models.txt.
REM Double-click this, or run it with a filter:  build.bat chess
cd /d "%~dp0"
"C:\Program Files\Python314\python.exe" build.py %*
echo.
pause
