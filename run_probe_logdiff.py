#!/usr/bin/env python3
"""Run the managed probe and show what the platform runtime logged during it."""
import os
import subprocess
import sys
import time

LOG = r"C:\ProgramData\Tobii\Tobii Platform Runtime\IS5LEYETRACKER5\pr_log0.txt"
APP = r"C:\Users\xursc\AppData\Local\TobiiGhost\app-1.14.1"
PROBE = sys.argv[1] if len(sys.argv) > 1 else "ghseq2.exe"
ARGS = sys.argv[2:] or ["20"]


def log_size():
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


before = log_size()
print("log size before: %d" % before)

p = subprocess.run([os.path.join(APP, PROBE)] + ARGS, cwd=APP,
                   capture_output=True, text=True, timeout=120)
print("--- probe stdout ---")
print(p.stdout[-3000:])
if p.stderr.strip():
    print("--- probe stderr ---")
    print(p.stderr[-2000:])

time.sleep(2)
after = log_size()
print("\nlog size after: %d (delta %d)" % (after, after - before))
if after > before:
    with open(LOG, "rb") as f:
        f.seek(before)
        tail = f.read().decode("utf-8", "replace")
    print("--- new service log lines ---")
    for line in tail.splitlines():
        print("  " + line[:230])
