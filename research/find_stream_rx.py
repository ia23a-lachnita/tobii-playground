with open('platform_runtime_service.exe', 'rb') as f:
    data = f.read()

# Search backward from 0x266aa0 for 0xcc padding or prologue
for i in range(0x266aa0, 0x260000, -1):
    if data[i:i+4] == b'\xcc\xcc\xcc\xcc':
        print(f"Function starts around file offset 0x{i+4:x}")
        break
