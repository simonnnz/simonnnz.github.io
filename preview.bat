@echo off
REM Starts a local web server and opens the site.
REM Leave this window open while you work. Close it to stop the server.
cd /d "%~dp0"
start "" http://localhost:8742/
echo Serving at http://localhost:8742/  --  close this window to stop.
echo.
"C:\Program Files\Python314\python.exe" -m http.server 8742
