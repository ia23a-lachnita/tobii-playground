# Tobii Eye Tracker 5L — Windows Compatibility & Enterprise Controller

Complete research codebase, reverse engineering documentation, binary patches, and high-performance PC mouse controller for running the **Tobii Eye Tracker 5L** peripheral (`IS510-100211404854`, PID `0x0314`) seamlessly on Windows with **Tobii Experience**, **Tobii Ghost**, and the **Tobii Stream Engine Enterprise API**.

---

## Quickstart

### 1. Enterprise PC & Mouse Control
Run the zero-lag mouse controller:
```powershell
python tobii_controller.py
```
- **Mouse Warp (Warp-on-Hotkey)**: Press or hold **`Caps Lock`** (or configured key in `mouse_settings.json`). The cursor instantly teleports to where you are looking with 0 latency.
- **Continuous Hands-Free Gaze Mouse**: Press **`F9`** to toggle continuous eye-tracking mouse control on/off.
  - Powered by an adaptive **1€ Filter (One Euro Filter)**: dead-steady during fixations (zero jitter on small buttons/links) with instantaneous response during saccades.
- **Dwell Clicking**: Hands-free left click after staring at a target for 550ms (configurable in `mouse_settings.json`).

### 2. Verify Enterprise Telemetry
Stream 2D Gaze, 6DOF Head Pose, 3D Eye Position, and User Presence simultaneously:
```powershell
python test_enterprise_features.py
```

### 3. Background Hardware Keepalive
Keeps the camera sensors and illuminators warmed up to eliminate cold-start latencies:
```powershell
python tobii_keepalive.py
```

---

## Why a Custom Controller vs. Official SDK?

1. **Tobii's Artificial Product Segmentation**:
   - On legacy trackers (Tobii EyeX, Eye Tracker 4C), Tobii included "Mouse Warp on Key" and desktop mouse control in consumer software (`Tobii Core Software`).
   - With the release of **Eye Tracker 5 / 5L**, Tobii stripped desktop mouse control and Windows Eye Control bridges out of consumer **Tobii Experience** to push users needing mouse/PC control or accessibility to **Tobii Dynavox** ($1,500+ specialized licenses) or the **Tobii Pro SDK**.
   - Analysis of `Tobii.EyeX.Interaction.Modules.dll` reveals that classes like `PointersModule`, `CursorWarper`, and `WindowsLookToMoveFeature` still exist in the assembly, but Tobii removed `PointersModule` from `Tobii.EyeX.Interaction.exe`'s `InitModules()` startup routine.
