@echo off
setlocal EnableExtensions
cd /d "%~dp0" || exit /b 1
echo === CAI DAT THU VIEN CHO WEB ===
rem Python da kiem tra tren may cua ban; khong phu thuoc PATH / shortcut Store.
set "PYTHON_EXE=C:\Python\Python313\python.exe"
if not exist "%PYTHON_EXE%" goto :missing_python
"%PYTHON_EXE%" -I -c "import sys,struct; print('Python:',sys.executable); print('Version:',sys.version.split()[0]); assert sys.version_info >= (3,10), 'Can Python 3.10 tro len'; assert struct.calcsize('P') == 8, 'Can Python 64-bit'"
if errorlevel 1 goto :failed
if /I "%~1"=="--check-python" exit /b 0

if not exist "%~dp0venv\Scripts\python.exe" (
    "%PYTHON_EXE%" -m venv "%~dp0venv"
    if errorlevel 1 goto :failed
)
set "VENV_PYTHON=%~dp0venv\Scripts\python.exe"
"%VENV_PYTHON%" -I -c "import sys; print('Thu muc venv:',sys.prefix); assert sys.prefix != sys.base_prefix, 'Chua vao dung venv'"
if errorlevel 1 goto :failed

rem Dung CA bundle hop le cua pip trong venv, thay duong dan Python cu.
rem Chi ap dung cho cua so cai dat nay; van kiem tra chung chi HTTPS.
set "PIP_CERT=%~dp0venv\Lib\site-packages\pip\_vendor\certifi\cacert.pem"
if not exist "%PIP_CERT%" goto :missing_certificate
set "REQUESTS_CA_BUNDLE=%PIP_CERT%"
set "CURL_CA_BUNDLE=%PIP_CERT%"
set "SSL_CERT_FILE=%PIP_CERT%"
set "SSL_CERT_DIR="
set "PIP_CACHE_DIR=%~dp0.pip-cache"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_INPUT=1"
"%VENV_PYTHON%" -I -c "import os,ssl; ssl.create_default_context(cafile=os.environ['PIP_CERT']); print('CA bundle hop le:',os.environ['PIP_CERT'])"
if errorlevel 1 goto :failed

"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :failed
"%VENV_PYTHON%" -m pip install flask opencv-python mysql-connector-python requests numpy
if errorlevel 1 goto :failed
rem Chi dung dlib-bin da bien dich san, khong tu build dlib/CMake.
"%VENV_PYTHON%" -m pip install --only-binary=:all: dlib-bin
if errorlevel 1 goto :failed
"%VENV_PYTHON%" -m pip install face_recognition --no-deps
if errorlevel 1 goto :failed
"%VENV_PYTHON%" -m pip install face_recognition_models Click Pillow "setuptools<81"
if errorlevel 1 goto :failed
"%VENV_PYTHON%" -c "import face_recognition,cv2,flask,mysql.connector,requests; from PIL import Image; print('OK - cai dat xong')"
if errorlevel 1 goto :failed
echo Thu vien da cai vao venv cua web. Mo MySQL, sau do chay chay.bat.
if /I "%~1"=="--unattended" exit /b 0
pause
exit /b 0

:missing_python
echo Khong tim thay Python tai: %PYTHON_EXE%
echo Sua dong PYTHON_EXE thanh duong dan python.exe that neu da doi vi tri Python.
goto :failed

:missing_certificate
echo Khong tim thay CA bundle cua pip trong venv: %PIP_CERT%
goto :failed

:failed
echo.
echo CAI DAT CHUA THANH CONG. Da dung tai buoc loi, khong chay tiep.
echo Gui noi dung loi ngay phia tren de kiem tra. Chua chay chay.bat.
if /I "%~1"=="--unattended" exit /b 1
pause
exit /b 1
