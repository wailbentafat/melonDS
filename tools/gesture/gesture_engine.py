"""
Embedded inside melonDS via the CPython C API (see GestureController.cpp).

melonDS calls init() once at startup and poll() once per emulated frame.
There is no window, no screen capture, no synthetic OS events here — the
host C++ side owns the actual window and feeds our output directly into
EmuInstance's key mask and touch-screen state. This module only turns a
webcam frame into: a steering direction, a throttle state, and a touch
cursor position in DS screen coordinates (0..255, 0..191), the same way
vendor/cockpit.py did outside the emulator.
"""

import math
import platform

import cv2
import mediapipe as mp

CAMERA_INDEX        = 0
DEAD_ZONE_DEG       = 12
RELEASE_ZONE_DEG    = 6
SOFT_ZONE_DEG       = 25
FLIP_CAMERA         = True
MIN_DETECTION_CONF  = 0.7
MIN_TRACKING_CONF   = 0.5
GRACE_FRAMES        = 8
OPEN_FINGER_THRESH  = 3
PINCH_THRESH        = 0.055

DS_SCREEN_W = 256
DS_SCREEN_H = 192

mp_hands = mp.solutions.hands

_state = {
    "cap": None,
    "hands": None,
    "held_left": False,
    "held_right": False,
    "lost_frames": 0,
    "pinch_active": False,
}


def is_open_hand(hand_landmarks):
    FINGER_TIPS = [8, 12, 16, 20]
    FINGER_PIPS = [6, 10, 14, 18]
    extended = sum(
        1 for tip, pip in zip(FINGER_TIPS, FINGER_PIPS)
        if hand_landmarks.landmark[tip].y < hand_landmarks.landmark[pip].y
    )
    return extended >= OPEN_FINGER_THRESH


def init():
    backend = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_ANY
    cap = cv2.VideoCapture(CAMERA_INDEX, backend)
    if not cap.isOpened():
        cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        return False

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    _state["cap"] = cap
    _state["hands"] = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        model_complexity=0,
        min_detection_confidence=MIN_DETECTION_CONF,
        min_tracking_confidence=MIN_TRACKING_CONF,
    )
    return True


def shutdown():
    if _state["cap"] is not None:
        _state["cap"].release()
        _state["cap"] = None
    if _state["hands"] is not None:
        _state["hands"].close()
        _state["hands"] = None


def _steer(left_wrist, right_wrist):
    dx = right_wrist[0] - left_wrist[0]
    dy = right_wrist[1] - left_wrist[1]
    angle = math.degrees(math.atan2(dy, dx))

    direction = "STRAIGHT"
    if angle < -DEAD_ZONE_DEG:
        direction = "LEFT"
    elif angle > DEAD_ZONE_DEG:
        direction = "RIGHT"
    elif _state["held_left"] and angle > -RELEASE_ZONE_DEG:
        direction = "STRAIGHT"
    elif _state["held_right"] and angle < RELEASE_ZONE_DEG:
        direction = "STRAIGHT"

    _state["held_left"] = direction == "LEFT"
    _state["held_right"] = direction == "RIGHT"
    return direction


def poll():
    """
    Returns a dict:
      direction: "LEFT" | "RIGHT" | "STRAIGHT"
      throttle:  "ACCEL" | "BRAKE" | "NEUTRAL"
      touching:  bool
      touch_x, touch_y: ints in DS screen space (0..255, 0..191), only
                         meaningful when touching is True
      frame: raw BGR bytes of the webcam frame (for the host-side PiP
             overlay), plus its width/height
    """
    cap = _state["cap"]
    hands = _state["hands"]
    if cap is None or hands is None:
        return {"direction": "STRAIGHT", "throttle": "NEUTRAL", "touching": False,
                "touch_x": 0, "touch_y": 0, "frame": b"", "frame_w": 0, "frame_h": 0}

    ret, frame = cap.read()
    if not ret or frame is None:
        return {"direction": "STRAIGHT", "throttle": "NEUTRAL", "touching": False,
                "touch_x": 0, "touch_y": 0, "frame": b"", "frame_w": 0, "frame_h": 0}

    if FLIP_CAMERA:
        frame = cv2.flip(frame, 1)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False
    results = hands.process(rgb)
    rgb.flags.writeable = True

    direction = "STRAIGHT"
    throttle = "NEUTRAL"
    touching = False
    touch_x = touch_y = 0

    if results.multi_hand_landmarks and results.multi_handedness:
        landmarks_by_label = {}
        for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
            landmarks_by_label[handedness.classification[0].label] = hand_landmarks

        if "Left" in landmarks_by_label and "Right" in landmarks_by_label:
            _state["lost_frames"] = 0
            l_wrist = landmarks_by_label["Left"].landmark[0]
            r_wrist = landmarks_by_label["Right"].landmark[0]
            left_open = is_open_hand(landmarks_by_label["Left"])
            right_open = is_open_hand(landmarks_by_label["Right"])

            direction = _steer((l_wrist.x, l_wrist.y), (r_wrist.x, r_wrist.y))
            if left_open and right_open:
                throttle = "BRAKE"
            elif (not left_open) and (not right_open):
                throttle = "ACCEL"
        else:
            _state["lost_frames"] += 1

        cursor_label = "Right" if "Right" in landmarks_by_label else (
            "Left" if "Left" in landmarks_by_label else None
        )
        if cursor_label:
            lm = landmarks_by_label[cursor_label]
            index_tip = lm.landmark[8]
            thumb_tip = lm.landmark[4]
            pinch_dist = math.hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y)
            pinching = pinch_dist < PINCH_THRESH
            _state["pinch_active"] = pinching
            if pinching:
                touching = True
                touch_x = int(max(0, min(1, index_tip.x)) * (DS_SCREEN_W - 1))
                touch_y = int(max(0, min(1, index_tip.y)) * (DS_SCREEN_H - 1))
    else:
        _state["lost_frames"] += 1
        _state["pinch_active"] = False

    if _state["lost_frames"] >= GRACE_FRAMES:
        direction = "STRAIGHT"
        throttle = "NEUTRAL"

    h, w = frame.shape[:2]
    return {
        "direction": direction,
        "throttle": throttle,
        "touching": touching,
        "touch_x": touch_x,
        "touch_y": touch_y,
        "frame": frame.tobytes(),
        "frame_w": w,
        "frame_h": h,
    }
