@echo off
rem Starts Gift Exchange on Windows. Double-click this file.
rem Nothing needs to be installed first: if Python isn't found, this installs uv (a small tool
rem that downloads Python 3.12 just for this app) and uses that.
setlocal
cd /d "%~dp0"
set "UV_VERSION=0.13.8"

rem 1. An installed Python 3.8 or newer runs the launcher directly.
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul
if errorlevel 1 goto try_python
py -3 run.py %*
goto done

:try_python
rem (the Microsoft Store "python" placeholder fails this check and is skipped)
where python >nul 2>nul
if errorlevel 1 goto use_uv
python -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul
if errorlevel 1 goto use_uv
python run.py %*
goto done

:use_uv
rem 2. No Python: use uv, installing it once if needed (into your user folder, no admin rights).
set "UV=%USERPROFILE%\.local\bin\uv.exe"
where uv >nul 2>nul
if not errorlevel 1 set "UV=uv"
if "%UV%"=="uv" goto run_with_uv
if exist "%UV%" goto run_with_uv
echo Installing uv, one time only. This needs an internet connection...
powershell -NoProfile -ExecutionPolicy ByPass -Command "$env:UV_NO_MODIFY_PATH='1'; irm https://astral.sh/uv/%UV_VERSION%/install.ps1 | iex"
if exist "%UV%" goto run_with_uv
echo.
echo Could not install uv. Check your internet connection and try again.
goto done

:run_with_uv
"%UV%" run --no-project --python 3.12 run.py %*

:done
rem keep the window open if something went wrong, so the message can be read
if errorlevel 1 pause
