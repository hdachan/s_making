@echo off
chcp 65001 >nul
setlocal

:: ============================================================
::  install_task.bat
::  실행하면 Windows 작업 스케줄러에
::  "SMarketing_DailyCollect" 작업을 등록합니다.
::
::  ※ 반드시 "관리자 권한으로 실행" 하세요.
::  ※ 이 파일은 collect_once.py 와 같은 폴더에 두세요.
:: ============================================================

:: ── 설정 ────────────────────────────────────────────────────
set TASK_NAME=SMarketing_DailyCollect

:: 수집 시각 (HH:MM 24시간 형식)
set RUN_TIME=09:00

:: Python 실행파일 경로 (.venv 사용 시 아래 경로 자동 감지)
set SCRIPT_DIR=%~dp0
set VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\pythonw.exe
set SYS_PYTHON=pythonw.exe

if exist "%VENV_PYTHON%" (
    set PYTHON_EXE=%VENV_PYTHON%
    echo [INFO] 가상환경 Python 사용: %VENV_PYTHON%
) else (
    set PYTHON_EXE=%SYS_PYTHON%
    echo [INFO] 시스템 Python 사용: pythonw.exe
)

set SCRIPT_PATH=%SCRIPT_DIR%collect_once.py
:: ─────────────────────────────────────────────────────────────

echo.
echo  등록할 작업 정보
echo  ───────────────────────────────────────────
echo  작업 이름  : %TASK_NAME%
echo  실행 시각  : 매일 %RUN_TIME%
echo  Python     : %PYTHON_EXE%
echo  스크립트   : %SCRIPT_PATH%
echo  ───────────────────────────────────────────
echo.

:: 기존 동일 이름 작업 삭제 (오류 무시)
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: 1단계: 작업 등록
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%PYTHON_EXE%\" \"%SCRIPT_PATH%\"" ^
  /sc DAILY ^
  /st %RUN_TIME% ^
  /rl HIGHEST ^
  /f

:: 2단계: PC를 늦게 켜도 밀린 수집 즉시 실행 (StartWhenAvailable)
powershell -NoProfile -Command "$t = Get-ScheduledTask -TaskName '%TASK_NAME%'; $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1); Set-ScheduledTask -TaskName '%TASK_NAME%' -Settings $s" >nul 2>&1

if %errorlevel% equ 0 (
    echo.
    echo  ✅ 작업 스케줄러 등록 완료!
    echo     매일 %RUN_TIME% 에 자동으로 수집됩니다.
    echo     PC를 늦게 켜도 켜자마자 밀린 수집을 바로 실행합니다.
    echo     로그: %SCRIPT_DIR%collect_log.txt
    echo.
    echo  [참고] 수집 시각을 바꾸려면 이 파일의 RUN_TIME 값을 수정 후 재실행하세요.
) else (
    echo.
    echo  ❌ 등록 실패. "관리자 권한으로 실행" 했는지 확인하세요.
)

echo.
pause