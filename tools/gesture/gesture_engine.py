"""
Embedded inside melonDS via the CPython C API (see GestureController.cpp).

melonDS calls init() once, then poll() repeatedly in a loop on its own
dedicated capture thread (decoupled from NDS emulation speed — see
GestureController::WorkerLoop). There is no window, no screen capture, no
synthetic OS events here — the host C++ side owns the actual window and
feeds our output directly into EmuInstance's key mask and touch-screen
state, and displays the HUD frame we hand back in a small overlay widget.

The wheel/HUD graphics are drawn here (reusing vendor/cockpit.py's exact
drawing code) and baked directly onto the returned frame, so the C++ side
never needs to know how to draw a wheel — it just displays a picture.
"""

import math
import platform
import time

import cv2
import mediapipe as mp

CAMERA_INDEX        = 0
DEAD_ZONE_DEG       = 12
RELEASE_ZONE_DEG    = 6
SOFT_ZONE_DEG       = 25
FLIP_CAMERA         = True
SHOW_ANGLE          = True
MIN_DETECTION_CONF  = 0.7
MIN_TRACKING_CONF   = 0.5
GRACE_FRAMES        = 8
OPEN_FINGER_THRESH  = 3
THUMB_OUT_RATIO     = 1.4

DS_SCREEN_W = 256
DS_SCREEN_H = 192

CLR_WHEEL   = (80, 200, 255)
CLR_LEFT    = (60, 120, 255)
CLR_RIGHT   = (50, 220, 140)
CLR_NEUTRAL = (200, 200, 200)
CLR_TEXT    = (255, 255, 255)
CLR_ACCENT  = (0, 180, 255)
CLR_HAND_L  = (255, 130, 60)
CLR_HAND_R  = (60, 230, 130)
CLR_ACCEL   = (50, 220, 100)
CLR_BRAKE   = (0, 60, 255)
CLR_CURSOR       = (0, 220, 255)
CLR_CURSOR_CLICK = (0, 255, 0)

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

_state = {
    "cap": None,
    "hands": None,
    "held_left": False,
    "held_right": False,
    "lost_frames": 0,
    "pinch_active": False,
    "prev_time": None,
}


def is_open_hand(hand_landmarks):
    FINGER_TIPS = [8, 12, 16, 20]
    FINGER_PIPS = [6, 10, 14, 18]
    extended = sum(
        1 for tip, pip in zip(FINGER_TIPS, FINGER_PIPS)
        if hand_landmarks.landmark[tip].y < hand_landmarks.landmark[pip].y
    )
    return extended >= OPEN_FINGER_THRESH


def is_thumb_out(hand_landmarks):
    # Simple "thumbs out" click gesture: thumb tip far from the wrist
    # relative to the thumb's base knuckle, i.e. the thumb is sticking
    # out away from the fist rather than tucked in.
    wrist     = hand_landmarks.landmark[0]
    thumb_mcp = hand_landmarks.landmark[2]
    thumb_tip = hand_landmarks.landmark[4]
    d_tip = math.hypot(thumb_tip.x - wrist.x, thumb_tip.y - wrist.y)
    d_mcp = math.hypot(thumb_mcp.x - wrist.x, thumb_mcp.y - wrist.y)
    return d_tip > d_mcp * THUMB_OUT_RATIO


