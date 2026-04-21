@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "ROOT=%%~fI"
set "PY=%ROOT%\venvs\rembg-dml\Scripts\python.exe"
"%PY%" "%SCRIPT_DIR%run_rembg_dml.py" %*
