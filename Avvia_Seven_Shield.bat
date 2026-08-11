@echo off
setlocal EnableExtensions
pushd "%~dp0"

set "VENV_PYTHON=.venv\Scripts\python.exe"
set "VENV_PYTHONW=.venv\Scripts\pythonw.exe"

if exist "%VENV_PYTHON%" goto check_install

echo [Seven Shield] Prima configurazione: creazione ambiente Python...
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
    goto venv_created
)

where python3 >nul 2>nul
if not errorlevel 1 (
    python3 -m venv .venv
    goto venv_created
)

where python >nul 2>nul
if not errorlevel 1 (
    python -m venv .venv
    goto venv_created
)

echo [ERRORE] Python 3 non trovato. Installare Python 3.11 o successivo.
goto failed

:venv_created
if errorlevel 1 (
    echo [ERRORE] Impossibile creare l'ambiente virtuale.
    goto failed
)

:check_install
"%VENV_PYTHON%" -c "import seven_shield" >nul 2>nul
if not errorlevel 1 goto launch

echo [Seven Shield] Installazione dell'applicazione...
"%VENV_PYTHON%" -m pip install --disable-pip-version-check -e .
if errorlevel 1 (
    echo [ERRORE] Installazione non riuscita.
    goto failed
)

:launch
if not exist "%VENV_PYTHONW%" (
    echo [ERRORE] Interprete grafico Python non trovato nell'ambiente virtuale.
    goto failed
)

start "Seven Shield" /D "%~dp0" "%VENV_PYTHONW%" -m seven_shield.gui
popd
exit /b 0

:failed
echo.
pause
popd
exit /b 1
