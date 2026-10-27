@echo off
echo ============================================================
echo  Tobii Eye Tracker 5L - Full Setup Script
echo  RIGHT-CLICK ^> RUN AS ADMINISTRATOR
echo ============================================================
echo.

:: Stop existing service
echo [1/5] Stopping existing service...
sc stop "Tobii IS5LEYETRACKER5 Platform Runtime" >nul 2>&1
timeout /t 2 >nul
sc delete "Tobii IS5LEYETRACKER5 Platform Runtime" >nul 2>&1
timeout /t 1 >nul

:: Copy platform runtime to proper location
echo [2/5] Installing platform runtime to C:\Program Files\Tobii...
mkdir "C:\Program Files\Tobii" >nul 2>&1
mkdir "C:\Program Files\Tobii\Platform Runtime" >nul 2>&1
xcopy /E /Y "C:\Users\xursc\AppData\Local\Temp\TobiiExtracted\Tobii\Tobii.EyeTracker5.Offline.Installer_4.183.0.30025\Platform\*" "C:\Program Files\Tobii\Platform Runtime\" >nul 2>&1

:: Create service pointing to correct path
echo [3/5] Creating Windows service...
sc create "TobiiPlatformRuntime" binPath= "\"C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe\"" start= auto DisplayName= "Tobii Platform Runtime" >nul 2>&1

:: Start the service
echo [4/5] Starting service...
sc start "TobiiPlatformRuntime" >nul 2>&1
timeout /t 5 >nul

:: Verify
echo [5/5] Verifying...
sc query "TobiiPlatformRuntime" >nul 2>&1
if %errorlevel% == 0 (
    echo.
    echo SUCCESS! Service is running.
    echo.
    echo Now run: python tobii_eye_tracker.py
) else (
    echo.
    echo Service may not have started. Trying alternative...
    "C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe" installstart
)

echo.
pause
