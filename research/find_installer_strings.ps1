$dir = "C:\Program Files\Tobii\Tobii EyeX"
Get-ChildItem -Path $dir -Filter "Tobii.EyeX.*.dll" | ForEach-Object {
    try {
        $asm = [System.Reflection.Assembly]::LoadFrom($_.FullName)
        try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }
        $installers = $types | Where-Object { $_.Name -like "*Installer*" }
        foreach ($inst in $installers) {
            $m = $inst.GetMethod("Install")
            if ($m) {
                $mod = $asm.ManifestModule
                $bytes = $m.GetMethodBody().GetILAsByteArray()
                for ($i = 0; $i -lt $bytes.Length - 4; $i++) {
                    if ($bytes[$i] -eq 0x72) { # ldstr
                        $tok = [BitConverter]::ToInt32($bytes, $i + 1)
                        try {
                            $str = $mod.ResolveString($tok)
                            if ($str -like "*Software\*" -or $str -like "*Tobii*") {
                                Write-Host "$($inst.FullName): ldstr '$str'"
                            }
                        } catch {}
                    }
                }
            }
        }
    } catch {}
}
