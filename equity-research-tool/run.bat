@echo off
cd /d "%~dp0"
set /p CO=Company name or ticker: 
python research.py %CO%
pause
