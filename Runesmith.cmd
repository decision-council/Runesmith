@echo off
setlocal
title Runesmith Studio
rem Double-click to open Runesmith Studio. Drop a folder on this file to work in that folder.
set "HERE=%~dp0"
set "PYTHONPATH=%HERE%;%PYTHONPATH%"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>nul || goto oldpython
echo.
echo   Runesmith Studio is starting. Your browser opens in a moment.
echo   Keep this window open while you work; close it to stop Runesmith.
echo.
if "%~1"=="" (
  %PY% -m runesmith up --last
) else (
  %PY% -m runesmith up "%~1"
)
if errorlevel 1 pause
exit /b

:nopython
echo.
echo   Runesmith needs Python 3.11 or newer, and it is not installed on this computer.
echo   Get it free from https://www.python.org/downloads/
echo   (in the installer, tick "Add python.exe to PATH"), then double-click Runesmith again.
echo.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:oldpython
echo.
echo   Runesmith needs Python 3.11 or newer. Please update Python from https://www.python.org/downloads/
echo.
pause
exit /b 1
