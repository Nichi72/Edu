@echo off
chcp 65001 > nul
cd /d "%~dp0"

if not exist ".env" (
  echo .env 가 없다. .env.example 을 복사해 .env 로 만들고 채운다.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo 처음 실행 - 파이썬 가상환경을 만든다...
  python -m venv .venv || goto FAIL
  .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt || goto FAIL
)

echo 채점 봇 시작. 끄려면 이 창을 닫거나 Ctrl+C.
.venv\Scripts\python.exe main.py
echo.
echo 봇이 끝났다.
pause
exit /b 0

:FAIL
echo 파이썬 설치가 안 됐거나 pip 이 실패했다. python.org 에서 3.11 이상을 설치하고 "Add to PATH" 를 켠다.
pause
exit /b 1
