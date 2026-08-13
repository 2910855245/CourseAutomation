@echo off
chcp 65001 >nul
echo ========================================
echo   网课助手 打包脚本
echo ========================================
echo.

cd /d "%~dp0"

:: 检查 PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [安装] PyInstaller...
    pip install pyinstaller
)

:: 检查依赖
echo [检查] 安装依赖...
pip install -r requirements_gui.txt -q

echo.
echo [打包] 开始打包...
echo.

pyinstaller ^
    --noconfirm ^
    --windowed ^
    --name "网课助手" ^
    --add-data "data;data" ^
    --add-data "..\HanSansCN_glyfHashedTables.pkl;." ^
    --hidden-import customtkinter ^
    --hidden-import scrapling ^
    --hidden-import scrapling.parser ^
    --hidden-import ddddocr ^
    --hidden-import openai ^
    --hidden-import httpx ^
    --hidden-import requests ^
    --hidden-import loguru ^
    --hidden-import dotenv ^
    --collect-all customtkinter ^
    --collect-all scrapling ^
    --collect-all ddddocr ^
    main.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败！
    pause
    exit /b 1
)

echo.
echo [完成] 打包成功！
echo 输出目录: dist\网课助手\
echo.

:: 复制数据文件
if exist "data" (
    echo [复制] 复制数据目录...
    xcopy /E /I /Y "data" "dist\网课助手\data" >nul
)

if exist "..\HanSansCN_glyfHashedTables.pkl" (
    copy /Y "..\HanSansCN_glyfHashedTables.pkl" "dist\网课助手\" >nul
)

echo.
echo ========================================
echo   打包完成！运行 dist\网课助手\网课助手.exe
echo ========================================
pause
