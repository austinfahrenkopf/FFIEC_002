@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "serve.ps1" -Port 8002
