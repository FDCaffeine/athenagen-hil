@echo off
setlocal
pushd %~dp0

rem 0) Κάνε το project root ορατό στα imports
set "PYTHONPATH=%CD%"

rem 1) Activate venv
call .\.venv\Scripts\activate.bat || (
  echo [ERROR] Cannot activate .venv
  goto :end
)

rem 2) pre-commit hooks σε όλα τα αρχεία
python -m pre_commit run --all-files --verbose
if errorlevel 1 (
  echo [INFO] Pre-commit έτρεξε αλλαγές ή βρήκε θέματα. Ξανατρέχω μια φορά...
  python -m pre_commit run --all-files --verbose
  if errorlevel 1 goto :end
)

rem 3) pytest (μόνο αν υπάρχει φάκελος tests)
if exist tests\ (
  python -m pytest -q
) else (
  echo [INFO] No tests/ directory; skipping pytest.
)

:end
echo.
echo Exit code: %ERRORLEVEL%
popd
pause
exit /b %ERRORLEVEL%