$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.exe"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }
$types | ForEach-Object { Write-Host $_.FullName }
