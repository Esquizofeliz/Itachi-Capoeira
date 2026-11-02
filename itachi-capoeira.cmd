@echo off
REM Itachi Capoeira Control (Windows) - atalho para: .venv\Scripts\python.exe -m itachi_capoeira <comando>
set "DIR=%~dp0"
if not exist "%DIR%.venv\Scripts\python.exe" (
  echo Ambiente nao instalado. Rode primeiro: install.bat
  exit /b 1
)
cd /d "%DIR%"
set "PYTHONPATH=%DIR%;%PYTHONPATH%"
set "PYTHONIOENCODING=utf-8"
"%DIR%.venv\Scripts\python.exe" -m itachi_capoeira %*
