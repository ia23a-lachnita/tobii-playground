$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.Modules.dll"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }

$t = $types | Where-Object { $_.FullName -like "*WindowsLookToMoveFeature*" }
$m = $t.GetMethod("UpdateSettings", [System.Reflection.BindingFlags]"Public,NonPublic,Instance,Static")
$mod = $asm.ManifestModule

# Read tokens from IL
$body = $m.GetMethodBody()
$bytes = $body.GetILAsByteArray()
for ($i = 0; $i -lt $bytes.Length - 4; $i++) {
    $opcode = $bytes[$i]
    if ($opcode -in 0x6f, 0x28, 0x7d, 0x7e, 0x80) { # call, callvirt, ldfld, ldsfld, stsfld
        $tok = [BitConverter]::ToInt32($bytes, $i + 1)
        try {
            $member = $mod.ResolveMember($tok)
            Write-Host ("{0:x4}: op={1:x2} tok={2:x8} -> {3}.{4}" -f $i, $opcode, $tok, $member.DeclaringType.Name, $member.Name)
        } catch {}
    }
}
