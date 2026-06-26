@echo off
rem Cogan Lab RP Coding Toolbox - double-click launcher (Windows).
rem Runs the GUI in the 'rpcoding' conda env, console-less and detached.
setlocal
where conda >nul 2>nul
if errorlevel 1 (
  echo conda was not found on PATH.
  echo Open a conda / Anaconda Prompt, run "conda activate rpcoding", then "rpcoding-gui".
  pause
  exit /b 1
)
rem Find the env's pythonw.exe (no console window) and launch the GUI detached.
for /f "usebackq delims=" %%i in (`conda run -n rpcoding python -c "import os,sys;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"`) do set "PYW=%%i"
if not exist "%PYW%" (
  echo Could not locate the 'rpcoding' env. Run scripts\setup_env.ps1 first.
  pause
  exit /b 1
)
start "" "%PYW%" -m rpcoding.gui.app
endlocal
