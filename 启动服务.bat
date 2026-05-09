@echo off
chcp 65001 >nul 2>&1
title 每日AI前沿 - 启动服务

echo.
echo  ═══════════════════════════════════════════
echo    每日AI前沿 服务启动器
echo  ═══════════════════════════════════════════
echo.

:: 检查数据库
if not exist "ai_news.db" (
    echo  [初始化] 数据库不存在，正在创建...
    python init_db.py
    echo.
)

:: 启动 Python 服务
echo  [启动] Python HTTP 服务 (端口 8899)...
start /b python serve.py
timeout /t 2 /nobreak >nul

:: 启动 cloudflared 隧道（免费，无需注册，自动获取公网地址）
echo  [启动] Cloudflare 隧道 (免费)...
start /b "" "%LOCALAPPDATA%\Programs\cloudflared.exe" tunnel --url http://localhost:8899
timeout /t 10 /nobreak >nul

echo.
echo  ═══════════════════════════════════════════
echo    服务已全部启动！
echo  ═══════════════════════════════════════════
echo.
echo  本地访问:  http://localhost:8899
echo  ngrok管理: http://127.0.0.1:4040
echo.
echo  [重要] 请复制下方地址分享给同事（手机电脑均可打开）
echo  该地址在本次运行期间有效，重启后会变更
echo  ═══════════════════════════════════════════
echo.
echo  按 Ctrl+C 停止所有服务
echo.

:: 保持运行
ping -n 99999 127.0.0.1 >nul 2>&1
