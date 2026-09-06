"""Tobii Eye Tracker 5L - Stream Engine Python Interface.

Works with tobii_stream_engine.dll (x64). Defaults to the DLL shipped in this
repo; falls back to the TobiiGhost install path.

All signatures/structs below follow the Stream Engine Client Kit headers
(v1.2.1.305, as transcribed in the `tobii-sys` Rust bindings, docs.rs).
Notable corrections vs. earlier revisions of this file:
  * subscribe = (device, callback, user_data) — 3 args, no leading int.
  * callbacks = (data*, user_data) — 2 args, no leading status int.
  * structs use int64 timestamps and tightly packed validity/position fields.
  * TOBII_VALIDITY_INVALID = 0, TOBII_VALIDITY_VALID = 1 (0 is NOT valid).
  * enumerate is callback-based, not buffer-based.
  * the pump loop is wait_for_callbacks(NULL, 1, &device) +
    device_process_callbacks(device); wait alone never fires callbacks.
"""

import ctypes
from ctypes import (
    c_void_p, c_char_p, c_int, c_uint, c_float, c_int64,
    Structure, POINTER, CFUNCTYPE, byref,
)
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
DLL_PATH = os.environ.get(
    "TOBII_STREAM_ENGINE_DLL",
    os.path.join(_HERE, "tobii_stream_engine.dll"),
)
_FALLBACK_DLL = r"C:\Users\xursc\AppData\Local\TobiiGhost\app-1.14.1\x64\tobii_stream_engine.dll"

# tobii_validity_t: INVALID = 0, VALID = 1
TOBII_VALIDITY_INVALID = 0
TOBII_VALIDITY_VALID = 1
TOBII_ERROR_NO_ERROR = 0


class TobiiGazePoint(Structure):
    # struct { int64 timestamp_us; tobii_validity_t validity; float position_xy[2]; }
    _fields_ = [
        ("timestamp_us", c_int64),
        ("validity", c_uint),
        ("position_x", c_float),
        ("position_y", c_float),
    ]


class TobiiGazeOrigin(Structure):
    # struct { int64 ts; validity left; float left_xyz[3]; validity right; float right_xyz[3]; }
    _fields_ = [
        ("timestamp_us", c_int64),
        ("validity_left", c_uint),
        ("position_left_x", c_float),
        ("position_left_y", c_float),
        ("position_left_z", c_float),
        ("validity_right", c_uint),
        ("position_right_x", c_float),
        ("position_right_y", c_float),
        ("position_right_z", c_float),
    ]


class TobiiEyePositionNormalized(Structure):
    _fields_ = [
        ("timestamp_us", c_int64),
        ("validity_left", c_uint),
        ("position_left_x", c_float),
        ("position_left_y", c_float),
        ("position_left_z", c_float),
        ("validity_right", c_uint),
        ("position_right_x", c_float),
        ("position_right_y", c_float),
        ("position_right_z", c_float),
    ]


class TobiiHeadPose(Structure):
    # struct { int64 ts; validity pos; float pos[3];
    #          validity rot[3]; float rot[3]; }
    _fields_ = [
        ("timestamp_us", c_int64),
        ("position_validity", c_uint),
        ("position_x", c_float),
        ("position_y", c_float),
        ("position_z", c_float),
        ("rotation_validity_x", c_uint),
        ("rotation_validity_y", c_uint),
        ("rotation_validity_z", c_uint),
        ("rotation_x", c_float),
        ("rotation_y", c_float),
        ("rotation_z", c_float),
    ]


# Callback types: (const data*, void* user_data), no status arg.
GAZE_POINT_CALLBACK = CFUNCTYPE(None, POINTER(TobiiGazePoint), c_void_p)
GAZE_ORIGIN_CALLBACK = CFUNCTYPE(None, POINTER(TobiiGazeOrigin), c_void_p)
EYE_POSITION_CALLBACK = CFUNCTYPE(None, POINTER(TobiiEyePositionNormalized), c_void_p)
HEAD_POSE_CALLBACK = CFUNCTYPE(None, POINTER(TobiiHeadPose), c_void_p)
ENUM_CALLBACK = CFUNCTYPE(None, c_char_p, c_void_p)


class TobiiError(RuntimeError):
    pass


