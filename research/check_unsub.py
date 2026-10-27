with open('func_273660_part2.asm', 'r') as f:
    for line in f:
        if '0x140273a90' in line:
            print("Unsubscribe function starts at 0x140273a90 (file offset 0x272e90)")
