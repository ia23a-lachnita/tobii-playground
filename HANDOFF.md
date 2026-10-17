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

## LIVE DEPLOY + MILESTONE 2026-10-17 (PID gate defeated)

- deploy_pid_patch.bat worked after my two fixes:
  (1) the first run died silently after the verify step — LF-only line endings,
  cmd.exe mis-parses LF batch files around if/parens. Fixed with CRLF + labels.
  (2) after the CRLF fix the script still exited right after the python verify
  line inside a real cmd console; the wrapper is unreliable so the deployment
  was done as 5 plain commands instead (net stop / backup copy / patched copy /
  net start / log tail) — no python, no control flow. Commands verbatim in
  project chat history.
- Service start type was DISABLED (from an earlier session that disabled it to
  free USB for direct TTP apps); set back to AUTO (sc config start= auto).
- LIVE RESULT — patched service started and the whole chain passed:
    "Starting IS5LEYETRACKER5 platform runtime with pids: (0x314),
     version: 1.37.4.0_f2b4e724c9"
    "Creating new device (device_id : 'IS510-100211404854')" (device_create)
    "Server created" / "Server listening for incoming connections"
  No "Wrong VID:PID list", no PID rejection. THE PID GATE IS DEFEATED LIVE.

## NEW WALL FOUND: firmware-version mismatch -> forced upgrade loop

- On bring-up: "Embedded version: 02a1a6a977, device version: 3.15.0-a36e7bc7"
- FUN_1402d2f30 (castor t2srv instance create) strcmps the platform's expected
  fw string vs the device-reported version. Equal -> normal create path.
  Different -> TTP opcode 0x31041 (FUN_1403b4640) -> "FW upgrade device mode
  init done" -> "Uploading new firmware to device tobii-usbttp://NN" ->
  5L rejects ET5 image ("Wrong manifest state 10 status 67") -> mode 4 ->
  re-added / re-plug loops; device stays flagged `fw_upgrading : true`.
- Ghost (TobiiGhost.exe, %LOCALAPPDATA%\TobiiGhost) connected on this state:
  command+subscription client created, "finished handshake, connection now
  valid", then dropped 14 ms later ("queued for destruction" /
  "Unknown client disconnected"). Consistent with refusing an fw_upgrading device.
- PATCH 3 (patch_fwcheck.py): 85 C9 74 47 -> EB 49 74 47 @ file 0x2D2465
  (VA 0x1402d3065 TEST ECX,ECX -> JMP 0x1402d30b0): normal create path is now
  unconditional — device fw accepted as-is, no upgrade trigger. Backup
  .bak_fwcheck. Applied to repo copy, awaiting admin deploy.
- Repo copy now carries THREE patches (imm gate 0xE7B2C, log string 0x43e34c,
  fw-check 0x2D2465). Installed copy carries patches 1+2 only.

## Capability-wall hunt 2026-10-17 late — full chain mapped (native, Ghidra/rea)

New wall after PID+FW gates: Ghost (ET5 client) says "We only discovered devices
that doesn't support eyetracking" while the runtime side is fully healthy
(algo init, plane config, PRP server listening, clients handshaking then
disconnecting). Live log decisive lines:
  Could not get sub platform type / lot id / integration id / calibration
  version / calibration date   (5L does not report ET5 identity fields)
  Found unmapped stream 0      (device-reported stream id list contains id 0)

Verified chain (all Ghidra assembly/pseudocode against the installed,
already-patched service binary):

1. setup_device_info (FUN_1402640d0, caps ctx = param_2):
   - +0xa5b0 = 1 only when tracker-properties, integration-type and platform-type
     queries all succeed (live: they did).
   - +0xae34 = sub-platform bucket: strncmp(first 4 bytes of integration-type
     string, "HMD") == 0 -> 1; else strcmp("Internal_display") -> 2; else 0.
     Magic confirmed: DAT_140469660 = 48 4d 44 ("HMD").
   - strcmp parity per identity field: +0x178 (sub platform type), +0x1d0 (lot
     id), +0x218 (integration id), +0x2b0 (calibration version), +0x348
     (calibration date) each gated on a ==1 presence flag, else log
     "Could not get <field>". 5L reports platform type (+0xfc present) but none
     of the five identity fields.

