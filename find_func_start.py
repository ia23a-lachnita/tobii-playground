import pefile

with open('platform_runtime_service.exe', 'rb') as f:
    data = f.read()

# Let's search backwards from 0xf0da9 for function prologues (push rbp / sub rsp / etc.)
# Or int3 padding (0xcc 0xcc ...)
for i in range(0xf0da9, 0xf0000, -1):
    if data[i:i+4] == b'\xcc\xcc\xcc\xcc':
        print(f"Function likely starts around file offset 0x{i+4:x}")
        break
