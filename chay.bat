@echo off
setlocal EnableExtensions
cd /d "%~dp0" || exit /b 1
set "VENV_PYTHON=%~dp0venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" goto :missing_venv
"%VENV_PYTHON%" -I -c "import sys; assert sys.prefix != sys.base_prefix, 'Chua vao dung venv'"
if errorlevel 1 goto :failed
set CAM_BACKEND=msmf
set CAM_DEBUG=0
rem Neu MySQL co mat khau root: bo rem dong duoi va dien mat khau.
rem set DB_PASSWORD=matkhau_cua_ban
echo Nho bat MySQL trong XAMPP. Mo trinh duyet: http://127.0.0.1:5000
"%VENV_PYTHON%" "%~dp0app.py"
if errorlevel 1 goto :failed
pause
exit /b 0

:missing_venv
echo Chua co venv. Hay chay cai_dat.bat truoc va cho OK - cai dat xong.
pause
exit /b 1

:failed
echo.
echo Web chua chay thanh cong. Gui noi dung loi phia tren de kiem tra.
pause
exit /b 1
