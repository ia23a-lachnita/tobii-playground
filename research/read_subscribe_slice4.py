with open('device_subscribe.asm', 'r') as f:
    lines = f.readlines()

for l in lines[430:520]:
    print(l, end='')
