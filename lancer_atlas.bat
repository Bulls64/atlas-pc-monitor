@echo off
cd /d "%~dp0"
py -3 atlas_pc.py
if errorlevel 1 (
  echo Python 3 est requis pour lancer Atlas PC.
  pause
)
