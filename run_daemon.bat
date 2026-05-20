@echo off
cd /d "%~dp0"
echo Starting Trade Pulse Quants scheduler daemon...
py -3 main.py
pause
