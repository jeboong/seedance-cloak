@echo off
chcp 65001 >nul
REM Seedance Cloak → exe 빌드
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 ( set PY=python ) else ( set PY=py )

echo [1/2] 빌드 의존성 확인/설치...
%PY% -m pip install -q -r requirements.txt

echo [2/2] exe 빌드 (FFmpeg 9.0 + 모델 다운로드 포함, 수 분 소요)...
%PY% build\build_exe.py %*

pause
