@echo off
cd /d "%~dp0"
echo Starting Trade Pulse Quants dashboard...
py -3 -m streamlit run app.py
pause
