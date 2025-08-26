@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ---------------------------------------------
REM AthenaGen HIL Review - Windows runner
REM ---------------------------------------------

REM Πάντα τρέξε από τον φάκελο του script (αν έχει κενά στο path)
cd /d "%~dp0"

REM UTF-8 κονσόλα (για ελληνικά logs/μηνύματα)
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM === Σιγουρέψου ότι το project root είναι στο PYTHONPATH (για data_parser package) ===
set "PYTHONPATH=%CD%"

echo.
echo ============================================
echo   AthenaGen HIL Review - Starter (Windows)
echo ============================================
echo.

REM Φάκελοι που χρησιμοποιεί η εφαρμογή
if not exist "outputs" mkdir "outputs"
if not exist "outputs\_backups" mkdir "outputs\_backups"
if not exist "exports" mkdir "exports"

REM Βρες Python launcher (py) ή python
where py >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  where python >nul 2>nul
  if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Δεν βρέθηκε Python. Εγκατέστησέ το από https://www.python.org/downloads/ και ξαναδοκίμασε.
    pause
    exit /b 1
  )
)

REM Δημιούργησε venv αν δεν υπάρχει
set "VENV_DIR=.venv"
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo Δημιουργία virtual environment...
  py -3.11 -m venv "%VENV_DIR%" 2>nul || py -3 -m venv "%VENV_DIR%" 2>nul || python -m venv "%VENV_DIR%"
  if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Αποτυχία δημιουργίας venv.
    pause
    exit /b 1
  )
)

REM Ενεργοποίηση venv
call "%VENV_DIR%\Scripts\activate.bat"
if %ERRORLEVEL% NEQ 0 (
  echo [ERROR] Αποτυχία ενεργοποίησης venv.
  pause
  exit /b 1
)

REM Αναβάθμιση pip (σωστά, μέσω python -m pip)
echo Αναβάθμιση pip...
python -m pip install --upgrade pip

REM Εγκατάσταση απαιτήσεων (lock αν υπάρχει, αλλιώς requirements.txt)
set "REQ=requirements.lock.txt"
if not exist "%REQ%" set "REQ=requirements.txt"

if exist "%REQ%" (
  echo Εγκατάσταση πακέτων από %REQ% ...
  python -m pip install -r "%REQ%"
) else (
  echo [WARN] Δεν βρέθηκαν ούτε requirements.lock.txt ούτε requirements.txt.
)

REM Pin για google-auth/cachetools (αν δεν είναι ήδη στο requirements)
python -m pip install "cachetools>=5.0.0,<6.0"
python -m pip install gspread==6.1.4 google-auth==2.33.0 gspread-dataframe==3.3.1
python -m pip install --upgrade openpyxl

REM (Προαιρετικό) Έλεγχος conflicts
python -m pip check || echo [WARN] Υπάρχουν dependency conflicts. Συνεχίζω...

REM -------- Google Sheets ρυθμίσεις --------
REM Βάλε το JSON του service account σε αρχείο gcp-sa.json (δίπλα στο app.py)
set "GOOGLE_APPLICATION_CREDENTIALS=%CD%\gcp-sa.json"

REM Αυτό το env το διαβάζει το app για το worksheet:
set "GSHEETS_WORKSHEET=Export"

REM ΣΗΜΕΙΩΣΗ: Το app διαβάζει ΣΗΜΕΡΑ hardcoded Sheet ID.
REM Προτείνω στο app.py: GSHEET_ID_DEFAULT = os.getenv("GSHEETS_SPREADSHEET_ID", "<hardcoded>")
REM Κι έπειτα μπορείς να ξεκλειδώσεις αυτή τη γραμμή:
REM set "GSHEETS_SPREADSHEET_ID=1B649fKVMBW_LP6C9Up46JFBnGH8Sex8NhXJ6rsMQMLI"

REM (Προαιρετικό) σταματάμε το telemetry της Streamlit
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"

echo.
echo Εκκίνηση εφαρμογής Streamlit...
echo Αν δεν ανοίξει αυτόματα, άνοιξε τον browser στο: http://localhost:8501
echo.

REM Τρέξε το app (προαιρετικά πρόσθεσε --server.runOnSave=true ή --server.port=8501)
python -m streamlit run app.py

echo.
echo ------------------------------------------------
echo Η εφαρμογή σταμάτησε. Πάτα ένα πλήκτρο για έξοδο.
echo ------------------------------------------------
pause >nul

endlocal
