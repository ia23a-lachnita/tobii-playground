# Tobii 5L → ET5 spoof — consolidated findings

Working notes for the ongoing effort. Updated as evidence lands.
Source of truth for continuity = this file + `HANDOFF.md`.

Date: 2026-10-25 (session `20261025_173625_9cdc9c` continuation)

---

## 1. Ground truth established this session

### 1.1 Export-directory semantics (both DLLs)
- Export directory has `Base = 1`, EAT indexed **0-based** ⇒ function index = ordinal − 1.
- Two independent stdlib parsers (`ordtruth.py`, `ordproof.py`) agree.
- ⇒ The earlier "3 of 4 force-true stubs landed on wrong exports" claim was an
  **off-by-one parser bug and is retracted**. The deployed x86 stubs land on the
  right exports.

### 1.2 Canonical export → file offset map (verified, not guessed)

x86 `tobii_stream_engine.dll` (imagebase 0x10000000, `.text` file = rva − 0x4600):

| export | rva | file offset |
|---|---|---|
| `tobii_stream_supported` | 0x11d630 | 0x11ca30 |
| `tobii_capability_supported` | 0x11d790 | 0x11cb90 |
| `tobii_internal_stream_supported` | 0x1245b0 | 0x1239b0 |
| `tobii_internal_capability_supported` | 0x124710 | 0x123b10 |

x64 `tobii_stream_engine.dll` (imagebase 0x180000000, `.text` file = rva − 0xc00):

| export | rva | file offset |
|---|---|---|
| `tobii_stream_supported` | 0x1410e0 | 0x1404e0 |
| `tobii_capability_supported` | 0x1412e0 | 0x1406e0 |
| `tobii_internal_stream_supported` | 0x14a410 | 0x149810 |
| `tobii_internal_capability_supported` | 0x14a610 | 0x149a10 |

### 1.3 Deployed x86 DLL — CORRECT EXPORTS, but a LATENT STACK BUG in the case patch
`pristine → deployed` diff is exactly 6 regions, nothing else:

