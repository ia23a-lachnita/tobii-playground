import shutil
import os

src = r'C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe'
dst = r'C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe'

# Back up the original before touching anything; patch a COPY so a bad pattern
# match (data.find returning -1) can never destroy the source binary.
backup = src + '.bak'
if not os.path.exists(backup):
    shutil.copy2(src, backup)
    print(f'Backed up original to {backup}')

with open(backup, 'rb') as f:
    data = bytearray(f.read())

old_pattern = b'IS50F*|IS5FF*'
idx = data.find(old_pattern)
if idx == -1:
    raise SystemExit('Pattern not found in binary - refusing to patch (source untouched)')
print(f'Found old pattern at offset 0x{idx:X}')

new_pattern = b'IS5*' + b'\x00' * 9
assert len(new_pattern) == len(old_pattern)

data[idx:idx+len(old_pattern)] = new_pattern

patched = src + '.patched'
with open(patched, 'wb') as f:
    f.write(data)

shutil.copy2(patched, dst)
print(f'Copied patched binary to {dst}')
print('Binary patched successfully!')
print(f'Old: {old_pattern.decode()}')
print(f'New: IS5*')
