@echo off
setlocal
set SRC=C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe
set DST=C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe
set LOGDIR=C:\ProgramData\Tobii\Tobii Platform Runtime\IS5LEYETRACKER5

echo === Admin check ===
net session >nul 2>&1
if errorlevel 1 goto NOTADMIN
echo OK - running elevated

echo === Verify patched gate bytes in repo copy (0xE7B26) ===
python -c "import sys; d=open(r'%SRC%','rb').read(); b=d[0xE7B26:0xE7B2E]; print('GATE bytes:', b.hex(' ')); sys.exit(0 if b==bytes.fromhex('c744242c04211403') else 1)"
if errorlevel 1 goto BADREPO

echo === Stopping service ===
net stop TobiiPlatformRuntime

echo === Backing up installed binary ===
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set TS=%%t
copy /y "%DST%" "%DST%.bak_%TS%" || echo WARN: no backup (installed copy maybe already replaced)

echo === Copying patched binary ===
copy /y "%SRC%" "%DST%"
if errorlevel 1 goto COPYFAIL
python -c "import sys; d=open(r'%DST%','rb').read(); b=d[0xE7B26:0xE7B2E]; print('INSTALLED GATE bytes:', b.hex(' ')); sys.exit(0 if b==bytes.fromhex('c744242c04211403') else 1)"
if errorlevel 1 goto BADINST

echo === Starting service ===
net start TobiiPlatformRuntime
sc query TobiiPlatformRuntime

echo === Deployed OK. Replug USB, then tail log ===
echo === Recent log lines ===
powershell -NoProfile -Command "Get-Content -Tail 15 '%LOGDIR%\pr_log0.txt'"
exit /b 0

:NOTADMIN
echo ============================================
echo NOT ELEVATED. Right-click cmd - Run as administrator, then:
echo   C:\Users\xursc\projects\tobii_playground\deploy_pid_patch.bat
echo ============================================
pause
exit /b 1

:BADREPO
echo ============================================
echo ABORT - repo copy is NOT patched. Run patch_pid_list.py first.
echo ============================================
pause
exit /b 1

:COPYFAIL
echo ============================================
echo ABORT - copy to Program Files failed.
echo ============================================
pause
exit /b 1

:BADINST
echo ============================================
echo ABORT - installed bytes wrong after copy. Restore backup manually.
echo ============================================
pause
exit /b 1
