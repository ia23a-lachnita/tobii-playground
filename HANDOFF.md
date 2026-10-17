# HANDOFF.md — Tobii 5L → ET5 (cross-harness state log)

Last updated: 2026-10-17 (Hermes session). This file is the source of truth for
project state across agent harnesses (OpenCode / MimoCode / Hermes). Append a
dated entry at the end of every work block; commit + push.

## Objective

Get the Tobii Eye Tracker 5L (VID 2104, PID 0314, serial IS510-100211405834)
recognized as a non-L Eye Tracker 5 / ET5 (PID 0313, serial families IS50F/IS5FF)
so the entire ET5 software ecosystem (Tobii Ghost, Game Hub, Experience,
tobiifree, etc.) works with it unchanged. The 5L firmware speaks the same
TTP/TLV USB protocol family as the ET5 (already proven streaming on 5L), so the
hypothesis is: the host stack gates on identity (USB PID + serial string +
possibly EyeChip device-info), not on protocol.

Two strategy branches (both evaluated, decision pending — see Next Steps):
- A: **Host-side patch** — make the Windows stack accept IS510 (serial pattern
  patch of platform runtime ALREADY done, proved insufficient — service still
  won't bring the device up through the official stack).
- B: **USB-level virtualization** — present the 5L as an ET5 (PID 0313 +
  IS5xx serial) via a virtual USB driver or filter driver. Previous estimate:
  weeks + driver signing; revisit with `rea` (binary analysis may reveal that
  only a small gate needs flipping, or that the service speaks a plaintext
  protocol we can broker).

## Working state (as of git 1ddb2cb)

- `TobiiGazeDemo/Program.cs` — direct WinUSB TTP/TLV client, streams ~133 Hz,
  prints raw columns. This is the ground-truth protocol tool.
- `TobiiGazeVisualizer/` — full gaze overlay: One Euro filter, 9-point
  calibration (median + MAD outlier rejection + per-eye affine/ridge-poly +
  late fusion), LOOCV/retry-worst-point, V validation pass.
  Measured accuracy ~0.25° mean in-sample (Tobii-quality band).
- `tobii_eye_tracker.py` — Stream Engine ctypes client (rewritten 2026-09-06
  against real headers); educational, cannot enumerate the 5L (DLL v4.x too old).
- `patch_binary.py` + `replace_binary.bat` — platform-runtime serial pattern
  patch `IS50F*|IS5FF*` → `IS5*` (admin). Applied once; service stopped again.
- Display area geometry (measured, not guessed): tilt 5.0°, Y_BOTTOM 14mm,
  Z_BOTTOM −15mm, viewing distance 550mm, physical screen 597.9×336.2mm.

## Protocol reference (verified by streaming on the 5L)

- USB: WinUSB, MI_00, GUID {85C0F97C-E2B1-422A-92A9-5F96072E79D8}, EP IN 0x83,
  EP OUT 0x05 (0x04 also present), FILE_FLAG_OVERLAPPED required.
- Session control: vendor control transfers 0x41 (open) / 0x42 (close).
- Envelope OUT: [dir=0x00][pad 3][len_LE u32] + TTP. IN: envelope INCLUDED in
  length, TTP header at offset 8.
- TTP: 24-byte BE header, magic REQ 0x51 / RSP 0x52 / NOTIFY 0x53.
  Ops: HELLO 0x3E8, QUERY_REALM 0x640 (realm_type 0, no auth), SET_DISPLAY_AREA
  0x5A0, GET_DISPLAY_AREA 0x596, SUBSCRIBE 0x4C4, CAL_START 0x3F2,
  add-point 0x408 / compute 0x42F / apply 0x456 (from tobiifree, not yet used).
- Subscribe payload: 20 bytes, stream_id BE u16 patched at bytes 9–10
  (gaze_point = 0x0500). 3-corner display area: TL, TR, BL (BR implied).
- Gaze TLV row 0x1c columns (39): timestamp_us, eye_origin, gaze_point_3d,
  gaze_point_2d_norm, frame_counter, validity_L/R (0 valid, 4 not detected).
  Column encoding: type5/s64, type2/point3d, type3/point3d, type0x1d/u32…
- Firmware emits frames continuously even out of range; negative ADCS coords are
  normal at edges (do not drop them — historical freeze bug, fixed in b92040e).

## Tooling: rea (installed 2026-10-17, working)

- MCP server live for Hermes: `node C:/Users/xursc/projects/headset_range_extension/rea/scripts/rea.mjs mcp`
  (v6.5.0; the clone is shared with the headset_range_extension agent — that
  agent is actively using it; do NOT reinstall/modify/`git pull` that clone
  without coordinating; another concurrent rea install would also collide).
- Doctor: node 26.7.0 OK; Hopper missing (no Windows support), Ghidra not
  configured, IDA not configured. Engine-free tools available NOW:
  `inspect_pe_resources`, `inspect_managed_artifact`/`_members` (.NET static),
  artifact-graph (`extract_artifact`, `inspect_artifact` — ZIP inventory),
  CLI `analyze-javascript-application`.
- Windows native bundle exists in the clone (native/windows/build/manifest.json)
  so Ghidra-P0-on-Windows is viable once Ghidra 12.1.x + JDK 21 are installed
  (set GHIDRA_INSTALL_DIR / JAVA_HOME). ~600MB local download, no cost —
  pending go/no-go.
- Project-local OpenCode registration: `opencode.json` → mcp "rea",
  npx-pinned 6.5.0 (independent of the shared clone).

## Known bugs / open threads

1. **V validation pass does not enter** (last user report, unresolved): after
   calibration results screen, V leaves results displayed / top dots progress.
   Reproduce in TobiiGazeVisualizer, check CalibrationForm key handling.
2. Left/top edge tracking shorter than physical screen (eye-rotation limit at
   550mm; mitigation is display-area inset + poly extrapolation).
3. Per-region accuracy falls off from center (~0.5° at edges) — vertical gain
   residual; may improve with a head-stability gate + positioning guide
   (needs 0x1770/0x50e stream decode from tobiifree).

## Next steps (ranked)

1. With rea, inventory the identity surface of the host stack:
   `platform_runtime_service.exe` (in repo, 20MB), `TobiiGhost` app files,
   `middleware_client.dll`, `tobii_stream_engine.dll`(+ portal), Game Hub.
   Search strings for `0313`/`0314`, `IS50F`, `IS510`, `IS5`, model names;
   find where PID/serial gates the device bring-up; map the EyeChip
   device-info response path. Decide branch A vs B on evidence.
2. If branch A: extend patch_binary.py to the full gate set the analysis finds.
3. If branch B: evaluate USBIP/virtual-USB driver options on Windows; check
   whether the service accepts a device whose *strings* say ET5 while PID
   stays 0314 (string-only gate would be patch-free on the USB side).
4. Install Ghidra 12.1.4 + JDK 21 for deep PE analysis when a target needs
   decompilation (go/no-go with user — local download only).
5. Fix the V-key bug; then re-run full calibration + validation for a clean
   baseline before any spoof experiments.

## Changelog

- 2026-10-17 Hermes: rea verified installed/live (MCP + CLI); no new install
  made to avoid collision with active headset_range_extension install.
  Created HANDOFF.md + rea entry in opencode.json. Full project history
  recovered from OpenCode DB (7 sessions, 2026-07-21 → 2026-09-06).
