$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.Settings.dll"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }

$types | Where-Object { $_.Name -like "*SettingsProvider*" -or $_.Name -like "*UserSettings*" -or $_.Name -like "*SettingsStorage*" } | ForEach-Object {
    Write-Host "Type: $($_.FullName)"
    $_.GetMethods() | ForEach-Object { Write-Host "  $($_.Name)" }
}
