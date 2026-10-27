with open('device_subscribe.asm', 'r') as f:
    lines = f.readlines()

for l in lines[255:285]:
    print(l, end='')
