@echo off
echo ============================================
echo  Tobii Platform Runtime Installer
echo  Right-click this file and "Run as administrator"
echo ============================================
echo.

set EXE="C:\Users\xursc\AppData\Local\Temp\TobiiExtracted\Tobii\Tobii.EyeTracker5.Offline.Installer_4.183.0.30025\Platform\platform_runtime_IS5LEYETRACKER5_service.exe"

if not exist %EXE% (
    echo ERROR: Platform runtime not found at:
    echo   %EXE%
    echo.
    echo Please run the extraction step first.
    pause
    exit /b 1
)

echo Installing Tobii Platform Runtime service...
%EXE% installstart
if errorlevel 1 (
    echo.
    echo Installation failed. Trying alternative method...
    echo.
    
    echo Creating service via sc.exe...
    sc.exe create "TobiiPlatformRuntime" binPath= %EXE% start= auto
    sc.exe start "TobiiPlatformRuntime"
)

echo.
echo Checking for services...
sc.exe query "TobiiPlatformRuntime" 2>nul
sc.exe query type= all state= all | findstr -i tobii

echo.
echo Done! You can close this window.
pause
