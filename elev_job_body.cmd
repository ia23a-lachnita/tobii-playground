@echo off
echo Starting service deployment...
net stop TobiiPlatformRuntime
timeout /t 2 /nobreak > nul
copy /Y "C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe" "C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe"
net start TobiiPlatformRuntime
echo Deployment completed successfully.
