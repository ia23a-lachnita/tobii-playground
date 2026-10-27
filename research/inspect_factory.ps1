$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.Settings.dll"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }

$factory = $types | Where-Object { $_.Name -like "*SettingsProvidersFactory*" -or $_.Name -like "*BrandingConfigSettingsProvider*" }
foreach ($f in $factory) {
    Write-Host "=== $($f.FullName) ==="
    $f.GetConstructors() | ForEach-Object { Write-Host "  .ctor: $($_.ToString())" }
    $f.GetMethods([System.Reflection.BindingFlags]"Public,NonPublic,Instance,Static") | ForEach-Object { Write-Host "  Method: $($_.Name)" }
}
