#!/usr/bin/env python3
"""Decode the REAL subscribe dispatch:
  r12d==1 -> STREAM table at 0x1400f865c, index = ebx-1 (34 entries)
  r12d==0 -> PROPERTY table at 0x1400f86e4, index = ebx (26 entries)
For each case: extract the called wrapper and the static descriptor address (r8),
then dump the descriptor bytes and the wrapper's requested internal type.
"""
import re
import struct

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

PATH = "platform_runtime_service.exe"
IB = 0x140000000
d = open(PATH, "rb").read()
e = struct.unpack("<I", d[0x3C:0x40])[0]
coff = e + 4
nsec = struct.unpack("<H", d[coff + 2:coff + 4])[0]
so = coff + 20 + struct.unpack("<H", d[coff + 16:coff + 18])[0]
SECS = {}
for i in range(nsec):
    s = so + i * 40
    nm = d[s:s + 8].rstrip(b"\x00").decode("latin1")
    vs, va, rs, rp = struct.unpack("<IIII", d[s + 8:s + 24])
    SECS[nm] = (va, vs, rp, rs)


def r2f(rva):
    for nm, (va, vs, rp, rs) in SECS.items():
        if va <= rva < va + max(vs, rs):
            return rp + (rva - va)
    return None


def f2r(off):
    for nm, (va, vs, rp, rs) in SECS.items():
        if rp <= off < rp + rs:
            return va + (off - rp)
    return None


STR = {}
for m in re.finditer(rb"[\x20-\x7e]{4,}", d):
    r = f2r(m.start())
    if r is not None:
        STR.setdefault(IB + r, m.group().decode())

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True


def dis(a, b):
    o = r2f(a - IB)
    return list(md.disasm(d[o:o + b - a], a)) if o is not None else []


PRP = [
    "INVALID", "CUSTOM", "HEADPOSE", "GAZE_POINT", "RESPONSIVE_GAZE_POINT",
    "GAZE_ORIGIN", "EYE_POSITION_NORMALIZED", "ADVANCED_GAZE",
    "IMAGE_COLLECTION", "LOW_FREQUENCY_HEAD_POSITION",
    "LOW_FREQUENCY_HEAD_ROTATION", "MULTIPLE_FACES", "WEARABLE_LIMITED_IMAGE",
    "WEARABLE_PUPIL_DIAMETER", "WEARABLE_PUPIL_POSITION",
    "WEARABLE_EYE_OPENNESS", "WEARABLE_3D_GAZE_PER_EYE",
    "WEARABLE_3D_GAZE_COMBINED", "USER_POSITION_GUIDE_XY",
    "USER_POSITION_GUIDE_Z", "WEARABLE_FOVEATED",
    "WEARABLE_TRACKING_IMPROVEMENTS", "WEARABLE_CONVERGENCE_DISTANCE",
    "DIAGNOSTICS_IMAGE", "PRIMARY_CAMERA_IMAGE", "SECONDARY_CAMERA_IMAGE",
    "WEARABLE_IMPROVE_USER_POSITION_HMD", "WEARABLE_INCREASE_EYE_RELIEF",
    "PROXIMITY_DATA_COLLECTION", "WEARABLE_ENTRANCE_PUPIL_POSITION",
    "WEARABLE_DIAGNOSTICS_IMAGE", "WEARABLE_IMAGE", "DEVICE_LOG",
    "ABSOLUTE_EYE_OPENNESS", "ALGO_DEBUG", "WEARABLE_INTEROCULAR_DISTANCE",
]


def decode_table(tbl_va, count, label):
    print("\n===== %s table @0x%x (%d entries) =====" % (label, tbl_va, count))
    off = r2f(tbl_va - IB)
    rows = []
    for i in range(count):
        rel = struct.unpack("<i", d[off + 4 * i:off + 4 * i + 4])[0]
        rows.append(IB + rel)
    return rows


def case_info(case_va):
    """Return (wrapper_va, descriptor_va) for a case block."""
    wrapper = None
    desc = None
    for ins in dis(case_va, case_va + 0x40):
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            s = ins.operands[1]
            if s.type == X86_OP_MEM and s.mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + s.mem.disp
                if 0x140400000 < tgt < 0x140600000:
                    desc = tgt
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            wrapper = ins.operands[0].imm
            break
        if ins.mnemonic in ("jmp", "ret"):
            break
    return wrapper, desc


def wrapper_type(wrapper_va):
    """Find the internal stream type the wrapper requests (mov byte/dword ptr [reg+4], imm)."""
    if wrapper_va is None:
        return None
    out = []
    for ins in dis(wrapper_va, wrapper_va + 0x180):
        if ins.mnemonic == "mov" and len(ins.operands) == 2:
            dst, src = ins.operands
            if src.type == X86_OP_IMM and dst.type == X86_OP_MEM and dst.mem.disp in (0, 4, 8):
                out.append((dst.mem.disp, src.imm))
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            out.append(("call", ins.operands[0].imm))
            if len(out) > 6:
                break
    return out


stream_rows = decode_table(0x1400f865c, 34, "STREAM")
prop_rows = decode_table(0x1400f86e4, 26, "PROPERTY")

print("\n===== STREAM dispatch (r12d==1, index=enum-1) =====")
for i, case in enumerate(stream_rows):
    enum = i + 1
    nm = PRP[enum] if enum < len(PRP) else "?"
    w, desc = case_info(case)
    dbytes = ""
    if desc:
        fo = r2f(desc - IB)
        dbytes = " ".join("%02x" % b for b in d[fo:fo + 16])
    wt = wrapper_type(w) if w else None
    print("  enum %2d %-30s case 0x%x  wrapper %s  desc 0x%x [%s]" %
          (enum, nm, case, ("0x%x" % w) if w else "-", desc or 0, dbytes))
    if wt:
        print("        wrapper imms: %s" % (wt,))

print("\n===== PROPERTY dispatch (r12d==0, index=enum) =====")
for i, case in enumerate(prop_rows):
    w, desc = case_info(case)
    dbytes = ""
    if desc:
        fo = r2f(desc - IB)
        dbytes = " ".join("%02x" % b for b in d[fo:fo + 16])
    print("  prop %2d case 0x%x  wrapper %s  desc 0x%x [%s]" %
          (i, case, ("0x%x" % w) if w else "-", desc or 0, dbytes))
