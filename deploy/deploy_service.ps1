$ErrorActionPreference = 'Stop'
$log = "$env:TEMP\tobii_deploy.log"
"=== deploy start $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $log -Encoding utf8

$src = 'C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe'
$dst = 'C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe'

try {
    Stop-Service TobiiPlatformRuntime -Force -ErrorAction Stop
    "service stopped" | Out-File $log -Append -Encoding utf8
} catch {
    "stop: $($_.Exception.Message)" | Out-File $log -Append -Encoding utf8
}
Start-Sleep -Seconds 3

if (-not (Test-Path "$dst.bak_a55c")) {
    Copy-Item $dst "$dst.bak_a55c" -Force
    "backup created ($dst.bak_a55c)" | Out-File $log -Append -Encoding utf8
}
Copy-Item $src $dst -Force
"copied $src to $dst" | Out-File $log -Append -Encoding utf8

$srcSha = (Get-FileHash $src -Algorithm SHA256).Hash.Substring(0,16)
$dstSha = (Get-FileHash $dst -Algorithm SHA256).Hash.Substring(0,16)
"src sha16=$srcSha  dst sha16=$dstSha" | Out-File $log -Append -Encoding utf8

$b = [System.IO.File]::ReadAllBytes($dst)
"dst bytes at a55c gate (0x264100): " + (($b[0x264100..0x264109] | ForEach-Object { $_.ToString('x2') }) -join ' ') | Out-File $log -Append -Encoding utf8
"dst bytes at a560 gate (0x264150): " + (($b[0x264150..0x264159] | ForEach-Object { $_.ToString('x2') }) -join ' ') | Out-File $log -Append -Encoding utf8
"dst bytes at subscribe bypass (0x272ae7): " + (($b[0x272ae7..0x272aee] | ForEach-Object { $_.ToString('x2') }) -join ' ') | Out-File $log -Append -Encoding utf8

try {
    Set-Service TobiiPlatformRuntime -StartupType Automatic
} catch { "startup: $($_.Exception.Message)" | Out-File $log -Append -Encoding utf8 }
Start-Service TobiiPlatformRuntime -ErrorAction Stop
Start-Sleep -Seconds 3
"service started: $((Get-Service TobiiPlatformRuntime).Status)" | Out-File $log -Append -Encoding utf8
"=== deploy done $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $log -Append -Encoding utf8
Write-Host (Get-Content $log -Raw)
