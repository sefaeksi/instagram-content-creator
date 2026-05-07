@echo off
cd /d "%~dp0"
echo Dashboard baslatiliyor...
start http://localhost:5050
python app.py
