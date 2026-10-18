"""
Embedded inside melonDS via the CPython C API (see PhoneController.cpp).

Each EmuInstance that picks "Phone" at the DS64 Setup dialog gets its own
copy of this module (one per instance, one port per instance) — this is
what makes multi-phone local multiplayer work: every melonDS instance
has its own focus-independent, process-direct phone listener, instead of
one external process trying to guess which OS-focused window to send
synthetic keystrokes to.

melonDS calls init(port) once, then poll() repeatedly in a loop on its
own dedicated thread (see PhoneController::WorkerLoop), same contract as
tools/gesture/gesture_engine.py.
"""

import json
import threading

from websockets.sync.server import serve

STEER_DEADZONE = 0.25

_state = {
    "server": None,
    "thread": None,
    "lock": threading.Lock(),
    "connected": False,
    "latest": {"steer": 0.0, "accel": False, "brake": False, "drift": False, "item": False},
}


def _handler(websocket):
    with _state["lock"]:
        _state["connected"] = True
    try:
        for message in websocket:
            try:
                data = json.loads(message)
            except (ValueError, TypeError):
                continue
            with _state["lock"]:
                _state["latest"] = {
                    "steer": float(data.get("steer", 0.0)),
                    "accel": bool(data.get("accel", False)),
                    "brake": bool(data.get("brake", False)),
                    "drift": bool(data.get("drift", False)),
                    "item": bool(data.get("item", False)),
                }
    finally:
        with _state["lock"]:
            _state["connected"] = False
            _state["latest"] = {"steer": 0.0, "accel": False, "brake": False, "drift": False, "item": False}


def init(port: int) -> bool:
    try:
        server = serve(_handler, "0.0.0.0", port)
    except OSError:
        return False

    _state["server"] = server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _state["thread"] = thread
    return True


def shutdown() -> None:
    server = _state["server"]
    if server is not None:
        server.shutdown()
    _state["server"] = None
    _state["thread"] = None


def poll() -> dict:
    """
    Returns a dict:
      connected: bool — whether a phone is currently attached
      direction: "LEFT" | "RIGHT" | "STRAIGHT"
      throttle:  "ACCEL" | "BRAKE" | "NEUTRAL"
      drift, item: bool
    Same vocabulary as gesture_engine.poll() so the C++ side (and the
    arbitration logic that hands control back on real keyboard/mouse
    input) can treat both input sources identically.
    """
    with _state["lock"]:
        connected = _state["connected"]
        latest = dict(_state["latest"])

    steer = latest["steer"]
    direction = "STRAIGHT"
    if steer <= -STEER_DEADZONE:
        direction = "LEFT"
    elif steer >= STEER_DEADZONE:
        direction = "RIGHT"

    if latest["brake"]:
        throttle = "BRAKE"
    elif latest["accel"]:
        throttle = "ACCEL"
    else:
        throttle = "NEUTRAL"

    return {
        "connected": connected,
        "direction": direction,
        "throttle": throttle,
        "drift": latest["drift"],
        "item": latest["item"],
    }
