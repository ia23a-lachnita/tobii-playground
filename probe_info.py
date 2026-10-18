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
    HELLO_PAYLOAD,
    OP_HELLO,
    OP_QUERY_REALM,
    Probe,
    drain,
    find_device,
    parse_frames,
)

OP_DEVICE_INFO = 0x354


def send_op(p, op, payload, label):
    """Send one op; drain prints every frame itself and returns raw bytes."""
    print(f"[i] {label}...", flush=True)
    try:
        p.send(op, payload)
    except Exception as exc:  # noqa: BLE001
        print(f"[!] send failed: {exc}", flush=True)
        return None
    resp = drain(p, 1.0, f"{label}: ")
    if not resp:
        print("    (no response)")
        return None
    frames = parse_frames(resp)
    hits = [f for f in frames if f[1] == op]
    if hits:
        plens = [f[2] for f in hits]
        print(f"    [i] answered op 0x{op:x}: {len(hits)} frame(s), plens={plens}")
    else:
        ops = sorted({f[1] for f in frames if f[1] is not None})
        print(f"    [!] no frame for op 0x{op:x}; saw ops "
              f"{[hex(o) for o in ops]}")
    return resp


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

        # HELLO with the demo's stream list — an empty hello gets only a bare
        # 32-byte ack (plen=0) and the device never negotiates.
        print("[i] HELLO (op 0x3e8, demo stream list)...", flush=True)
        p.send(OP_HELLO, HELLO_PAYLOAD)
        drain(p, 1.0, "hello: ")

        # Reference: realm (known-good op).
        send_op(p, OP_QUERY_REALM, b"\x00\x00", "realm 0x640")

        # The decisive query. The service sends an empty payload (arg 0 in
        # FUN_1403da6c0(info, 0, 0x354)); try empty, then 2 zero bytes, then a
        # 4-byte zero field for robustness.
        variants = [
            (b"", "device info 0x354 [empty]"),
            (b"\x00\x00", "device info 0x354 [00 00]"),
            (b"\x00\x00\x00\x00", "device info 0x354 [00000000]"),
        ]
        answered = False
        for payload, label in variants:
            resp = send_op(p, OP_DEVICE_INFO, payload, label)
            if resp:
                frames = parse_frames(resp)
                # First variant with a real answer wins; stop hammering.
                if any(f[1] == OP_DEVICE_INFO and f[2] for f in frames):
                    answered = True
                    break
        if not answered:
            print("[!] op 0x354 not answered by any payload variant — "
                  "integration type stays unknown")
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
