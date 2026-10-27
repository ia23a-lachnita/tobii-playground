with open('platform_runtime_service.exe', 'rb') as f:
    f.seek(0x27799b)
    b = f.read(16)
    print("Bytes at 0x27799b:", b.hex())
