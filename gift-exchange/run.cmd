@echo off
rem Starts Gift Exchange on Windows: double-click this file, or type run in a terminal here.
rem The same as: py run.py
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 run.py %*
) else (
  python run.py %*
)
if errorlevel 1 pause
