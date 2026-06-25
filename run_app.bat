@echo off
chcp 65001 > nul
SET PYTHON=C:\QGIS\apps\Python312\python.exe
SET PORT=8501
SET DIR=%~dp0

IF NOT EXIST "%PYTHON%" (
    echo [오류] QGIS Python이 없습니다: %PYTHON%
    pause & exit /b 1
)

cd /d "%DIR%"

REM 이전에 실행 중인 Streamlit 종료
taskkill /F /IM python.exe /FI "WINDOWTITLE eq streamlit*" > nul 2>&1

REM Streamlit 이메일 프롬프트 건너뛰기
IF NOT EXIST "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
IF NOT EXIST "%USERPROFILE%\.streamlit\credentials.toml" (
    > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
    >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

echo.
echo  건축 동선 전환 분석기 시작 중...
echo  브라우저: http://localhost:%PORT%
echo  종료: Ctrl+C
echo.

REM 4초 후 기본 브라우저 열기
start /b cmd /c "ping -n 5 127.0.0.1 > nul & start http://localhost:%PORT%"

"%PYTHON%" -m streamlit run app.py --server.port %PORT% --browser.gatherUsageStats false
pause
