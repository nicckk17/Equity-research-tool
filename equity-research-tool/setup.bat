@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python tests\test_offline.py
pause
