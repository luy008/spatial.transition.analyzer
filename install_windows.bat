@echo off
REM 건축 동선 전환 분석기 — Windows 설치 스크립트
REM QGIS Python 번들을 사용합니다.

SET PYTHON=C:\QGIS\apps\Python312\python.exe

echo === 건축 동선 전환 분석기 설치 ===
echo Python: %PYTHON%

IF NOT EXIST "%PYTHON%" (
    echo [ERROR] QGIS Python을 찾을 수 없습니다: %PYTHON%
    echo         QGIS가 설치되어 있는지 확인하세요.
    pause
    exit /b 1
)

echo.
echo [1/3] 패키지 설치 중...
"%PYTHON%" -m pip install --upgrade pip --quiet
"%PYTHON%" -m pip install -r requirements.txt --quiet

IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] 패키지 설치 실패. requirements.txt를 확인하세요.
    pause
    exit /b 1
)

echo.
echo [2/3] Streamlit 버전 확인...
"%PYTHON%" -m streamlit --version

echo.
echo [3/3] 설치 완료.
echo       실행: run_app.bat
echo.
pause
