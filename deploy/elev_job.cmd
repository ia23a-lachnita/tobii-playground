@echo off
REM Runs via the TobiiElevUser scheduled task.
set OUT=C:\Users\xursc\projects\tobii_playground\elev_job_out.log
echo === job start %DATE% %TIME% > "%OUT%"
if exist "%~dp0elev_job_body.cmd" (
    call "%~dp0elev_job_body.cmd" >> "%OUT%" 2>&1
) else if exist "C:\Users\xursc\projects\tobii_playground\elev_job_body.cmd" (
    call "C:\Users\xursc\projects\tobii_playground\elev_job_body.cmd" >> "%OUT%" 2>&1
)
echo exit=%ERRORLEVEL% >> "%OUT%"
exit /b 0
