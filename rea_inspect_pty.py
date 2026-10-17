"""Run rea CLI commands with a PTY (works around rea's 'stdin is not a tty'
check when launched from non-interactive shells).

Usage: python rea_inspect_pty.py <rea-subcommand> [args...]
Env: GHIDRA_INSTALL_DIR / JAVA_HOME must be set for engine-backed commands.
"""
import os, sys, pty, subprocess

rea_dir = r"C:\Users\xursc\projects\headset_range_extension\rea"
node = r"C:\Users\xursc\AppData\Local\hermes\tools\node-26.7.0-win32-x64\node.exe"
cmd = [node, os.path.join(rea_dir, "scripts", "rea.mjs")] + sys.argv[1:]
out_path = sys.argv[1] and None  # placeholder

master, slave = pty.openpty()
log = open(r"C:\Users\xursc\AppData\Local\hermes\cache\scratch\rea_pty_output.txt", "wb")
# duplicate the log fd also into master so child writes are captured
p = subprocess.Popen(cmd, stdin=slave, stdout=log, stderr=log,
                     close_fds=True, cwd=rea_dir)
os.close(slave)
rc = p.wait()
with open(r"C:\Users\xursc\AppData\Local\hermes\cache\scratch\rea_pty_output.txt", "ab") as f:
    f.write(f"\nEXIT={rc}\n".encode())
print("rea exited", rc, "-> see scratch/rea_pty_output.txt")
sys.exit(rc)
