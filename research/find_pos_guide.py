import sys

with open('platform_runtime_service.exe', 'rb') as f:
    data = f.read()

targets = [
    b'Failed to subscribe to PRP_COMPOUND_STREAM_ENUM_USER_POSITION_GUIDE_XYZ',
    b'subscribe for User Position Guide stream',
    b'PRP_COMPOUND_STREAM_ENUM_USER_POSITION_GUIDE_XYZ',
    b'User Position Guide stream',
]

for t in targets:
    pos = 0
    found = 0
    while True:
        pos = data.find(t, pos)
        if pos == -1:
            break
        print(f'Found {t.decode("latin1")} at file offset 0x{pos:x}')
        pos += len(t)
        found += 1
    if not found:
        print(f'NOT FOUND: {t.decode("latin1")}')
