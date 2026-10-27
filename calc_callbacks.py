callbacks = {
    "ebx=1": 0x1400f8371 + 7 + 0x51f8,
    "ebx=2": 0x1400f834f + 7 + 0x4d9a,
    "ebx=3": 0x1400f832d + 7 + 0x533c,
    "ebx=4": 0x1400f8308 + 7 + 0x5161,
}

for k, v in callbacks.items():
    print(f"{k}: VA 0x{v:x}")
