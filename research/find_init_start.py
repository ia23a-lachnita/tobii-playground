with open('platform_runtime_service.exe', 'rb') as f:
    data = f.read()

for i in range(0x25f88a, 0x25e000, -1):
    if data[i:i+4] == b'\xcc\xcc\xcc\xcc':
        print(f"Function starts around file offset 0x{i+4:x}")
        break
