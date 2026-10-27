$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.Settings.dll"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }

$t = $types | Where-Object { $_.Name -like "*Pointers*" }
foreach ($type in $t) {
    Write-Host "=== $($type.FullName) ==="
    $type.GetProperties() | ForEach-Object { Write-Host "  $($_.PropertyType.Name) $($_.Name)" }
}