class TobiiTracker:
    def __init__(self, dll_path=None):
        path = dll_path or DLL_PATH
        if not os.path.exists(path) and os.path.exists(_FALLBACK_DLL):
            path = _FALLBACK_DLL
        self.dll = ctypes.CDLL(path)
        self.dll_path = path
        self.api = c_void_p()
        self.device = c_void_p()
        self._callbacks = []  # keep CFUNCTYPE refs alive
        self._setup_api()

    def _setup_api(self):
        dll = self.dll

        dll.tobii_api_create.argtypes = [POINTER(c_void_p), c_void_p, c_void_p]
        dll.tobii_api_create.restype = c_int

        dll.tobii_api_destroy.argtypes = [c_void_p]
        dll.tobii_api_destroy.restype = c_int

        dll.tobii_enumerate_local_device_urls.argtypes = [c_void_p, ENUM_CALLBACK, c_void_p]
        dll.tobii_enumerate_local_device_urls.restype = c_int

        dll.tobii_device_create.argtypes = [c_void_p, c_char_p, POINTER(c_void_p)]
        dll.tobii_device_create.restype = c_int

        dll.tobii_device_destroy.argtypes = [c_void_p]
        dll.tobii_device_destroy.restype = c_int

        dll.tobii_gaze_point_subscribe.argtypes = [c_void_p, GAZE_POINT_CALLBACK, c_void_p]
        dll.tobii_gaze_point_subscribe.restype = c_int

        dll.tobii_gaze_point_unsubscribe.argtypes = [c_void_p]
        dll.tobii_gaze_point_unsubscribe.restype = c_int

        dll.tobii_gaze_origin_subscribe.argtypes = [c_void_p, GAZE_ORIGIN_CALLBACK, c_void_p]
        dll.tobii_gaze_origin_subscribe.restype = c_int

        dll.tobii_gaze_origin_unsubscribe.argtypes = [c_void_p]
        dll.tobii_gaze_origin_unsubscribe.restype = c_int

        dll.tobii_eye_position_normalized_subscribe.argtypes = [c_void_p, EYE_POSITION_CALLBACK, c_void_p]
        dll.tobii_eye_position_normalized_subscribe.restype = c_int

        dll.tobii_eye_position_normalized_unsubscribe.argtypes = [c_void_p]
        dll.tobii_eye_position_normalized_unsubscribe.restype = c_int

        dll.tobii_head_pose_subscribe.argtypes = [c_void_p, HEAD_POSE_CALLBACK, c_void_p]
        dll.tobii_head_pose_subscribe.restype = c_int

        dll.tobii_head_pose_unsubscribe.argtypes = [c_void_p]
        dll.tobii_head_pose_unsubscribe.restype = c_int

        dll.tobii_wait_for_callbacks.argtypes = [c_void_p, c_int, POINTER(c_void_p)]
        dll.tobii_wait_for_callbacks.restype = c_int

        dll.tobii_device_process_callbacks.argtypes = [c_void_p]
        dll.tobii_device_process_callbacks.restype = c_int

        dll.tobii_error_message.argtypes = [c_int]
        dll.tobii_error_message.restype = c_char_p

    def _check(self, result, what):
        if result != TOBII_ERROR_NO_ERROR:
            msg = self.dll.tobii_error_message(result)
            raise TobiiError(
                f"{what} failed: {result} ({msg.decode(errors='replace') if msg else '?'})"
            )
        return result

    def create(self):
        self._check(self.dll.tobii_api_create(byref(self.api), None, None), "tobii_api_create")
        print(f"API created via {self.dll_path}")

    def enumerate_devices(self):
        urls = []

        @ENUM_CALLBACK
        def _receiver(url, user_data):
            if url:
                urls.append(url.decode("utf-8", errors="replace"))

        self._callbacks.append(_receiver)  # keep alive during the call
        self._check(
            self.dll.tobii_enumerate_local_device_urls(self.api, _receiver, None),
            "tobii_enumerate_local_device_urls",
        )
        for u in urls:
            print(f"  Found device: {u}")
        return urls

    def create_device(self, url):
        url_bytes = url.encode() if isinstance(url, str) else url
        self._check(
            self.dll.tobii_device_create(self.api, url_bytes, byref(self.device)),
            f"tobii_device_create ({url})",
        )
        print(f"Device created: {url}")

    def _subscribe(self, fn, ctype, callback):
        cb = ctype(callback)
        self._callbacks.append(cb)  # must stay alive while subscribed
        self._check(fn(self.device, cb, None), fn.__name__ if hasattr(fn, "__name__") else "subscribe")
        return cb

    def subscribe_gaze_point(self, callback):
        return self._subscribe(self.dll.tobii_gaze_point_subscribe, GAZE_POINT_CALLBACK, callback)

    def subscribe_gaze_origin(self, callback):
        return self._subscribe(self.dll.tobii_gaze_origin_subscribe, GAZE_ORIGIN_CALLBACK, callback)

    def subscribe_eye_position(self, callback):
        return self._subscribe(
            self.dll.tobii_eye_position_normalized_subscribe, EYE_POSITION_CALLBACK, callback
        )

    def subscribe_head_pose(self, callback):
        return self._subscribe(self.dll.tobii_head_pose_subscribe, HEAD_POSE_CALLBACK, callback)

    def pump(self):
        """Wait for new data and dispatch callbacks. Call in a loop."""
        self._check(
            self.dll.tobii_wait_for_callbacks(None, 1, byref(self.device)),
            "tobii_wait_for_callbacks",
        )
        self._check(
            self.dll.tobii_device_process_callbacks(self.device),
            "tobii_device_process_callbacks",
        )

    def unsubscribe_all(self):
        for fn in (
            self.dll.tobii_gaze_point_unsubscribe,
            self.dll.tobii_gaze_origin_unsubscribe,
            self.dll.tobii_eye_position_normalized_unsubscribe,
            self.dll.tobii_head_pose_unsubscribe,
        ):
            try:
                fn(self.device)
            except Exception:
                pass

    def destroy(self):
        self.unsubscribe_all()
        try:
            if self.device:
                self.dll.tobii_device_destroy(self.device)
        finally:
            if self.api:
                self.dll.tobii_api_destroy(self.api)
        self.device = c_void_p()
        self.api = c_void_p()
        self._callbacks.clear()


