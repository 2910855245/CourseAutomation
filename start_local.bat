@echo off
chcp 65001 >nul
REM 本地一键启动：Rust daemon(:17017) + OCR sidecar(:17018) + API(:8000)
setlocal
cd /d "%~dp0"

echo === 1/3 Rust 刷课 daemon (:17017) ===
set "RUST_BIN=%RUST_DAEMON_BIN%"
if "%RUST_BIN%"=="" set "RUST_BIN=D:\dev\rust-target\release\rust_worker.exe"
if not exist "%RUST_BIN%" (
  echo [!] 未找到 rust_worker.exe，尝试 cargo 构建...
  pushd rust_worker
  cargo build --release || (echo 构建失败 & popd & exit /b 1)
  popd
  set "RUST_BIN=D:\dev\rust-target\release\rust_worker.exe"
)
start "rust-daemon" "%RUST_BIN%"

echo === 2/3 OCR sidecar (:17018) ===
start "ocr-sidecar" python -m uvicorn ocr_sidecar:app --host 127.0.0.1 --port 17018

echo === 3/3 API 服务 (:8000) ===
echo 提示：如端口被旧实例占用，先执行 taskkill /F /IM rust_worker.exe 和
echo      netstat -ano ^| findstr ":8000" 清理后重跑本脚本。
echo.
python run.py
