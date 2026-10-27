with open('device_subscribe.asm', 'r') as f:
    lines = f.readlines()

for l in lines[290:340]:
    print(l, end='')
