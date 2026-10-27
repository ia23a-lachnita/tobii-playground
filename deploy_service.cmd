@echo off
REM Deploy the patched Tobii Platform Runtime service (un-gate a55c/a560 stream registration + subscribe bypass)
REM Must run in an elevated command prompt (Administrator).
setlocal
set SRC=C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe
set DST=C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe
set LOG=%TEMP%\tobii_deploy.log
echo === deploy start %DATE% %TIME% > "%LOG%"

net stop TobiiPlatformRuntime >> "%LOG%" 2>&1
timeout /t 3 /nobreak >nul
if not exist "%DST%.bak_a55c" (
  copy "%DST%" "%DST%.bak_a55c" >> "%LOG%" 2>&1
  echo backup ok >> "%LOG%"
) else (
  echo backup already exists >> "%LOG%"
)
copy /Y "%SRC%" "%DST%" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo COPY FAILED >> "%LOG%"
  goto :fail
)
echo copy ok >> "%LOG%"
net start TobiiPlatformRuntime >> "%LOG%" 2>&1
timeout /t 3 /nobreak >nul
sc query TobiiPlatformRuntime >> "%LOG%" 2>&1
echo === deploy done %DATE% %TIME% >> "%LOG%"
type "%LOG%"
exit /b 0

:fail
net start TobiiPlatformRuntime >> "%LOG%" 2>&1
type "%LOG%"
exit /b 1
