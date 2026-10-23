@echo off
REM TV PC 시작 프로그램에 바로가기를 넣어 두면 부팅 시 자동 실행
cd /d %~dp0
start "TV server" /min python server.py
timeout /t 3 /nobreak >nul
start "" msedge --kiosk http://localhost:8080 --edge-kiosk-type=fullscreen --no-first-run