| file offset | pristine | deployed | meaning |
|---|---|---|---|
| 0x11ca30 (13 B) | `55 8b ec 83 e4 f8 51 53 56 8b 75 08 57` | `8b 4c 24 0c c7 01 01 00 00 00 33 c0 c3` | force-true `tobii_stream_supported` |
| 0x11cb90 (13 B) | prologue | same stub | force-true `tobii_capability_supported` |
| 0x1239b0 (13 B) | prologue | same stub | force-true `tobii_internal_stream_supported` |
| 0x123b10 (13 B) | prologue | same stub | force-true `tobii_internal_capability_supported` |
| 0x12d58c (1 B) | `ba` | `b0` | case patch |
| 0x12d58e..0x12d59c (15 B) | `00 00 00 e8 fa 58 01 00 84 c0 5f 0f 95 c0 5e` | `90 ×15` | case patch (call nop'd) |

x86 stub ABI: `8b 4c 24 0c` = `mov ecx,[esp+0xc]` (3rd arg, cdecl) →
`mov dword ptr [ecx],1` → `xor eax,eax` → `ret`. Correct for `__cdecl` x86.

### 1.4 Deployed x64 DLL — BROKEN
- The 4 export entry points are **byte-identical to pristine** ⇒ the intended
  force-true patch was never applied to the exports.
- A bogus 5-byte JMP was planted inside an unrelated function (destroys a
  `mov rcx,[rcx+0x4f0]` + a following call) and its target is `int3` padding.
- ⇒ Repair = restore pristine x64, then patch the 4 export entries.

### 1.5 Repo artifact `x86_patched_tobii_stream_engine.dll` — CORRUPT
- 2 068 844 bytes vs pristine 2 068 840 ⇒ 4 bytes inserted without updating the
  section table ⇒ export directory unreadable. Must be regenerated from pristine.

---

## 2. Service-side root cause of the gaze failure

`platform_runtime_IS5LEYETRACKER5_service.exe`
(sha256 `cd9189445db2a32a…` — **identical to the repo copy**
`platform_runtime_service.exe`, so the repo patches are already deployed).

Ghidra (rea, `FUN_140264c90` = stream_type_receiver, x86-64):
- `0x140264c9f  MOV EAX,[RCX]` — stream id
- dispatch ladder of `CMP EAX,imm` / `JNZ next`:
  1 → 4 → 2 → 0x11 → **5** → 0xc → 9 → 0xe → 0xf → 3 → 7/0xd → 0x10 → 0x12 → 0x15 → default
- **id 5 handler body starts at 0x140265027**
  (`XOR EDX,EDX; MOV RCX,RBX; CALL 0x140263a90` ×3 with EDX = 0,1,2, then the
  capability append at 0x14026504b…0x1402650d6).
- **id 5 comparison is at 0x14026501e** (`83 f8 05` + `JNZ 0x1402650ef`).
- default / unmapped block at **0x140265284**: `LEA RDI,[0x1404696a0]`,
  `MOV EDX,0x5c`, `strnlen`, log `"Found unmapped stream %d"`, `RET`.
- capability append gate: `if ([RBX+0xa5b0] != 1 || [RBX+0xae34] != 1)`.
  With `ae34` forced to 0 (already deployed) the append **does** happen for id 5.

Live evidence: `pr_log0.txt` contains exactly one `Found unmapped stream 0`;
the gaze capability is therefore never published ⇒ the client subscribe returns
`TOBII_ERROR_NOT_SUPPORTED`.

**Inference (important):** if id 5 had ever arrived, the capability *would* have
been appended (ae34 = 0 ⇒ gate open) and subscribe would have succeeded. It did
not ⇒ **the 5L announces gaze as stream id 0 and id 5 never arrives.**
⇒ Remap id 0 onto the id-5 handler; id 5 does not need to keep working.

### 2.1 VA → file offset for the service
`.text` va = 0x1000, rp = 0x400 ⇒ **file = rva − 0xc00** (imagebase 0x140000000).

| VA | file offset | content |
|---|---|---|
| 0x14026501e | 0x26441e | `83 f8 05` + `JNZ` — id-5 comparison |
| 0x140265027 | 0x264427 | id-5 handler body |
| 0x1402650ef | 0x2644ef | else chain |
| 0x140265284 | 0x264684 | default / unmapped block |

### 2.2 Bugs in the existing repo script `patch_stream0_gaze.py`
1. **Stale signature**: expects `488d3d153d2000` at 0x264684; the real bytes are
   `488d3d15442000` (disp = 0x204415 → target 0x1404696a0). The script aborts.
2. **Wrong jump target**: it jumps to 0x14026501e, which is the *comparison*, not
   the handler. Landing there with EAX = 0 → `CMP EAX,5` fails → walks the else
   chain → back to the default block → logs the same warning. The patch as
   written cannot work.
3. It also over-routes: jumping the whole default block sends *every* unmapped
   id to the gaze handler.

### 2.3 Chosen service patch (1 byte)
`0x14026501e`: `83 f8 05` → `83 f8 00` ⇒ `CMP EAX,0`.
- id 0 ⇒ ZF=1 ⇒ falls through into the id-5 handler at 0x140265027 ⇒ gaze
  capability published.
- id 5 ⇒ now falls into the else chain ⇒ ends in the default block ⇒ logged as
  unmapped. Acceptable: id 5 is never sent by the 5L (proved above), and the
  capability is already published by then.
- every other id keeps its current behaviour.

Antigravity second opinion was taken on the byte-level alternatives (9-byte
two-test slot patch, default-block JMP, stack-balance of the x64 stub). It
flagged that a 9-byte `83 f8 00 74 04 83 f8 05 74 ff` sequence **overflows the
9-byte slot by one byte** and would clobber the handler's first byte — the
1-byte `CMP` change avoids that entirely.

---

## 3. x64 client DLL repair plan
- Restore pristine x64 `tobii_stream_engine.dll` (installed copy is corrupted).
- Overwrite the first 10 bytes of each of the 4 export entries with
  `41 c7 00 01 00 00 00 31 c0 c3`
  = `mov dword ptr [r8],1 ; xor eax,eax ; ret`.
  - Ghidra: `tobii_stream_supported(longlong *param_1, int param_2, uint *param_3)`
    ⇒ arg3 = r8 = out-pointer. ✔
  - The replaced bytes are shadow-space stores + pushes, **no `sub rsp`** ⇒ the
    original epilogue is never reached, stack stays balanced. Plain `ret` is
    correct for Windows x64 (no callee stack cleanup).
- Same shape as the proven x86 stub, so behaviour matches the working x86 path.

## 4. Repo artifact regeneration
`x86_patched_tobii_stream_engine.dll` must be rebuilt **from pristine** with a
documented script so that repo bytes == deployed bytes (no size change, no
section-table damage).

---

## 5. Outstanding / next actions
- [x] Apply the 1-byte service patch (needs elevated copy + service restart). -> Done 2026-10-25.
- [x] Restore + patch x64 DLL in the app install dir. -> Done 2026-10-27 (`make_patched_dlls.py --install`).
- [x] Regenerate the repo x86 blob from pristine via script. -> Done 2026-10-27 (`make_patched_dlls.py` + `patch_x86_subscribe_gate.py`).
- [ ] Deploy the new service patch (`deploy_service.cmd` / `deploy_service.ps1`) in an elevated terminal.
- [ ] Runtime verification: run `python run_probe_logdiff.py` to confirm `SubscribeToGazePoints` succeeds and gaze frames stream.

---

## 6. Root cause of `PLATMOD_ERROR_NOT_SUPPORTED` and the a55c gate (2026-10-27)

### 6.1 Reverse Engineering Chain
When `ghseq2.exe` calls `SubscribeToGazePoints`, the client connects to the service, receives the device list, and opens `tobii-prp://IS510-100211404854`. However, `subscribe` fails with:
`[W] Failed to subscribe to PRP_STREAM_ENUM_GAZE_POINT with error PLATMOD_ERROR_NOT_SUPPORTED`

1. **`general_stream_subscribe` (0x140273660)**:
   - Evaluates stream descriptor `param_4` filled by `FUN_140277c20` for requested stream 4 (`GAZE_POINT`).
   - Because `param_4[0] == 0`, it searches the context's registered streams table at `param_1 + 0x10e8` (length at `param_1 + 0x14e8`).
   - If stream ID 4 is not found in that table, it exits at VA `0x1402736e9` returning error 3 (`PLATMOD_ERROR_NOT_SUPPORTED`).

2. **Why stream 4 was missing from `0x10e8`**:
   - Stream registration occurs in `stream_type_receiver` (VA `0x140264c90`), in the `id == 1` ladder block.
   - At VA `0x140264cf9` (file offset `0x2640f9`), `cmp dword ptr [rbx + 0xa55c], 1 ; jne 0x140264d49` guards the write of stream 4 into `[rbx + 0x10e8]`.
   - The 5L device does not set `ctx+0xa55c` to 1, so the `jne` jump skips registration.
   - Similarly, at VA `0x140264d49`, `cmp dword ptr [rbx + 0xa560], 1 ; jne 0x140264d99` guards stream `0x1d` (`RESPONSIVE_GAZE_POINT`).

### 6.2 Patches Applied in `platform_runtime_service.exe`
Created `patch_service_a55c_gate.py`:
1. `0x264100` (VA `0x140264d00`): `75 47` -> `90 90` (NOP NOP) — unconditionally registers stream 4 (`GAZE_POINT`) into `[rbx + 0x10e8]`.
2. `0x264150` (VA `0x140264d50`): `75 47` -> `90 90` (NOP NOP) — unconditionally registers stream `0x1d` (`RESPONSIVE_GAZE_POINT`) into `[rbx + 0x10e8]`.
3. `0x272ae7` (VA `0x1402736e7`): `75 40` -> `eb 40` (`jmp short 0x140273729`) — prevents `general_stream_subscribe` from failing with error 3.

Disassembly verified with Capstone. Binary ready to deploy via `deploy_service.cmd` or `deploy_service.ps1`.

