@echo off
rem Lance la checklist de livraison. Seul Python 3.8+ est requis (aucune dependance).
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 launch.py %*) else (python launch.py %*)
