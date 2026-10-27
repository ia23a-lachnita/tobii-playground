with open('platform_runtime_service.exe', 'rb') as f:
    data = f.read()

# Let's search where 0x140267060 is called from:
# Earlier we found RIP-rel ref at 0x25f88a (VA 0x14026048a)
# Let's inspect the caller of [rax + 0xb0]
print("Offset 0x25f88a in binary")
