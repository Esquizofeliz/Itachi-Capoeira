@echo off
REM Itachi Capoeira - instalador para Windows 10/11
REM Uso: clique duas vezes, ou:  install.bat [--yes] [--tier xl|m|s|cpu] [--autostart] ...
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && (py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PY=py -3")
if not defined PY (
  where python >nul 2>nul && (python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PY=python")
)
if not defined PY (
  echo Python 3.10+ nao encontrado. Tentando instalar o Python 3.12 com winget...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo Instale o Python 3.12 em https://www.python.org/downloads/ ^(marque "Add python.exe to PATH"^) e rode este arquivo de novo.
    pause
    exit /b 1
  )
  winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY="%LocalAppData%\Programs\Python\Python312\python.exe""
)
if not defined PY (
  echo Python instalado. FECHE esta janela, abra uma nova e rode install.bat novamente.
  pause
  exit /b 1
)

%PY% install.py %*
set "RC=%ERRORLEVEL%"
echo.
pause
exit /b %RC%
