with open('device_subscribe.asm', 'r') as f:
    lines = f.readlines()

# Search for GAZE_POINT subscription in device_subscribe.asm
for idx, l in enumerate(lines):
    if '0x1402751a0' in l or '0x140275e10' in l or '0x1402768b0' in l or '0x1402777e0' in l:
        print(f"Line {idx}: {l.strip()}")
