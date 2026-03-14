@echo off
chcp 65001 >nul

:: ============================================================
::  uninstall_task.bat
::  "SMarketing_DailyCollect" 작업을 스케줄러에서 제거합니다.
::  ※ 관리자 권한으로 실행하세요.
:: ============================================================

set TASK_NAME=SMarketing_DailyCollect

echo.
echo  "%TASK_NAME%" 작업을 삭제합니다...

schtasks /delete /tn "%TASK_NAME%" /f

if %errorlevel% equ 0 (
    echo  ✅ 삭제 완료.
) else (
    echo  ⚠️  작업이 없거나 삭제 실패 (이미 삭제됐을 수 있습니다).
)

echo.
pause