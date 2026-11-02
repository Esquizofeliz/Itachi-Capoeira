@echo off
REM itachi-capoeira-gui (Windows) - abre a interface grafica local do Itachi Capoeira
set "DIR=%~dp0"
if not exist "%DIR%.venv\Scripts\python.exe" (
  echo Ambiente nao instalado. Rode primeiro: install.bat
  exit /b 1
)
cd /d "%DIR%"
set "PYTHONPATH=%DIR%;%PYTHONPATH%"
set "PYTHONIOENCODING=utf-8"
"%DIR%.venv\Scripts\python.exe" -m itachi_capoeira.gui %*
