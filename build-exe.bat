@echo off
REM 打包 Pixort 网页版为单个 EXE，产物在 dist\Pixort.exe
setlocal
cd /d "%~dp0"

echo [1/2] 检查 PyInstaller ...
python -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
  echo       未安装，正在安装 ...
  python -m pip install --upgrade pyinstaller || goto :fail
)

echo [2/2] 正在打包 ...
python -m PyInstaller --clean --noconfirm pixort.spec || goto :fail

echo.
echo 打包完成： %CD%\dist\Pixort.exe
echo 把 exe 单独拷到任意文件夹即可运行，数据库与图片会生成在它旁边。
pause
exit /b 0

:fail
echo.
echo 打包失败，请查看上面的输出。
pause
exit /b 1