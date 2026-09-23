@echo off
REM 启动 Pixort 后端（同时托管前端界面）
cd /d "%~dp0"
python backend\run.py --open %*
if errorlevel 1 pause
