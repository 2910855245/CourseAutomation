@echo off
chcp 65001 >nul
REM 本地一键启动：Rust 单一后端（API + 前端静态页 + OCR + 刷课 daemon 全在 :17017）
setlocal
cd /d "%~dp0"

echo === Rust 后端 (:17017) ===
set "RUST_BIN=%RUST_DAEMON_BIN%"
if "%RUST_BIN%"=="" set "RUST_BIN=D:\dev\rust-target\release\rust_worker.exe"
if not exist "%RUST_BIN%" (
  echo [!] 未找到 rust_worker.exe，尝试 cargo 构建...
  pushd rust_worker
  cargo build --release || (echo 构建失败 & popd & exit /b 1)
  popd
  set "RUST_BIN=D:\dev\rust-target\release\rust_worker.exe"
)
echo 访问地址：http://localhost:17017
echo.
start "rust-backend" "%RUST_BIN%"
