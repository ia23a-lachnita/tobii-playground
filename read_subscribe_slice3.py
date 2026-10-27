with open('device_subscribe.asm', 'r') as f:
    lines = f.readlines()

for l in lines[200:290]:
    print(l, end='')
