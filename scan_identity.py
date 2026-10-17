"""Identity-surface scanner for the Tobii 5L->ET5 spoof investigation.

Byte-level first pass (no engine): find where host binaries gate on device
identity - USB VID/PID, serial patterns, model strings. Plain byte scan, so
results are observations to verify with rea deeper tools later.

Scans both ASCII and UTF-16LE encodings (Windows binaries mix them).
"""
import sys, re

TARGETS = {
    "platform_runtime_service.exe": "C:/Users/xursc/projects/tobii_playground/platform_runtime_service.exe",
    "tobii_stream_engine.dll": "C:/Users/xursc/projects/tobii_playground/tobii_stream_engine.dll",
    "tobii_stream_engine_portal.dll": "C:/Users/xursc/projects/tobii_playground/tobii_stream_engine_portal.dll",
    "Tobii.StreamEngine.Net.dll": "C:/Users/xursc/projects/tobii_playground/Tobii.StreamEngine.Net.dll",
}

# ASCII patterns and raw byte patterns
ASCII_PATTERNS = [
    b"0313", b"0314", b"2104",
    b"IS50F", b"IS5FF", b"IS510", b"IS5",
    b"EYETRACKER5", b"EYETRACKER5L", b"EyeTracker5", b"EyeTracker5L",
    b"IS5LEYETRACKER5", b"IS5EYETRACKER",
    b"vid_2104", b"pid_0314", b"pid_0313",
    b"VID_2104", b"PID_0314", b"PID_0313",
    b"5L", b"5l",
    b"Target Serial", b"serial pattern", b"Serial pattern",
]
RAW_PATTERNS = [
    (b"\x13\x03", "PID 0x0313 LE"), (b"\x14\x03", "PID 0x0314 LE"),
    (b"\x03\x13", "PID 0x0313 BE"), (b"\x04\x21", "VID 0x2104 LE"),
]

def utf16(s):
    return s.decode("ascii", "ignore").encode("utf-16-le")

def scan(path):
    try:
        data = open(path, "rb").read()
    except OSError as e:
        print(f"  !! cannot read: {e}")
        return
    print(f"\n=== {path.split('/')[-1]} ({len(data):,} bytes) ===")
    # UTF-16 variants of the ASCII patterns
    u16 = [utf16(p) for p in ASCII_PATTERNS]
    hits = {}
    for i, p in enumerate(ASCII_PATTERNS):
        for m in re.finditer(re.escape(p), data):
            k = f"ascii:{p.decode('ascii','ignore')}"
            hits.setdefault(k, []).append(m.start())
        for m in re.finditer(re.escape(u16[i]), data):
            k = f"utf16:{p.decode('ascii','ignore')}"
            hits.setdefault(k, []).append(m.start())
    for p, name in RAW_PATTERNS:
        for m in re.finditer(re.escape(p), data):
            hits.setdefault(f"raw:{name}", []).append(m.start())
    for k in sorted(hits):
        offs = hits[k]
        if len(offs) > 12:
            print(f"  {k:34s} x{len(offs)}  (first: {hex(offs[0])})")
        else:
            ctx = []
            for o in offs:
                chunk = data[max(0, o - 24):o + 40]
                printable = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                ctx.append(f"{hex(o)}: {printable}")
            print(f"  {k:34s} " + " | ".join(ctx))

for name, path in TARGETS.items():
    scan(path)
