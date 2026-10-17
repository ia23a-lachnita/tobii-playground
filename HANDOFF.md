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

0. **CONFIRMED GATE (2026-10-17):** the service's compiled PID list holds
   exactly one entry — ET5's 0x0313 (runtime log: `Target PID [0/1]:
   (0x0313)`, `Starting ... with pids: (0x313)`). Our device is 0x0314 →
   rejected at the usb_manager match step (events handled, device never
   created). Serial gate also present (`Target Serial pattern`), config key
   `target_serial_pattern` exists in pr_config.ini (= `IS510*|IS50F*|IS5FF*`,
   written Jul 24 17:56, never exercised — service was stopped the same
   minute). Repo copy of the service binary is patched 0x313→0x314
   (same-length string, offset 0x43e34c, backup `.bak_pid313`).
1. **USER-GATED (admin):** deploy the patched exe to
   `C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe`,
   restart service, watch pr_log0.txt for `pids: (0x314)` /
   `Target PID [0/1]: (0x0314)` and a device-created line; then launch
   Ghost / Game Hub and check device visibility.
2. Ghidra pass on the service binary: xref `Wrong VID:PID list. Different
   VIDs are not supported` (0x466c60) → the VID:PID list may be CONFIG-able
   (single VID only) — find the config key; xref `0x313` (0x43e34c) →
   confirm the string feeds the match list (not just the log); xref
   `Target Serial pattern` (0x466ca8) → matching semantics (fnmatch `IS5*`
   vs exact vs registry string). Ghidra 12.1.4 download started to
   `C:\Users\xursc\tools\ghidra`; JDK 21 (Corretto, JAVA_HOME set) present.
3. If the VID:PID list is config-able, prefer pr_config.ini over binary
   patch (no signature breakage).
4. License wall: licenseKey JSON schema found in utf16 strings
   (serialNumbers, platformTypes, models, dateValid, featureGroup,
   featureLocks, licenseKey, --SE-SIGNATURE--) at 0x442b90.. — map the
   verify path before promising Ghost features.
5. Fix the V-key bug; then re-run full calibration + validation for a
   clean baseline before further spoof experiments.

## Changelog

- 2026-10-17 Hermes: rea verified installed/live (MCP + CLI); no new install
  made to avoid collision with active headset_range_extension install.
  Created HANDOFF.md + rea entry in opencode.json. Full project history
  recovered from OpenCode DB (7 sessions, 2026-07-21 → 2026-09-06).
- 2026-10-17 Hermes RE sweep (byte-level evidence, see "Next steps" #0):
  * Live PnP: `USB\VID_2104&PID_0314\IS510-100211404854` → device serial
    IS510-100211404854 (previous notes said ...05834 — wrong, memory fixed).
  * Runtime log pr_log0.txt: service starts `with pids: (0x313)`,
    `Target Serial pattern: 'IS5*'` (patched), `Target PID [0/1]: (0x0313)`
    — ONE compiled PID entry, ET5 only; usb_manager logs "Handling device
    event" on every plug/unplug but the device is never created → match
    gate rejects 0x0314 at platmod (usb_manager.cpp:573 event, no
    device_create/device_open lines).
  * pr_config.ini exists (`[platform] target_serial_pattern = IS510*|IS50F*|IS5FF*`,
    mtime 2026-07-24 17:56, never exercised — service stopped same minute).
  * Static strings in platform_runtime_service.exe: `Target Serial pattern:
    '%s'` (0x466ca8), `Target PID [%u/%u]: (0x%04X)` (0x466cc8),
    `Wrong VID:PID list. Different VIDs are not supported` (0x466c60) →
    VID:PID list looks CONFIG-able (single VID); default pid string `0x313`
    @0x43e34c; device URI `tobii-usbttp://%u` (0x466a50); licenseKey JSON
    schema utf16 @0x442b90 (serialNumbers/platformTypes/models/dateValid/
    featureGroup/featureLocks/licenseKey/--SE-SIGNATURE--); device codenames
    IS5_DEVICE_CASTOR_EVAL / RUFIO_E_P0 @0x12af63b; platmod source paths
    platform_modules/castor/src/standard/platform_module_castor.cpp:381/385.
  * Repo scripts added: scan_identity.py, extract_regions.py, patch_pid_314.py.
  * Repo binary patched (deploy = admin/user-gated): `0x313`→`0x314`
    length-preserving @0x43e34c; backup platform_runtime_service.exe.bak_pid313.
  * Ghidra 12.1.4 download started (background) to C:\Users\xursc\tools\ghidra;
    JDK 21 Corretto already installed (JAVA_HOME set).
  * Hermes skill tobii-5l-re created (project rules + protocol facts).

## Ghidra pass 2026-10-17 (rea MCP, engine 12.1.4) — gate chain proven

Full chain recovered by decompilation (binaries stay gitignored; evidence in repo scripts):

- `platmod_start` (FUN_14025f600) receives the platmod config: count at +8,
  serial pattern ptr at +0x38, list at +0x44 = N x {uint16 vid @+0, uint16 pid @+2}.
  It loops N entries requiring ALL identical VIDs ("Wrong VID:PID list. Different
  VIDs are not supported"), logs `Target Serial pattern: '%s'` (src
  platform_module_castor.cpp:381) and `Target PID [%u/%u]: (0x%04X)` (src:385)
  per entry, then starts the usb_manager thread (usb_manager.cpp:573 events).
- Defaults come from the service config-struct builder FUN_1400e86d0:
  `MOV dword [RSP+0x2c], 0x03132104` (file 0xE7B26, imm32 @0xE7B2A,
  {VID 0x2104, PID 0x0313}), count=1 (`MOV dword [RSP+0x28], 1`), copied to
  instance+0xc (vid@+0x44 after +0x38 shift). UNIQUE occurrence in the file.
- Config-file route DEAD in this 5L binary: the loader FUN_14026e730 is a 5-byte
  stub `MOV EAX,0x3; RET` → always fails → "Platmod runtime configuration not
  set" always logged, values come from compiled defaults only. The
  `target_serial_pattern` ini key does not exist in the binary (0 hits,
  both encodings) - pr_config.ini is INERT for this service.
- Log string `0x313`→`0x314` @0x43e34c is cosmetic (startup log concatenation
  in main, no functional effect).

Patches applied to repo copy of platform_runtime_service.exe (bin/SHA on request):
1. gate byte file 0xE7B2C: 0x13→0x14 → compiled list = {VID 0x2104, PID 0x0314}
   (script patch_pid_list.py, backup .bak_gate313, unique-signature verified)
2. log string 0x313→0x314 @0x43e34c (script patch_pid_314.py, backup .bak_pid313)
Deploy = deploy_pid_patch.bat (admin) — verifies gate bytes c744242c04211403,
stops/copies/starts TobiiPlatformRuntime, tails pr_log0.txt. Expect after
deploy: `with pids: (0x314)`, `Target PID [0/1]: (0x0314)`, then device-created.
