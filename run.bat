@echo off
chcp 65001 >nul
REM Seedance Cloak 실행 (소스)
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 ( set PY=python ) else ( set PY=py )

echo [1/2] 의존성 확인/설치...
%PY% -m pip install -q -r requirements.txt

echo [2/2] 실행...
%PY% run.py

if %errorlevel% neq 0 pause
