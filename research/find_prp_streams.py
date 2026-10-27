import re
data = open('platform_runtime_service.exe', 'rb').read()
matches = sorted(set(re.findall(rb'PRP_[A-Z0-9_]+', data)))
for m in matches:
    if b'STREAM' in m:
        print(m.decode())