def draw_steering_wheel(frame, center, angle_deg, direction, strength):
    h, w = frame.shape[:2]
    radius = int(min(w, h) * 0.18)
    cx, cy = center

    color = CLR_NEUTRAL
    if direction == "LEFT":
        color = CLR_LEFT
    elif direction == "RIGHT":
        color = CLR_RIGHT

    cv2.circle(frame, (cx + 3, cy + 3), radius, (0, 0, 0), 4)
    cv2.circle(frame, (cx, cy), radius, color, 3)

    for sa in [0, 120, 240]:
        rad = math.radians(sa - angle_deg)
        x1 = int(cx + radius * 0.4 * math.cos(rad))
        y1 = int(cy - radius * 0.4 * math.sin(rad))
        x2 = int(cx + radius * 0.95 * math.cos(rad))
        y2 = int(cy - radius * 0.95 * math.sin(rad))
        cv2.line(frame, (x1, y1), (x2, y2), color, 2)

    cv2.circle(frame, (cx, cy), 6, color, -1)

    if direction != "STRAIGHT":
        start_a = -30 if direction == "RIGHT" else 150
        end_a   =  30 if direction == "RIGHT" else 210
        cv2.ellipse(frame, (cx, cy), (radius, radius), 0, start_a, end_a, color, 5)


def draw_hud(frame, angle, direction, strength, throttle_mode, both_hands_visible, left_open, right_open, fps):
    h, w = frame.shape[:2]

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - 95), (w, h), (10, 10, 20), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    font = cv2.FONT_HERSHEY_SIMPLEX
    dir_color = CLR_LEFT if direction == "LEFT" else (CLR_RIGHT if direction == "RIGHT" else CLR_NEUTRAL)
    cv2.putText(frame, direction, (10, h - 60), font, 0.55, dir_color, 2)

    throttle_color = CLR_ACCEL if throttle_mode == "ACCEL" else (CLR_BRAKE if throttle_mode == "BRAKE" else CLR_NEUTRAL)
    cv2.putText(frame, throttle_mode, (10, h - 30), font, 0.5, throttle_color, 2)

    cv2.putText(frame, f"FPS: {fps:.0f}", (w - 80, 20), font, 0.45, CLR_ACCENT, 1)

    status       = "TRACKING" if both_hands_visible else "SHOW HANDS"
    status_color = (60, 220, 60) if both_hands_visible else (0, 80, 255)
    cv2.putText(frame, status, (10, 20), font, 0.45, status_color, 1)

    draw_steering_wheel(frame, (w - 55, h - 55), angle, direction, strength)


def draw_hand_connection(frame, lw, rw):
    lx, ly = lw
    rx, ry = rw
    cv2.line(frame, (lx, ly), (rx, ry), (30, 100, 200), 6)
    cv2.line(frame, (lx, ly), (rx, ry), CLR_ACCENT, 2)
    cv2.circle(frame, (lx, ly), 8, CLR_HAND_L, -1)
    cv2.circle(frame, (rx, ry), 8, CLR_HAND_R, -1)
    mx = (lx + rx) // 2
    my = (ly + ry) // 2
    cv2.circle(frame, (mx, my), 5, CLR_WHEEL, -1)


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
    _state["prev_time"] = time.time()
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

    strength = 0.0
    if direction in ("LEFT", "RIGHT"):
        strength = min(1.0, (abs(angle) - DEAD_ZONE_DEG) / (SOFT_ZONE_DEG - DEAD_ZONE_DEG))

    return angle, direction, strength


def _empty_result():
    return {"direction": "STRAIGHT", "throttle": "NEUTRAL", "item": False, "touching": False,
            "touch_x": 0, "touch_y": 0, "both_visible": False,
            "frame": b"", "frame_w": 0, "frame_h": 0}


