@echo off
rem ============================================================
rem  LinuxDOJO Windows launcher
rem    start.bat            WSL があれば全モード、なければ はじめて・基礎練習 を起動
rem    start.bat --windows  WSL があっても Windows 版で起動
rem ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"

if /i "%~1"=="--windows" goto native
where wsl.exe >nul 2>nul
if errorlevel 1 goto native
wsl.exe -e python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if errorlevel 1 goto wsl_not_ready
echo WSL で起動します。全モードを使えます。
wsl.exe --cd "%~dp0." -e bash ./start.sh %*
exit /b %errorlevel%

:wsl_not_ready
echo WSL の Ubuntu などで python3 が見つからないため、Windows 版で起動します。
echo 実践モードを使うには、Ubuntu で sudo apt install python3 を実行してください。
echo.

:native
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto run_native
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto run_native
echo Python 3.8 以上が見つかりません。
echo https://www.python.org/downloads/ からインストールしてください。
echo インストール画面では「Add python.exe to PATH」にチェックを入れます。
echo WSL を入れると、実践モードを含む全モードを使えます。PowerShell で wsl --install
pause
exit /b 1

:run_native
echo Windows 版で起動します。はじめて・基礎練習モードを使えます。
%PY% engine\main.py
set "CODE=%errorlevel%"
if not "%CODE%"=="0" pause
exit /b %CODE%
