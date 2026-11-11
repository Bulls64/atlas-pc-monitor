@echo off
rem Lance Atlas PC avec le Python disponible sur ce poste.
rem Les arguments sont transmis : lancer_atlas.bat --json, lancer_atlas.bat --help...
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 atlas_pc.py %*
  goto fin
)
where python >nul 2>nul
if not errorlevel 1 (
  python atlas_pc.py %*
  goto fin
)
echo Python 3 est introuvable sur ce poste.
echo Installez-le depuis https://www.python.org/downloads/ puis relancez ce fichier.
pause
exit /b 1
:fin
if errorlevel 1 pause
