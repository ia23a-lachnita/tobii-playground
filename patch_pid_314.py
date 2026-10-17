"""Patch compiled default PID list 0x313 -> 0x314 (length-preserving).

Evidence: pr_log0.txt 'Target PID [0/1]: (0x0313)' at every startup;
string '0x313' at file offset 0x43e34c of platform_runtime_service.exe,
adjacent to format ' platform runtime with pids: ('.

Operates on the repo copy. Deployment (admin) = replace
C:\\Program Files\\Tobii\\Platform Runtime\\platform_runtime_IS5LEYETRACKER5_service.exe
and restart service TobiiPlatformRuntime.
"""
import shutil, sys

PATH = r"C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe"
BAK = PATH + ".bak_pid313"
OFFSET = 0x43E34C
OLD = b"0x313"
NEW = b"0x314"

data = bytearray(open(PATH, "rb").read())
found = bytes(data[OFFSET:OFFSET + len(OLD)])
if found != OLD:
    sys.exit(f"ABORT: expected {OLD!r} at {hex(OFFSET)}, found {found!r}")
data[OFFSET:OFFSET + len(OLD)] = NEW
shutil.copy(PATH, BAK)
open(PATH, "wb").write(bytes(data))
chk = open(PATH, "rb").read()[OFFSET:OFFSET + len(NEW)]
print(f"patched @ {hex(OFFSET)}: {OLD.decode()} -> {NEW.decode()} | verify: {chk.decode()} | backup: {BAK}")
