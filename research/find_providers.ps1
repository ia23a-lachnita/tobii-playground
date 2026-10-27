$dir = "C:\Program Files\Tobii\Tobii EyeX"
Get-ChildItem -Path $dir -Filter "*.dll" | ForEach-Object {
    try {
        $asm = [System.Reflection.Assembly]::LoadFrom($_.FullName)
        try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }
        $match = $types | Where-Object { $_.GetInterfaces() | Where-Object { $_.Name -like "*SettingsProvider*" } }
        if ($match) {
            Write-Host "$($_.Name):"
            $match | ForEach-Object { Write-Host "   $($_.FullName)" }
        }
    } catch {}
}
