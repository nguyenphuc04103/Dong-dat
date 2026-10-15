@echo off
cd /d "%~dp0"
if not exist venv (echo Chua cai dat. Hay chay cai_dat.bat truoc. & pause & exit /b 1)
call venv\Scripts\activate.bat
set CAM_BACKEND=msmf
set CAM_SETTINGS=1
set CAM_DEBUG=0
rem set DB_PASSWORD=matkhau_cua_ban
echo Hop thoai driver webcam se hien ra (co the nam sau cua so khac).
echo Nho bat MySQL trong XAMPP truoc. Mo trinh duyet: http://127.0.0.1:5000
python app.py
pause
