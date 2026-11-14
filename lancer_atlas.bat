@echo off
rem Lance Atlas PC Monitor avec le Python disponible sur ce poste.
rem Au premier lancement, installe PySide6 (interface graphique) pour l'utilisateur courant.
rem Les arguments sont transmis : lancer_atlas.bat --json, lancer_atlas.bat --help...
rem Starts Atlas PC Monitor with the Python available on this computer.
rem On the first launch, installs PySide6 (graphical interface) for the current user.
rem Arguments are passed on: lancer_atlas.bat --json, lancer_atlas.bat --help...
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython
%PY% -c "import PySide6" >nul 2>nul
if not errorlevel 1 goto run
echo Premier lancement : installation de PySide6, l'interface graphique d'Atlas PC Monitor...
%PY% -m pip install --user -r requirements.txt
if errorlevel 1 goto pipfail
:run
%PY% atlas_pc.py %*
if errorlevel 1 pause
exit /b
:nopython
echo Python 3 est introuvable sur ce poste.
echo Installez-le depuis https://www.python.org/downloads/ puis relancez ce fichier.
pause
exit /b 1
:pipfail
echo L'installation de PySide6 a echoue. Verifiez la connexion, puis lancez :
echo     %PY% -m pip install --user -r requirements.txt
pause
exit /b 1
