"""Test WebSocket connection to TobiiGhost with various paths"""
import websocket

paths = [
    "/",
    "/ws",
    "/api",
    "/gaze",
    "/socket",
    "/connect",
    "/tobii",
    "/eye-tracking",
    "/v1",
    "/v1/gaze",
    "/api/v1",
    "/ghost",
]

for path in paths:
    try:
        url = f"ws://127.0.0.1:7890{path}"
        ws = websocket.create_connection(url, timeout=2)
        print(f"Connected to {url}!")
        ws.send('{"type":"ping"}')
        result = ws.recv()
        print(f"  Response: {result[:200]}")
        ws.close()
    except Exception as e:
        err_str = str(e)
        if "501" in err_str:
            status = "501 Not Implemented"
        elif "404" in err_str:
            status = "404 Not Found"
        elif "timed out" in err_str.lower():
            status = "Timeout"
        else:
            status = err_str[:80]
        print(f"  {url}: {status}")
