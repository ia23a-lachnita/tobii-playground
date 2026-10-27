"""Patch the compiled VID:PID gate list 0x0313 -> 0x0314 in the code.

Evidence chain (rea/Ghidra, binary sha256 2aa99064...):
- FUN_1400e86d0 (service config-struct builder) writes the default gate as one
  immediate: file offset 0xE7FB6: C7 44 24 2C  = MOV dword [RSP+0x2c], imm32
  file offset 0xE7FBA: 04 21 13 03          = imm32 0x03132104
    layout: [VID 0x2104 (LE 04 21)][PID 0x0313 (LE 13 03)]
- That imm32 lands at instance+0x0c -> vid at instance+0x44, pid at +0x46,
  count(=1) at +8, exactly what platmod_start (FUN_14025f600) validates
  ("Wrong VID:PID list...") and logs ("Target PID [0/1]: (0x0313)").
- Config-file route is dead: the loader FUN_14026e730 is a 5-byte stub
  (MOV EAX,0x3; RET) - it always returns 3, hence the permanent
  "Platmod runtime configuration not set" warning and default-only values.

Patch: PID byte 0x13 -> 0x14 at file offset 0xE7FBC (single byte, part of the
imm32). count stays 1 (single-entry list {VID 0x2104, PID 0x0314}).

Operates on the repo copy. Deployment (admin) = replace
C:\\Program Files\\Tobii\\Platform Runtime\\platform_runtime_IS5LEYETRACKER5_service.exe
and restart service TobiiPlatformRuntime (see deploy_pid_patch.bat).
"""
import shutil, sys

PATH = r"C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe"
BAK = PATH + ".bak_gate313"
INSN_OFF = 0xE7B26          # C7 44 24 2C (mov dword [rsp+0x2c], imm32) [VA 0x1400e8726 -> file 949034+0xC00 verified by unique signature]
IMM_OFF = 0xE7B2A           # 04 21 13 03  (imm32 0x03132104)
PID_OFF = IMM_OFF + 2       # 13 -> 14

data = bytearray(open(PATH, "rb").read())
if bytes(data[INSN_OFF:INSN_OFF + 4]) != bytes([0xC7, 0x44, 0x24, 0x2C]):
    sys.exit(f"ABORT: instruction bytes mismatch at {hex(INSN_OFF)}: "
             f"{bytes(data[INSN_OFF:INSN_OFF+4]).hex()}")
if bytes(data[IMM_OFF:IMM_OFF + 4]) != bytes([0x04, 0x21, 0x13, 0x03]):
    sys.exit(f"ABORT: imm32 mismatch at {hex(IMM_OFF)}: "
             f"{bytes(data[IMM_OFF:IMM_OFF+4]).hex()} (0x03132104 expected)")
if data[PID_OFF] != 0x13:
    sys.exit(f"ABORT: PID byte at {hex(PID_OFF)} is {hex(data[PID_OFF])}, expected 0x13")

data[PID_OFF] = 0x14
shutil.copy(PATH, BAK)
open(PATH, "wb").write(bytes(data))
chk = open(PATH, "rb").read()
assert list(chk[IMM_OFF:IMM_OFF + 4]) == [0x04, 0x21, 0x14, 0x03]
print(f"patched PID gate: imm32 0x03132104 -> 0x03142104 "
      f"(VID 0x2104, PID 0x0313 -> 0x0314) @ file {hex(PID_OFF)}; backup: {BAK}")
