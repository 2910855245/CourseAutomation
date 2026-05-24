@echo off
chcp 65001 >nul
title 刷课系统 SaaS · 一键启动
cd /d "%~dp0"

set PORT=8000

echo ============================================
echo    刷课系统 SaaS · 一键启动
echo ============================================
echo.

:: [1/4] 检测 Python
echo [1/4] 检测 Python ...
set PYTHON=
python --version >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python
    goto :check_python_done
)
python3 --version >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python3
    goto :check_python_done
)
py -3 --version >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=py -3
    goto :check_python_done
)
echo ❌ 未找到 Python！请先安装 Python 3.7+
pause
exit /b 1

:check_python_done
for /f "tokens=*" %%i in ('%PYTHON% --version 2^>^&1') do set PY_VER=%%i
echo    使用: %PY_VER%

:: [2/4] 停止旧进程
echo.
echo [2/4] 停止旧进程 ...
taskkill /f /im python.exe /fi "WINDOWTITLE eq 刷课系统*" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo    已清理

:: [3/4] 检查依赖
echo.
echo [3/4] 检查依赖 ...
%PYTHON% -c "import fastapi, uvicorn" 2>nul
if %errorlevel% neq 0 (
    echo    ⚠ 依赖缺失，正在安装 ...
    %PYTHON% -m pip install -r requirements-api.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    %PYTHON% -m pip install lxml -i https://pypi.tuna.tsinghua.edu.cn/simple
)
echo    依赖就绪

:: [4/4] 启动服务器
echo.
echo [4/4] 启动服务器 (端口: %PORT%) ...
echo ============================================
echo    ✅ 服务器启动成功！
echo    访问地址: http://localhost:%PORT%
echo    后台运行中，关闭此窗口不会停止服务
echo ============================================
echo.

set PORT=%PORT%
start "刷课系统服务器" /MIN %PYTHON% run.py

echo 按任意键打开浏览器访问 ...
pause >nul
start http://localhost:%PORT%
pause
