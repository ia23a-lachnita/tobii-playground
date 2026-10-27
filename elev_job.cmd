@echo off
REM Runs as SYSTEM via the TobiiElevJob scheduled task.
REM The agent overwrites C:\Users\xursc\projects\tobii_playground\elev_job_body.cmd
REM with the commands to execute, then runs:  schtasks /run /tn TobiiElevJob
set OUT=C:\Users\xursc\projects\tobii_playground\elev_job_out.log
echo === job start %DATE% %TIME% > "%OUT%"
call "C:\Users\xursc\projects\tobii_playground\elev_job_body.cmd" >> "%OUT%" 2>&1
echo exit=%ERRORLEVEL% >> "%OUT%"
exit /b 0
