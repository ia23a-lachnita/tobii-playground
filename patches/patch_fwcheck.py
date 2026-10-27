"""Neutralize the firmware-version-mismatch upgrade trigger.

Evidence (Ghidra 12.1.4 via rea, platform_runtime_service.exe, deployed 5L binary):
- FUN_1402d2f30 (castor t2srv instance create) reads the platform's expected
  firmware string from (struct+0x40), reads the device metadata over TTP
  (FUN_1402d4410), logs "Embedded version: %s, device version: %s" and does an
  inline strcmp of the two version strings.
  Live log:
    Embedded version: 02a1a6a977, device version: 3.15.0-a36e7bc7
  (they differ: the platform ships the ET5 firmware's version tag).
- If they are EQUAL it jumps to the normal create path (LAB_1402d30b0).
  If they DIFFER it sends TTP opcode 0x31041 to the device
  (FUN_1403b4640(dev, {0x31041, 0}, ...)) which puts the device into
  "FW upgrade device mode init done" -> the runtime tries to upload the ET5
  image, the 5L rejects it ("Wrong manifest state 10 status 67") and the
  device stays stuck flagged fw_upgrading : true, which makes clients
  (Ghost) drop right after the prp handshake.
- Decision point (x86-64):
    0x1402d3065: TEST ECX, ECX        ; 85 C9
    0x1402d3067: JZ   0x1402d30b0     ; 74 47  equal -> normal path
    0x1402d3069: MOV  RCX, [RBX+0x40] ; ... -> upgrade path
- Patch: 85 C9 -> EB 49 (JMP 0x1402d30b0) at file offset 0x2D2465:
  the normal create path is now unconditional — whatever the device
  firmware version is, it is accepted as-is and no upgrade is triggered.
  The trailing JZ becomes dead code.
Operates on the repo copy; deploy like the PID patch (admin copy + service
restart). Backup: platform_runtime_service.exe.bak_fwcheck
"""
import shutil, sys

PATH = r"C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe"
BAK = PATH + ".bak_fwcheck"
OFF = 0x2D2465
BEFORE = bytes([0x85, 0xC9, 0x74, 0x47])
AFTER = bytes([0xEB, 0x49, 0x74, 0x47])

data = bytearray(open(PATH, "rb").read())
if bytes(data[OFF:OFF + 4]) != BEFORE:
    sys.exit(f"ABORT: signature mismatch at {hex(OFF)}: "
             f"{bytes(data[OFF:OFF + 4]).hex(' ')} (expected {BEFORE.hex(' ')})")
data[OFF:OFF + 2] = AFTER[:2]
shutil.copy(PATH, BAK)
open(PATH, "wb").write(bytes(data))
chk = open(PATH, "rb").read()
assert bytes(chk[OFF:OFF + 4]) == AFTER
print(f"patched fw-check: {BEFORE.hex(' ')} -> {AFTER.hex(' ')} @ file {hex(OFF)} "
      f"(VA 0x1402d3065: TEST ECX,ECX -> JMP 0x1402d30b0 = unconditional normal path); "
      f"backup: {BAK}")