def main():
    print("Tobii Eye Tracker 5L - Stream Engine")
    print("=" * 50)

    tracker = TobiiTracker()

    try:
        tracker.create()
    except TobiiError as e:
        print(e)
        return

    print("\nEnumerating devices...")
    try:
        urls = tracker.enumerate_devices()
    except TobiiError as e:
        print(e)
        tracker.destroy()
        return

    if not urls:
        print("No devices found!")
        print("Make sure the Platform Runtime service is installed and running.")
        print("Run setup_tobii_admin.bat as Administrator.")
        tracker.destroy()
        return

    url = urls[0]
    print(f"\nConnecting to: {url}")
    try:
        tracker.create_device(url)
    except TobiiError as e:
        print(e)
        tracker.destroy()
        return

    # Subscribe to streams
    print("\nSubscribing to data streams...")

    gaze_count = [0]

    def on_gaze_point(data, user_data):
        gaze_count[0] += 1
        if data.contents.validity == TOBII_VALIDITY_VALID:
            print(f"  Gaze: x={data.contents.position_x:.4f} y={data.contents.position_y:.4f} "
                  f"t={data.contents.timestamp_us / 1e6:.3f}s")

    def on_gaze_origin(data, user_data):
        if data.contents.validity_left == TOBII_VALIDITY_VALID:
            print(f"  Left eye origin:  ({data.contents.position_left_x:.1f}, "
                  f"{data.contents.position_left_y:.1f}, {data.contents.position_left_z:.1f})")
        if data.contents.validity_right == TOBII_VALIDITY_VALID:
            print(f"  Right eye origin: ({data.contents.position_right_x:.1f}, "
                  f"{data.contents.position_right_y:.1f}, {data.contents.position_right_z:.1f})")

    def on_head_pose(data, user_data):
        if data.contents.position_validity == TOBII_VALIDITY_VALID:
            print(f"  Head: pos=({data.contents.position_x:.1f}, {data.contents.position_y:.1f}, "
                  f"{data.contents.position_z:.1f}) rot=({data.contents.rotation_x:.1f}, "
                  f"{data.contents.rotation_y:.1f}, {data.contents.rotation_z:.1f})")

    try:
        tracker.subscribe_gaze_point(on_gaze_point)
        print("  Gaze point subscribed")
        tracker.subscribe_gaze_origin(on_gaze_origin)
        print("  Gaze origin subscribed")
        tracker.subscribe_head_pose(on_head_pose)
        print("  Head pose subscribed")
    except TobiiError as e:
        print(e)
        tracker.destroy()
        return

    # Pump loop
    print("\nReading eye tracking data (Ctrl+C to stop)...")
    print("-" * 50)

    frame_count = 0
    try:
        while True:
            tracker.pump()
            frame_count += 1
            if frame_count % 100 == 0:
                print(f"  [Pump {frame_count}, {gaze_count[0]} gaze points received]")
    except KeyboardInterrupt:
        print(f"\n\nStopped. Total pumps: {frame_count}, gaze points: {gaze_count[0]}")
    except TobiiError as e:
        print(f"\nStream error: {e}")
    finally:
        tracker.destroy()


if __name__ == "__main__":
    main()