2. **Advantages of [tobii_controller.py](file:///C:/Users/xursc/projects/tobii_playground/tobii_controller.py)**:
   - Connects directly to the low-level `x64_patched_tobii_stream_engine.dll` C API.
   - Independent of Tobii Experience UI state.
   - Features a high-precision **1-Euro Filter**: solves the fundamental eye-tracking dilemma (heavy smoothing on fixations to eliminate ocular tremor, 0 filtering on saccades to eliminate cursor drag/lag).

---

## Core Binary Patches

The Tobii 5L is functionally identical to the ET5, but restricted by identity and capability gates in the host middleware:

1. **Gaze Point & Responsive Gaze Stream Table Gates** (`platform_runtime_service.exe`):
   - In `stream_type_receiver` (`FUN_140264c90`), stream 4 (`GAZE_POINT`) and stream 0x1d (`RESPONSIVE_GAZE_POINT`) are gated on device capability flags `[rbx + 0xa55c] == 1` (offset `0x264100`) and `[rbx + 0xa560] == 1` (offset `0x264150`).
   - Bypassed with `90 90` (NOPs), allowing stream IDs to populate the active stream table.
   - In `general_stream_subscribe` (`FUN_140273660`, offset `0x272ae7`), `75 40` patched to `eb 40` to force subscription acceptance.
2. **User Position Guide Calibration Fix** (`platform_runtime_service.exe`):
   - Compound stream 4 (`PRP_COMPOUND_STREAM_ENUM_USER_POSITION_GUIDE_XYZ`) previously triggered a blank screen during Tobii Experience calibration because 5L firmware rejected the subscribe opcode and did not activate the camera engine for compound stream 4 alone.
   - Offset `0x27799b`: `xor esi, esi; nop...` suppresses `TRACKER_ERROR_NOT_SUPPORTED`.
   - Offset `0x27857d`: `mov byte ptr [rcx+5], 1; mov byte ptr [rcx+0xb], 1; ret` automatically activates camera/illuminator stream 5 and gaze stream 0xb whenever User Position Guide is requested.
   - Offset `0x2785bd`: clean deactivation on unsubscribe.
3. **Display Area Flat-Screen Override**:
   - Offset `0x264000`: `[rbx + 0xae34]` forced to 0 (flat desktop display bucket).
4. **Stream Engine Client Library** (`tobii_stream_engine.dll`):
   - Patched x86 & x64 client DLLs to unconditionally report streams and internal capabilities as supported.

---

## Repository Structure

```
tobii_playground/
├── README.md                           # Master project guide & reference
├── HANDOFF.md                          # Comprehensive chronological engineering log
├── FINDINGS.md                         # Deep reverse engineering notes & protocol analysis
├── tobii_controller.py                 # Enterprise PC & Mouse Controller (Warp / 1€ Filter / Dwell)
├── mouse_settings.json                 # Controller configuration (hotkeys, smoothing, dwell timings)
├── test_enterprise_features.py         # Multi-stream verification suite (Gaze, Head Pose, Guide, Presence)
├── tobii_keepalive.py                  # Stream Engine keepalive background daemon
├── platform_runtime_service.exe        # Master patched platform runtime binary
├── x86_patched_tobii_stream_engine.dll # Patched 32-bit Stream Engine library (Tobii Ghost)
├── x64_patched_tobii_stream_engine.dll # Patched 64-bit Stream Engine library (Python / Native clients)
├── elev_job.cmd                        # Scheduled task entry point for zero-prompt silent elevation
│
├── deploy/                             # Service deployment & silent privilege escalation
│   ├── elev_job.cmd                    # Scheduled task worker script
│   ├── elev_job_body.cmd               # Service replacement and restart routine
│   ├── install_elev_job.ps1            # One-time scheduled task installer (highest runlevel)
│   └── deploy_service.cmd              # Command-line service installer
│
├── patches/                            # Automated binary patch scripts
│   ├── patch_user_pos_both.py          # Patches User Position Guide auto-activation & error suppression
│   ├── patch_service_a55c_gate.py      # Patches stream 4 / 0x1d registration gates
│   ├── patch_service_display_area.py   # Patches display area bucket
│   ├── patch_x86_subscribe_gate.py     # Patches x86 client DLL subscription validation
│   └── make_patched_dlls.py            # Automated DLL patch generator
│
├── research/                           # Reverse engineering archive & diagnostic tooling
│   ├── asm/                            # Disassembled assembly dumps of critical runtime routines
│   ├── bin/                            # Binary payloads and TTP frame captures
│   ├── logs/                           # Historical telemetry & diagnostic probe logs
│   ├── map_stream_ladder.py            # Decompiles & maps TTP stream dispatch ladder
│   ├── probe_all_enterprise_subs.py    # Probes subscription return codes across all API functions
│   ├── find_mouse_features.py          # Scans Tobii assemblies for Pointer & MouseWarp classes
│   └── ...                             # 100+ historical disassemblers, analyzers, and scanners
│
├── TobiiGazeVisualizer/                # C# WinUSB standalone real-time gaze visualization app
└── TobiiGazeDemo/                      # C# low-level WinUSB TTP/TLV protocol streamer
```

---

## Silent Service Deployment Pipeline

To deploy patched binaries into `C:\Program Files\Tobii\Platform Runtime\` without interactive UAC prompts:
```powershell
schtasks /run /tn TobiiElevUser
```
This triggers [deploy/elev_job.cmd](file:///C:/Users/xursc/projects/tobii_playground/deploy/elev_job.cmd) -> [deploy/elev_job_body.cmd](file:///C:/Users/xursc/projects/tobii_playground/deploy/elev_job_body.cmd) with elevated privileges, cleanly stopping `TobiiPlatformRuntime`, replacing the executable, and restarting the service.
