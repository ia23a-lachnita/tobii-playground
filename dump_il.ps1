$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.Modules.dll"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }

$t = $types | Where-Object { $_.FullName -like "*WindowsLookToMoveFeature*" }
$m = $t.GetMethod("UpdateSettings", [System.Reflection.BindingFlags]"Public,NonPublic,Instance,Static")
$body = $m.GetMethodBody()
$bytes = $body.GetILAsByteArray()
Write-Host "UpdateSettings IL length: $($bytes.Length)"
Write-Host ($bytes | ForEach-Object { "{0:x2}" -f $_ }) -separator " "
