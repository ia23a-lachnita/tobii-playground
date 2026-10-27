$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.Modules.dll"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }

$pm = $types | Where-Object { $_.FullName -eq "Tobii.EyeX.Interaction.Modules.Pointers.PointersModule" }
$m = $pm.GetMethod("RegisterFeatures", [System.Reflection.BindingFlags]"Public,NonPublic,Instance,Static")
$bytes = $m.GetMethodBody().GetILAsByteArray()
$mod = $asm.ManifestModule
for ($i = 0; $i -lt $bytes.Length - 4; $i++) {
    if ($bytes[$i] -in 0x6f, 0x28, 0x73) {
        $tok = [BitConverter]::ToInt32($bytes, $i + 1)
        try {
            $member = $mod.ResolveMember($tok)
            Write-Host ("{0:x4}: -> {1}.{2}" -f $i, $member.DeclaringType.Name, $member.Name)
        } catch {}
    }
}
