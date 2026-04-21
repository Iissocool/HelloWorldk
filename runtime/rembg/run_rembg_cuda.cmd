@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "ROOT=%%~fI"
set "PY=%ROOT%\venvs\rembg-nvidia\Scripts\python.exe"
if not exist "%PY%" set "PY=%ROOT%\venvs\rembg-nv\Scripts\python.exe"
"%PY%" "%SCRIPT_DIR%run_rembg_multi.py" --backend cuda %*
