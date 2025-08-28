@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ---------------------------------------------
REM AthenaGen HIL Review - Windows runner (fixed)
REM ---------------------------------------------

cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PYTHONPATH=%CD%"

if not exist "outputs"               mkdir "outputs"
if not exist "outputs\_backups"      mkdir "outputs\_backups"
if not exist "exports"               mkdir "exports"

echo.
echo ============================================
echo   AthenaGen HIL Review - Starter (Windows)
echo ============================================
echo.

REM Pick python launcher
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  set "PY=py -3"
) else (
  where python >nul 2>&1 || (
    echo [ERROR] Δεν βρέθηκε Python. Κατέβασε από https://www.python.org/downloads/
    pause
    exit /b 1
  )
  set "PY=python"
)

REM Create venv if missing
set "VENV_DIR=.venv"
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [INFO] Δημιουργία virtual environment...
  %PY% -3.11 -m venv "%VENV_DIR%" 2>nul || %PY% -m venv "%VENV_DIR%"
  if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Αποτυχία δημιουργίας venv.
    pause
    exit /b 1
  )
)

REM Activate venv
call "%VENV_DIR%\Scripts\activate.bat" || (
  echo [ERROR] Αποτυχία ενεργοποίησης venv.
  pause
  exit /b 1
)

echo Αναβάθμιση pip...
python -m pip install --upgrade pip

REM Install deps: try lock first, fallback to requirements.txt
set "USED_LOCK=0"
if exist "requirements.lock.txt" (
  echo Εγκατάσταση πακέτων από requirements.lock.txt ...
  python -m pip install -r "requirements.lock.txt"
  if errorlevel 1 (
    echo [WARN] Αποτυχία από requirements.lock.txt ^(encoding; fallback σε requirements.txt^)...
    if exist "requirements.txt" (
      python -m pip install -r "requirements.txt"
      if errorlevel 1 (
        echo [ERROR] Αποτυχία εγκατάστασης από requirements.txt.
        goto :fail
      )
    ) else (
      echo [ERROR] Δεν βρέθηκε requirements.txt για fallback.
      goto :fail
    )
  ) else (
    set "USED_LOCK=1"
  )
) else (
  if exist "requirements.txt" (
    echo Εγκατάσταση πακέτων από requirements.txt ...
    python -m pip install -r "requirements.txt"
    if errorlevel 1 (
      echo [ERROR] Αποτυχία εγκατάστασης από requirements.txt.
      goto :fail
    )
  ) else (
    echo [WARN] Δεν βρέθηκαν ούτε requirements.lock.txt ούτε requirements.txt.
  )
)

REM Ensure GSheets deps (idempotent)
python -m pip install "cachetools>=5.0.0,<6.0"
python -m pip install gspread==6.1.4 google-auth==2.33.0 gspread-dataframe==3.3.1
python -m pip install --upgrade openpyxl

REM Ensure streamlit exists
python -c "import streamlit" 1>nul 2>nul
if errorlevel 1 (
  echo [INFO] Εγκατάσταση streamlit...
  python -m pip install "streamlit==1.48.0"
  if errorlevel 1 (
    echo [ERROR] Αποτυχία εγκατάστασης streamlit.
    goto :fail
  )
)

REM Optional dependency check
python -m pip check || echo [WARN] Υπάρχουν dependency conflicts. Συνεχίζω...

REM GOOGLE_APPLICATION_CREDENTIALS only if key file present
if exist "%CD%\gcp-sa.json" (
  set "GOOGLE_APPLICATION_CREDENTIALS=%CD%\gcp-sa.json"
) else (
  echo [INFO] Δεν βρέθηκε gcp-sa.json στο project root ^(Sheets export off^).
)

set "GSHEETS_WORKSHEET=Export"
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"

echo.
echo Εκκίνηση εφαρμογής Streamlit...
echo Αν δεν ανοίξει αυτόματα, άνοιξε: http://localhost:8501
echo.

python -m streamlit run app.py
set "EXITCODE=%ERRORLEVEL%"
goto :end

:fail
set "EXITCODE=1"

:end
echo.
echo ------------------------------------------------
echo Η εφαρμογή σταμάτησε. Exit code: %EXITCODE%
echo ------------------------------------------------
pause >nul
endlocal & exit /b %EXITCODE%