2. stream_type_receiver (FUN_140264c90, platmod_castor_setup_capabilities.cpp):
   - dispatch on device-reported stream id (param_1->[0]).
   - Mapped ids: 1,2,3,4,5,7,9,0xc,0xd,0xe,0xf,0x10,0x11,0x12,0x15.
     Id 0 -> default block: only logs "Found unmapped stream %d".
   - stream 5 (== the 5L's wire gaze subscribe id 0x0500 >> 8) handler at
     VA 0x14026501e appends the gaze capability entries:
     FUN_140263a90(ctx,0/1/2) + entry 3 at ctx+0xd8 array
     (fields 3/0x10/0x11 + count) UNLESS (a5b0==1 && ae34==1).
   - For "contains X" pre-checks the receiver scans the device id list at
     [ttp+0xf0]=count, [ttp+0xf4]=ids.

3. tracker_usb_ttp_t::get_capabilities (FUN_1402b7b90):
   - request op = 0x546 (request builder FUN_1402c5bd0: MOV [RSP+0x20], 0x546;
     the response-section pull is FUN_1402c1900(resp+0x28, 0x16)).
   - parse: entries 0x7c bytes apart at [container+0x10], count at
     [container+8]; per entry: u32 id at +0 (only ids < 0xe accepted),
     5-byte value at +4 compared against "true" (DAT_14112ea88 = 74 72 75 65
     00), boolean stored into the caps flag struct (0xb8 bytes, memset first).
   - get_capabilities_all (FUN_1402b7eb0) is the same walker over feature ids
     1000..1034 (0x3e9..0x40a), request op 0x547 (builder FUN_1402c5bf0).
   - for-each-stream dispatch into stream_type_receiver:
     FUN_140263c90 -> FUN_1402b3200 (vtable slot +0x48, tracker_usb_ttp_t
     interface) -> callback per id.

4. FW-gate (previous patch, re-confirmed): FUN_1402d2f30, strcmp embedded-vs-
   device version; equal -> normal create; differ -> upgrade opcode 0x31041 via
   FUN_1403b4640. Patch: JMP over the upgrade branch at file 0x2D2465.

Second opinion (antigravity, required before implementing): verdict "No — not
safe as clean fix, viable only as quick dirty test" on the naive patch
(default-block entry VA 0x140265284 -> JMP stream-5 handler, 5 bytes E9 95 FD
FF FF). Reason: default block is a catch-all for ALL unmapped ids, capability
registration is only the announcement layer (a separate demuxer must also
accept stream 0), and the root cause is more likely the wire id unpack:
(u8)0x0500 == 0 vs 0x0500 >> 8 == 5 — an endianness/truncation issue in the
id parse, which would fix capability negotiation AND data routing in one place.

Next experiment (probe_caps.py): stop the service, query the 5L directly over
WinUSB with op 0x546 (+0x547), dump the raw response. Ground truth: the exact
stream-id encoding the 5L returns (small ints? 16-bit 0x0500-style?) tells us
whether the fix belongs in the parse (16-bit id handling) or in the dispatch
table. Script written, verified with python -c compile; ready to run.

## probe_caps.py debugging pass 2026-10-18 — discovery now proven

Local API-level debugging (service can stay running — only CreateFile needs it
stopped). Fixed bugs found this pass:
1. Missing argtypes/restypes: without them ctypes truncates every HANDLE to
   32 bits on x64; SetupDiGetClassDevsW's return was truncated and every
   SetupAPI call silently failed → "0 interfaces scanned". All setupapi/
   kernel32/winusb functions now carry explicit restype + argtypes.
2. SetupDiEnumDeviceInterfaces takes FIVE args (set, DeviceInfoData=NULL,
   guid, memberindex, out-data) — the None slot is mandatory; a 4-arg call
   never fills the out struct.
3. SP_DEVICE_INTERFACE_DATA cbSize must be 32 on x64 (DWORD+GUID+DWORD+PTR);
   writing 40 makes the API reject the enum call with ERROR_INVALID_PARAMETER.
4. SP_DEVICE_INTERFACE_DETAIL_DATA_W layout: path starts at byte 4 (wchar
   index 2), not byte 8 — slicing at 4 clipped the leading backslash; parse
   up to the NUL terminator.
5. CreateFile failure check must accept both -1 and 0xFFFFFFFFFFFFFFFF as
   INVALID_HANDLE (restype=HANDLE surfaces the unsigned form).

VERIFIED locally with service RUNNING:
  discovery returns
  \?\usb#vid_2104&pid_0314&mi_00#7&42101eb&0&0000#{85c0f97c-e2b1-422a-92a9-5f96072e79d8}
  CreateFile returns ACCESS DENIED (err 5) while the service owns the device
  → the probe MUST run with the service stopped (already in the run docs).

## GROUND TRUTH 2026-10-18 — 5L capability list captured (probe_caps2.py)

probe_caps2.py (protocol-corrected v2) WORKED with the service stopped:
- Session open = vendor ctrl 0x41/0x41 (missing in v1 — device discarded frames).
- 24-byte TTP header, byte-exact vs TobiiGazeDemo/Program.cs.
- HELLO 0x3e8 -> RSP payload [00 00][02 size4 00 01 00 08] = stream count 8?? (demo list).
- QUERY_REALM 0x640 -> RSP ok.
- GET_CAPABILITIES op 0x546 (both payload variants, identical response, 427B):

  Wire grammar (decoded from the hexdump): [00 00] prefix, header
  [05|size=4|tag 0x000e0100][02|size=4|0x2710], then repeating units
  [05|size=4|tag 0x00022710][02|size=4|ID][14|size|strlen|"true"/"false"].
  Inner u32 of the 0x14 TLV = strlen (4 for "true", 5 for "false").

  0x546 STREAM CAPS — the 5L reports 13 stream ids 0..12 (SMALL ints on the
  wire, NOT 16-bit 0x0500-style — antigravity's unpack-truncation hypothesis
  is disproven):
    id:  0     1     2     3      4      5     6     7     8     9      10     11     12
    val: true  true  true  false  false  true  true  true  true  true   false  true   false
  - id 5 = gaze = TRUE (device DOES claim eyetracking capability).
  - id 0 = TRUE and is the only id unmapped in stream_type_receiver's
    dispatch table (logs "Found unmapped stream 0"; path only logs).
  - id 3 = FALSE. Service RE note: the stream-5 handler appends capability
    entry 3 (gaze) to the served array — entry index 3 correlates with this
    device-reported false. Prime suspect for Ghost's "doesn't support
    eyetracking" verdict.
- op 0x547 (caps_all / feature ids): all true, ids 0x3ec-0x3fc (1004-1020;
  service walks feature ids 1000..1034).

CONCLUSION: the 5L itself answers the capability query with gaze=true(id5),
yet Ghost refuses. Remaining suspects, in order:
  1. Ghost's managed filter (TobiiGhost.dll) keys on a specific caps entry —
     decompile it and read the exact check behind
     "We only discovered devices that doesn't support eyetracking."
  2. The 5 identity fields the 5L cannot report (sub platform type, lot id,
     integration id, calibration version, calibration date — live log
     "Could not get ...") used for model classification.
Next: RE TobiiGhost.dll (managed) for that string -> identify the checked
capability -> patch the service's caps relay for exactly that entry.

## Ghost eyetracking-wall ROOT CAUSE chain 2026-10-18 — ae34 gate proven

Ghost's "We only discovered devices that doesn't support eyetracking" traces to
the capabilities the SERVICE announces, not to Ghost itself:

stream_type_receiver (FUN_140264c90) appends the gaze capability entry
{type 3, 0x10, 0x11, present=1} at ctx+0xd8 (array base ctx+0x18f0, stride
0x88, count ctx+0xa0f0) from BOTH stream id 1 and stream id 5 handlers — but
ONLY when !(ctx+0xa5b0 == 1 && ctx+0xae34 == 1).

setup_device_info (FUN_1402640d0) computes ctx+0xae34 from the device-info TTP
response to op 0x354:

    uVar5 = 1;                                // DEFAULT = HMD-class
    if (info+0x78 != 0) {                     // integration-type string present
        uVar5 = strncmp(info, "HMD", 4) == 0  ? 1   // DAT_140469660 = "HMD"
             : strcmp(info, "Internal_display") == 0 ? 2
             : 0;
    }
    *(ctx+0xae34) = uVar5;                    // absent/errored field stays 1

Live log: a5b0 == 1 (device-info present). If the 5L's integration type either
starts with "HMD" or fails the +0x78 presence flag, ae34 == 1 -> gaze entry
skipped -> Ghost reports the device as eyetracking-incapable. That is the only
remaining hypothesis and it is decidable with one device query.

probe_info.py (new): replays op 0x354 over the proven probe_caps2.py transport,
dumps the raw device-info answer. Run block (admin cmd, repo root):

    net stop TobiiPlatformRuntime
    set PYTHONHOME=&& set UV_INTERNAL__PYTHONHOME=&& python probe_info.py
    net start TobiiPlatformRuntime
