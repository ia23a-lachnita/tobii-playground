with open('platform_runtime_service.exe', 'rb') as f:
    data = f.read()

pos = 0
while True:
    pos = data.find(b'User Position Guide', pos)
    if pos == -1: break
    print(f"Found 'User Position Guide' at file offset 0x{pos:x}")
    pos += 1
