$path = "C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.Interaction.Modules.dll"
$asm = [System.Reflection.Assembly]::LoadFrom($path)
try { $types = $asm.GetTypes() } catch [System.Reflection.ReflectionTypeLoadException] { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }

$t = $types | Where-Object { $_.FullName -like "*WindowsLookToMoveFeature*" }
Write-Host "Type: $($t.FullName)"
$t.GetMembers([System.Reflection.BindingFlags]"Public,NonPublic,Instance,Static") | ForEach-Object {
    Write-Host "  $($_.MemberType) $($_.Name)"
}
