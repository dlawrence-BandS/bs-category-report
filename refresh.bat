@echo off
cd /d "%~dp0"
echo Refreshing B^&S Item Category Report data...
py refresh_data.py
if errorlevel 1 (
  echo REFRESH FAILED
  pause
  exit /b 1
)
echo Done. Commit and push the data folder via GitHub Desktop to publish.
pause
