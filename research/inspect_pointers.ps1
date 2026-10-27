$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.Modules.dll"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }

$warpTypes = $types | Where-Object { $_.FullName -like "*Pointers*" }
foreach ($t in $warpTypes) {
    Write-Host "=== $($t.FullName) ==="
    Write-Host "Methods:"
    $t.GetMethods([System.Reflection.BindingFlags]"Public,NonPublic,Instance,Static") | ForEach-Object { Write-Host "  $($_.ReturnType.Name) $($_.Name)($([string]::Join(', ', ($_.GetParameters() | ForEach-Object { $_.ParameterType.Name + ' ' + $_.Name }))))" }
}
