@echo off
cd /d "%~dp0"
echo Installing upgrade packages...
pip install financedatabase openbb-core openbb-tmx
echo.
echo Running RY with the TMX cross-check...
python research.py RY --crosscheck
echo.
pause
