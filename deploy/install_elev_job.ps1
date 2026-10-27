@echo off
REM One-time elevated bootstrap: registers a scheduled task that runs as SYSTEM.
REM After this succeeds, the agent can trigger admin operations WITHOUT any
REM further UAC prompt by writing a job file and running:
REM   schtasks /run /tn TobiiElevJob
setlocal
set JOB=%TEMP%\tobii_elev_job.cmd
set LOG=%TEMP%\tobii_elev_install.log
echo === install start %DATE% %TIME% > "%LOG%"

schtasks /create /tn TobiiElevJob /tr "%JOB%" /sc once /st 00:00 /rl HIGHEST /ru SYSTEM /f >> "%LOG%" 2>&1
echo create-exit=%ERRORLEVEL% >> "%LOG%"

REM make the task's action file
(
  echo @echo off
  echo set LOG=%%TEMP%%\tobii_elev_run.log
  echo echo === run %%DATE%% %%TIME%% ^> "%%LOG%%"
  echo call "%%~1"
  echo echo exit=%%ERRORLEVEL%% ^>^> "%%LOG%%"
) > "%JOB%"

echo === install done %DATE% %TIME% >> "%LOG%"
exit /b 0
