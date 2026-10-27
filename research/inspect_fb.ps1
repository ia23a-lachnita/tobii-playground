$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.exe"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }

$fb = $types | Where-Object { $_.Name -like "*FeatureBootstrapper*" }
$fb.GetMethods([System.Reflection.BindingFlags]"Public,NonPublic,Instance,Static") | ForEach-Object {
    Write-Host "Method: $($_.Name)"
    $b = $_.GetMethodBody()
    if ($b) {
        $bytes = $b.GetILAsByteArray()
        $mod = $asm.ManifestModule
        for ($i = 0; $i -lt $bytes.Length - 4; $i++) {
            if ($bytes[$i] -in 0x6f, 0x28, 0x73) {
                $tok = [BitConverter]::ToInt32($bytes, $i + 1)
                try {
                    $m = $mod.ResolveMember($tok)
                    Write-Host "   -> $($m.DeclaringType.Name).$($m.Name)"
                } catch {}
            }
        }
    }
}
