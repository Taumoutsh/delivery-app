@echo off
rem Lance la checklist de livraison (Windows). Options : --port 8765 --data .\data
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creation de l'environnement Python (.venv)...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist ".venv\.deps-ok" (
  echo Installation des dependances d'export (PDF/Word)...
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt && type nul > ".venv\.deps-ok"
)
".venv\Scripts\python.exe" -m delivery_app --open %*
