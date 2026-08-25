@echo off
chcp 65001 >nul
title 爱优护全自动视频生成工厂
cd /d "%~dp0"

echo ================================================
echo   爱优护全自动视频生成工厂  启动中...
echo ================================================

REM 创建虚拟环境（首次）
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 首次运行，创建 Python 虚拟环境...
    python -m venv .venv
)

echo [2/3] 安装依赖...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q

echo [3/3] 启动服务 http://127.0.0.1:8000 ...
start "" http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000

pause
