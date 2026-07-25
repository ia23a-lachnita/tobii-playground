@echo off
echo Stopping Tobii Platform Runtime service...
net stop "TobiiPlatformRuntime" 2>nul
timeout /t 2 >nul

echo Copying patched binary...
copy /Y "C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe" "C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe"

echo Starting service...
net start "TobiiPlatformRuntime" 2>nul
echo Done!
pause
