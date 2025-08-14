@echo off
setlocal ENABLEDELAYEDEXPANSION

:: Πάντα τρέξε από τον φάκελο του script (αν έχει κενά στο path)
cd /d "%~dp0"

:: UTF-8 κονσόλα (για ελληνικά logs/μηνύματα)
chcp 65001 >nul

echo.
echo ============================================
echo   AthenaGen HIL Review - Starter (Windows)
echo ============================================
echo.

:: Φάκελοι που χρησιμοποιεί η εφαρμογή
if not exist "outputs" mkdir "outputs"
if not exist "outputs\_backups" mkdir "outputs\_backups"
if not exist "exports" mkdir "exports"

:: Βρες Python launcher (py) ή python
where py >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  where python >nul 2>nul
  if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Δεν βρέθηκε Python. Εγκατέστησέ το απο python.org και ξαναδοκίμασε.
    pause
    exit /b 1
  )
)

:: Δημιούργησε venv αν δεν υπάρχει
set VENV_DIR=.venv
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo Δημιουργία virtual environment...
  :: Προσπάθησε με 3.11, αλλιώς με ό,τι υπάρχει
  py -3.11 -m venv "%VENV_DIR%" 2>nul || py -3 -m venv "%VENV_DIR%" 2>nul || python -m venv "%VENV_DIR%"
  if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Αποτυχία δημιουργίας venv.
    pause
    exit /b 1
  )
)

:: Ενεργοποίηση venv
call "%VENV_DIR%\Scripts\activate.bat"
if %ERRORLEVEL% NEQ 0 (
  echo [ERROR] Αποτυχία ενεργοποίησης venv.
  pause
  exit /b 1
)

:: Αναβάθμιση pip (σωστά, μέσω python -m pip)
echo Αναβάθμιση pip...
python -m pip install --upgrade pip

:: Εγκατάσταση απαιτήσεων (lock αν υπάρχει, αλλιώς requirements.txt)
set REQ=requirements.lock.txt
if not exist "%REQ%" set REQ=requirements.txt

if exist "%REQ%" (
  echo Εγκατάσταση πακέτων από %REQ% ...
  python -m pip install -r "%REQ%"
) else (
  echo [WARN] Δεν βρέθηκαν ούτε requirements.lock.txt ούτε requirements.txt.
)

:: Σιγουρέψου ότι υπάρχει openpyxl για Excel export
python -m pip install --upgrade openpyxl

:: (Προαιρετικό) σταματάμε το telemetry της Streamlit
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

echo.
echo Εκκίνηση εφαρμογής Streamlit...
echo Αν δεν ανοίξει αυτόματα, άνοιξε τον browser στο: http://localhost:8501
echo.

:: Τρέξε το app
python -m streamlit run app.py

echo.
echo ------------------------------------------------
echo Η εφαρμογή σταμάτησε. Πάτα ένα πλήκτρο για έξοδο.
echo ------------------------------------------------
pause >nul

endlocal