def poll():
    """
    Returns a dict:
      direction: "LEFT" | "RIGHT" | "STRAIGHT"
      throttle:  "ACCEL" | "BRAKE" | "NEUTRAL"
      touching:  bool
      touch_x, touch_y: ints in DS screen space (0..255, 0..191), only
                         meaningful when touching is True
      frame: BGR bytes of the webcam frame with the wheel/HUD already
             drawn onto it (for the host-side overlay), plus width/height
    """
    cap = _state["cap"]
    hands = _state["hands"]
    if cap is None or hands is None:
        return _empty_result()

    ret, frame = cap.read()
    if not ret or frame is None:
        return _empty_result()

    if FLIP_CAMERA:
        frame = cv2.flip(frame, 1)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False
    results = hands.process(rgb)
    rgb.flags.writeable = True

    angle = 0.0
    direction = "STRAIGHT"
    strength = 0.0
    throttle = "NEUTRAL"
    touching = False
    touch_x = touch_y = 0
    both_visible = False
    left_open = right_open = False
    item_throw = False

    if results.multi_hand_landmarks and results.multi_handedness:
        landmarks_by_label = {}
        for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
            landmarks_by_label[handedness.classification[0].label] = hand_landmarks
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

        if "Left" in landmarks_by_label and "Right" in landmarks_by_label:
            both_visible = True
            _state["lost_frames"] = 0
            l_wrist = landmarks_by_label["Left"].landmark[0]
            r_wrist = landmarks_by_label["Right"].landmark[0]
            left_open = is_open_hand(landmarks_by_label["Left"])
            right_open = is_open_hand(landmarks_by_label["Right"])

            h, w = frame.shape[:2]
            draw_hand_connection(
                frame,
                (int(l_wrist.x * w), int(l_wrist.y * h)),
                (int(r_wrist.x * w), int(r_wrist.y * h)),
            )
            angle, direction, strength = _steer((l_wrist.x, l_wrist.y), (r_wrist.x, r_wrist.y))
            # Binary, never neutral while both hands are tracked: coasting
            # with no accel/brake feels bad. Both hands open = brake;
            # anything else (both fists, or a mixed in-between pose) =
            # accelerate, since "go" should be the default/easy state.
            throttle = "BRAKE" if (left_open and right_open) else "ACCEL"

            # Throw/use item: stick either thumb out while driving. Separate
            # from the fist/open-palm throttle gesture, so it works
            # together with either accelerating or braking.
            item_throw = is_thumb_out(landmarks_by_label["Left"]) or is_thumb_out(landmarks_by_label["Right"])
        else:
            _state["lost_frames"] += 1

        cursor_label = "Right" if "Right" in landmarks_by_label else (
            "Left" if "Left" in landmarks_by_label else None
        )
        if cursor_label:
            lm = landmarks_by_label[cursor_label]
            index_tip = lm.landmark[8]
            pinching = is_thumb_out(lm)
            _state["pinch_active"] = pinching
            if pinching:
                touching = True
                touch_x = int(max(0, min(1, index_tip.x)) * (DS_SCREEN_W - 1))
                touch_y = int(max(0, min(1, index_tip.y)) * (DS_SCREEN_H - 1))

            cur_h, cur_w = frame.shape[:2]
            cx, cy = int(index_tip.x * cur_w), int(index_tip.y * cur_h)
            cursor_color = CLR_CURSOR_CLICK if pinching else CLR_CURSOR
            cv2.circle(frame, (cx, cy), 12, cursor_color, 2)
            cv2.line(frame, (cx - 16, cy), (cx + 16, cy), cursor_color, 1)
            cv2.line(frame, (cx, cy - 16), (cx, cy + 16), cursor_color, 1)
    else:
        _state["lost_frames"] += 1
        _state["pinch_active"] = False

    if _state["lost_frames"] >= GRACE_FRAMES:
        angle, direction, strength = 0.0, "STRAIGHT", 0.0
        throttle = "NEUTRAL"

    now = time.time()
    prev = _state["prev_time"] or now
    fps = 1.0 / max(now - prev, 1e-6)
    _state["prev_time"] = now

    draw_hud(frame, angle, direction, strength, throttle, both_visible, left_open, right_open, fps)
    if item_throw:
        cv2.putText(frame, "ITEM!", (frame.shape[1] - 90, frame.shape[0] - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    h, w = frame.shape[:2]
    return {
        "direction": direction,
        "throttle": throttle,
        "item": item_throw,
        "touching": touching,
        "touch_x": touch_x,
        "touch_y": touch_y,
        "both_visible": both_visible,
        "frame": frame.tobytes(),
        "frame_w": w,
        "frame_h": h,
    }
