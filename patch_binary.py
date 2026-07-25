import shutil

src = r'C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe'
dst = r'C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe'

with open(src, 'rb') as f:
    data = bytearray(f.read())

old_pattern = b'IS50F*|IS5FF*'
idx = data.find(old_pattern)
print(f'Found old pattern at offset 0x{idx:X}')

new_pattern = b'IS5*' + b'\x00' * 9
assert len(new_pattern) == len(old_pattern)

data[idx:idx+len(old_pattern)] = new_pattern

with open(src, 'wb') as f:
    f.write(data)

shutil.copy2(src, dst)
print(f'Copied patched binary to {dst}')
print('Binary patched successfully!')
print(f'Old: {old_pattern.decode()}')
print(f'New: IS5*')
