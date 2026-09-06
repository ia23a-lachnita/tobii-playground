"""Test WebSocket connection to TobiiGhost.

NOTE (audit 2026-09-06): Tobii Ghost exposes NO documented local WebSocket API
— its overlay is SSOverlay.exe captured via game-capture (OBS) or the Twitch
extension. The ghost.exe/game_hub.exe files in this repo are actually saved
Tobii download web pages (identical SHA-256), not executables, so there is no
local Ghost binary to probe here. These probes are kept as experiments; expect
connection-refused / 501s until a real Ghost install is running.
"""
import websocket
import json
import time

ws = websocket.create_connection("ws://127.0.0.1:7890", timeout=5)
print("Connected to WebSocket!")

messages = [
    "{}",
    '{"type":"get_device_info"}',
    '{"action":"get_device_info"}',
    '{"method":"get_device_info"}',
    '{"command":"get_device_info"}',
    '{"type":"ping"}',
    '{"action":"ping"}',
    '{"type":"subscribe","stream":"gaze"}',
    '{"type":"subscribe","channel":"gaze"}',
    '{"type":"gaze_subscribe"}',
    '{"type":"start"}',
    '{"type":"get_status"}',
    '{"type":"info"}',
]

for msg in messages:
    try:
        ws.send(msg)
        result = ws.recv()
        print(f"Sent: {msg}")
        print(f"Received: {result[:500]}")
        print()
    except Exception as e:
        print(f"Sent: {msg}, Error: {e}")
        break

ws.close()
