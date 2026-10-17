"""probe_info.py — replay the service's device-info TTP query (op 0x354) against
the 5L and dump the raw answer.

Why op 0x354: platform_runtime_service.exe's setup_device_info
(FUN_1402640d0) calls FUN_1403da6c0(param_3, 0, 0x354) -> FUN_1402b3370 to fill
the device-info struct, then computes:

    uVar5 = 1;                                  // default = "HMD class"
    if (info+0x78 != 0) {                       // integration type present?
        ae34 = starts_with(info, "HMD") ? 1
             : strcmp(info, "Internal_display") == 0 ? 2
             : 0;
    }
    ctx->ae34 = uVar5;                          // absent field stays 1

and the stream receiver appends the gaze capability entry ONLY when
    !(a5b0 == 1 && ae34 == 1)
-> ae34 == 1 (HMD class) suppresses the eyetracking capability entry, which is
exactly the Ghost failure ("We only discovered devices that doesn't support
eyetracking").

So the single decisive question: what does the 5L answer to op 0x354?
"""

import sys

from probe_caps2 import (
    OP_HELLO,
    OP_QUERY_REALM,
    Probe,
    drain,
    find_device,
    hexdump,
    parse_frames,
)

OP_DEVICE_INFO = 0x354


def send_and_dump(p, op, payload, label):
    """Send one op, drain the answer frames, return list of (op, payload)."""
    print(f"[i] {label}...", flush=True)
    try:
        p.send(op, payload)
    except Exception as exc:  # noqa: BLE001
        print(f"[!] send failed: {exc}", flush=True)
        return []
    data = drain(p, seconds=1.0, label=label)
    frames = parse_frames(data)
    for op_seen, pl in frames:
        status = "OK" if op_seen == op else f"?0x{op_seen:x}"
        print(f"    <- 0x{op_seen:x} plen={len(pl)} {status}")
        hexdump(pl)
    if not frames:
        print("    (no response)")
    return frames


def main():
    print("[i] looking for Tobii device (VID 2104, PID 0314/0313)...")
    path = find_device()
    if not path:
        print("[!] device not found (is it plugged in? is the service stopped?)")
        return 1
    p = Probe(path)
    try:
        p.open()
        if not p.session_open():
            print("[!] session open failed")
            p.close()
            return 2

        # HELLO first (same stream list as the working demo / probe_caps2).
        p.send(OP_HELLO, b"")
        drain(p, seconds=0.5, label="hello")

        # Reference: realm (known-good op).
        send_and_dump(p, OP_QUERY_REALM, b"\x00\x00", "realm 0x640")

        # The decisive query. The service sends an empty payload (arg 0 in
        # FUN_1403da6c0(info, 0, 0x354)); try empty, then 2 zero bytes, then a
        # 4-byte zero field for robustness.
        variants = [
            (b"", "device info 0x354 [empty]"),
            (b"\x00\x00", "device info 0x354 [00 00]"),
            (b"\x00\x00\x00\x00", "device info 0x354 [00000000]"),
        ]
        for payload, label in variants:
            frames = send_and_dump(p, OP_DEVICE_INFO, payload, label)
            if frames:
                # First answering variant wins; stop hammering the device.
                break
        print("[i] done")
        return 0
    finally:
        try:
            p.session_close()
        except Exception:  # noqa: BLE001
            pass
        p.close()


if __name__ == "__main__":
    sys.exit(main())
