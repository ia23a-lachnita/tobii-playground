Add-Type -Path "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.Modules.dll" -ErrorAction SilentlyContinue

$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.Modules.dll"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try {
    $types = $asm.GetTypes()
} catch [System.Reflection.ReflectionTypeLoadException] {
    $types = $_.Exception.Types | Where-Object { $_ -ne $null }
}

Write-Host "Types matching Mouse / Warp / Feature / License:"
$types | Where-Object { $_.Name -match "Mouse|Warp|Feature|License|Gaze" } | ForEach-Object { $_.FullName }
