@echo off
REM ==========================================================================
REM deploy_pid_patch.bat - ADMIN REQUIRED (run as Administrator)
REM
REM Deploys the PID-gate patch (0x313 -> 0x314) to the installed Tobii
REM Platform Runtime service and restarts it. Evidence basis:
REM   pr_log0.txt: 'Starting ... with pids: (0x313)' / 'Target PID [0/1]:
REM   (0x0313)' - the service accepts ONLY ET5's PID 0x0313; our 5L is
REM   0x0314 and is rejected at the usb_manager match step.
REM   patch_pid_314.py already patched this repo copy (0x43e34c).
REM
REM Expectation after deploy: pr_log0.txt shows 'pids: (0x314)' and
REM   'Target PID [0/1]: (0x0314)'; device events should create a device
REM   (device_create lines / functional clients).
REM Rollback: restore .bak_pid313 over both copies and restart.
REM ==========================================================================

setlocal
set SRC=C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe
set DST=C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe
set LOG=C:\ProgramData\Tobii\Tobii Platform Runtime\IS5LEYETRACKER5\pr_log0.txt

echo === Verifying patched bytes at 0x43e34c of %SRC%
findstr /c:"0x314" /m nul >nul 2>&1
python -c "d=open(r'%SRC%','rb').read(); b=d[0x43e34c:0x43e351]; print('PATCH OK:', b); exit(0 if b==b'0x314' else 1)" || (
    echo ABORT: %SRC% is not patched - run patch_pid_314.py first!
    pause
    exit /b 1
)

echo === Stopping service
net stop "TobiiPlatformRuntime" 2>nul

echo === Backing up installed binary
if not exist "%DST%.orig" copy /Y "%DST%" "%DST%.orig" >nul

echo === Copying patched binary
copy /Y "%SRC%" "%DST%"

echo === Starting service
net start "TobiiPlatformRuntime" 2>nul

echo === Service state
sc query TobiiPlatformRuntime | findstr STATE

echo === Recent log lines
powershell -NoProfile -Command "Get-Content '%LOG%' -Tail 12"

echo === Done. Device still plugged in? Watch for device-created lines.
pause
