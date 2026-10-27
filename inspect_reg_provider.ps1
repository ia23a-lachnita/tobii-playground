$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.Foundation.dll"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }

$t = $types | Where-Object { $_.FullName -like "*RegistrySettingsProvider*" }
Write-Host "=== $($t.FullName) ==="
$t.GetConstructors([System.Reflection.BindingFlags]"Public,NonPublic,Instance,Static") | ForEach-Object { Write-Host "  .ctor: $($_.ToString())" }
$t.GetFields([System.Reflection.BindingFlags]"Public,NonPublic,Instance,Static") | ForEach-Object {
    Write-Host "  Field: $($_.FieldType.Name) $($_.Name) = $($_.GetValue($null))"
}
