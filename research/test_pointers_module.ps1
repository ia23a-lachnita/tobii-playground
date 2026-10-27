$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.Modules.dll"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }

$pm = $types | Where-Object { $_.FullName -like "*PointersModule*" }
Write-Host "PointersModule: $($pm.FullName)"
$pm.GetConstructors() | ForEach-Object { Write-Host "ctor: $($_.ToString())" }
