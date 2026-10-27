$ErrorActionPreference = 'Continue'
$log = "$env:TEMP\tobii_reenum.log"
"=== reenum start $(Get-Date -Format 'HH:mm:ss') ===" | Out-File $log -Encoding utf8

$ids = @(
  'USB\VID_2104&PID_0314\IS510-100211404854',
  'USB\VID_2104&PID_0314&MI_00\7&42101EB&0&0000',
  'USB\VID_2104&PID_0314&MI_01\7&42101EB&0&0001'
)

foreach ($id in $ids) {
    $dev = Get-PnpDevice -InstanceId $id -ErrorAction SilentlyContinue
    if (-not $dev) { "not found: $id" | Out-File $log -Append -Encoding utf8; continue }
    "disable $id (status $($dev.Status))" | Out-File $log -Append -Encoding utf8
    Disable-PnpDevice -InstanceId $id -Confirm:$false -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 5
foreach ($id in $ids) {
    "enable $id" | Out-File $log -Append -Encoding utf8
    Enable-PnpDevice -InstanceId $id -Confirm:$false -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 8
Get-PnpDevice -InstanceId '*VID_2104*' | ForEach-Object {
    "{0} | {1} | {2}" -f $_.Status, $_.Class, $_.InstanceId | Out-File $log -Append -Encoding utf8
}
"=== reenum done $(Get-Date -Format 'HH:mm:ss') ===" | Out-File $log -Append -Encoding utf8
