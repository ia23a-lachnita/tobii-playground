"""Extract full string context around the identity-gate regions found by
scan_identity.py in platform_runtime_service.exe."""
PATH = "C:/Users/xursc/projects/tobii_playground/platform_runtime_service.exe"

def show(start, end, label):
    data = open(PATH, "rb").read()
    chunk = data[start:end]
    # split on NULs, print printable strings with offsets
    print(f"\n=== {label} ({hex(start)}..{hex(end)}) ===")
    cur = b""
    cur_start = start
    for i, b in enumerate(chunk):
        if b == 0:
            if len(cur) >= 4:
                s = cur.decode("ascii", "replace")
                print(f"  {hex(cur_start)}: {s}")
            cur = b""
            cur_start = start + i + 1
        else:
            cur += bytes([b])
    if len(cur) >= 4:
        print(f"  {hex(cur_start)}: {cur.decode('ascii','replace')}")

show(0x466c40, 0x466e80, "Target PID / serial gate strings")
show(0x43e480, 0x43e640, "serial pattern strings (patched IS5*)")
show(0x43d950, 0x43db20, "service identity strings")
show(0x12af5c0, 0x12af6c0, "IS5_DEVICE_CASTOR_EVAL region")
