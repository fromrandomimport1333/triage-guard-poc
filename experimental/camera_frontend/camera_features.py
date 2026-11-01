"""Camera front end: facial-geometry cues and temporal warning rules.

The rules engine behind ``driver_monitoring_prototype.py``. It implements the
formulas and default settings of the team's webcam prototype (the
file as received is kept in ``docs/camera_prototype_received_2026-11-01/``) and
adds explicit validity handling around them. Every added behaviour is marked
``ADDED`` in the docstrings; everything else follows the prototype.

The module has no OpenCV or dlib dependency. It consumes per-frame
observations (face box, eye landmarks, nose x-coordinate) with explicit
timestamps, so every timer and counter can be tested with synthetic sequences.
The capture loop lives in ``driver_monitoring_prototype.py``.

What these cues are: image-plane proxies for eye openness, face position and
face presence. They are not measurements of consciousness, head pose or any
medical state, and nothing here may authorize a vehicle request on its own
(TRIAGE-GUARD invariant I1).
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, Sequence, Tuple

Point = Tuple[float, float]
Box = Tuple[float, float, float, float]  # x, y, w, h

# Defaults exactly as in the received prototype (and its research draft).
EAR_THRESHOLD = 0.25
EYE_CLOSED_SECONDS = 1.5
FACE_LOST_SECONDS = 1.5
DISPLACEMENT_THRESHOLD = 0.45
DISPLACEMENT_SECONDS = 1.0
MOTION_THRESHOLD = 0.045
MOTION_HISTORY_SECONDS = 1.5
MOTION_CHANGES = 5
BEEP_INTERVAL_SECONDS = 2.0
EPS = 1e-6

# ADDED: tolerance for short gaps in valid eye measurements before the
# closure timer is abandoned. The prototype has no such value; with 0 the timer
# resets on the first invalid frame.
EYE_GAP_TOLERANCE_SECONDS = 0.3


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Measurement:
    """A scalar with an explicit validity flag.

    ADDED. The prototype returns 0 when the eye's horizontal distance is almost
    zero. A 0 is below every plausible EAR threshold, so a failed computation
    would read as a closed eye. Here a failed computation is ``valid=False``
    with a reason, and consumers must treat it as unknown.
    """
    value: Optional[float]
    valid: bool
    reason: str = ""

    @staticmethod
    def invalid(reason: str) -> "Measurement":
        return Measurement(None, False, reason)


def _finite_point(p: Point) -> bool:
    return (len(p) == 2 and all(isinstance(c, (int, float)) for c in p)
            and all(math.isfinite(c) for c in p))


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def eye_aspect_ratio_draft(eye: Sequence[Point]) -> float:
    """EAR exactly as the received prototype computes it, including its ``return 0``.

    EAR = (|p2 - p6| + |p3 - p5|) / (2 |p1 - p4|), points ordered p1..p6 as
    in the dlib 68-landmark layout (outer corner, two upper lid points, inner
    corner, two lower lid points). Kept for reference and for the test that
    shows why the zero return is unsafe. Do not use it in the monitor.
    """
    a = _dist(eye[1], eye[5])
    b = _dist(eye[2], eye[4])
    c = _dist(eye[0], eye[3])
    if c <= EPS:
        return 0.0
    return (a + b) / (2.0 * c)


def eye_aspect_ratio(eye: Optional[Sequence[Point]]) -> Measurement:
    """Same formula as ``eye_aspect_ratio_draft`` with validity handling.

    ADDED checks: six points, finite coordinates, horizontal distance above
    ``EPS``. Any failure yields an invalid measurement instead of 0.
    """
    if eye is None or len(eye) != 6:
        return Measurement.invalid("missing_landmarks")
    if not all(_finite_point(p) for p in eye):
        return Measurement.invalid("non_finite_landmark")
    c = _dist(eye[0], eye[3])
    if c <= EPS:
        return Measurement.invalid("degenerate_horizontal")
    a = _dist(eye[1], eye[5])
    b = _dist(eye[2], eye[4])
    return Measurement((a + b) / (2.0 * c), True)


def averaged_ear(left: Optional[Sequence[Point]],
                 right: Optional[Sequence[Point]]) -> Measurement:
    """Mean of both eyes as in the prototype; invalid if either eye is invalid."""
    l, r = eye_aspect_ratio(left), eye_aspect_ratio(right)
    if not l.valid:
        return l
    if not r.valid:
        return r
    return Measurement((l.value + r.value) / 2.0, True)


def face_center_and_width(box: Box) -> Tuple[float, float, float]:
    x, y, w, h = box
    return x + w / 2.0, y + h / 2.0, w


def normalized_displacement(box: Box, ref: Tuple[float, float, float]) -> float:
    """D = sqrt((x - x0)^2 + (y - y0)^2) / max(w0, 1), as in the prototype."""
    cx, cy, _ = face_center_and_width(box)
    x0, y0, w0 = ref
    return math.hypot(cx - x0, cy - y0) / max(w0, 1.0)


def valid_box(box: Optional[Box]) -> bool:
    return (box is not None and len(box) == 4
            and all(isinstance(c, (int, float)) and math.isfinite(c) for c in box)
            and box[2] > 0 and box[3] > 0)


# --------------------------------------------------------------------------
# Temporal rules
# --------------------------------------------------------------------------

class EyeClosureMonitor:
    """Prolonged eye-closure rule.

    Prototype: the timer starts on the first frame with EAR < threshold (strict,
    so EAR equal to the threshold counts as open), keeps running while
    detected-face frames stay below it, and resets when EAR rises to or above
    the threshold. ``T_closed = t_current - t_start``; the warning is raised
    when ``T_closed >= eye_closed_seconds``.

    ADDED: invalid measurements never advance the timer. Closed time is
    counted only up to the last valid below-threshold frame. If no valid
    frame arrives for more than ``gap_tolerance`` seconds the timer is
    abandoned and the state is UNKNOWN, so a lost face is never read as
    continuous closure.
    """
    OPEN, CLOSING, PROLONGED, UNKNOWN = "OPEN", "CLOSING", "PROLONGED_CLOSURE", "UNKNOWN"

    def __init__(self, threshold: float = EAR_THRESHOLD,
                 eye_closed_seconds: float = EYE_CLOSED_SECONDS,
                 gap_tolerance: float = EYE_GAP_TOLERANCE_SECONDS) -> None:
        self.threshold = threshold
        self.eye_closed_seconds = eye_closed_seconds
        self.gap_tolerance = gap_tolerance
        self.reset()

    def reset(self) -> None:
        self._start: Optional[float] = None
        self._last_valid_below: Optional[float] = None
        self.state = self.UNKNOWN
        self.closed_seconds = 0.0

    def update(self, ear: Measurement, t: float) -> str:
        if not ear.valid:
            if self._start is not None and self._last_valid_below is not None \
                    and t - self._last_valid_below > self.gap_tolerance:
                self._start = None
                self._last_valid_below = None
                self.closed_seconds = 0.0
            self.state = self.UNKNOWN
            return self.state
        if ear.value < self.threshold:
            if self._start is None:
                self._start = t
            self._last_valid_below = t
            self.closed_seconds = t - self._start
            self.state = self.PROLONGED if self.closed_seconds >= self.eye_closed_seconds else self.CLOSING
        else:
            self._start = None
            self._last_valid_below = None
            self.closed_seconds = 0.0
            self.state = self.OPEN
        return self.state


class FaceAbsenceMonitor:
    """Face-absence rule.

    Prototype: when the detector returns no face a missing-face timer starts;
    ``T_missing >= face_lost_seconds`` gives FACE OUT OF VIEW, and before that
    FACE TEMPORARILY LOST is shown if a face had previously been detected.

    ADDED: ``camera_ok=False`` (no frame delivered) is CAMERA_FAILURE, which
    resets the absence timer and is never counted as absence. Before the first
    detection the state is NO_FACE_YET; the timer still runs, so a driver who
    never appears raises OUT_OF_VIEW after the same delay.
    """
    NO_FACE_YET, PRESENT, LOST, OUT, CAMERA = (
        "NO_FACE_YET", "PRESENT", "TEMPORARILY_LOST", "OUT_OF_VIEW", "CAMERA_FAILURE")

    def __init__(self, face_lost_seconds: float = FACE_LOST_SECONDS) -> None:
        self.face_lost_seconds = face_lost_seconds
        self.reset()

    def reset(self) -> None:
        self._missing_since: Optional[float] = None
        self._ever_seen = False
        self.state = self.NO_FACE_YET
        self.missing_seconds = 0.0

    def update(self, face_present: bool, t: float, camera_ok: bool = True) -> str:
        if not camera_ok:
            self._missing_since = None
            self.missing_seconds = 0.0
            self.state = self.CAMERA
            return self.state
        if face_present:
            self._ever_seen = True
            self._missing_since = None
            self.missing_seconds = 0.0
            self.state = self.PRESENT
            return self.state
        if self._missing_since is None:
            self._missing_since = t
        self.missing_seconds = t - self._missing_since
        if self.missing_seconds >= self.face_lost_seconds:
            self.state = self.OUT
        else:
            self.state = self.LOST if self._ever_seen else self.NO_FACE_YET
        return self.state


class DisplacementMonitor:
    """Face-centre displacement relative to the first detected face.

    Prototype: the reference (x0, y0, w0) is stored at the first detection and
    not updated. ``D > displacement_threshold`` starts a timer; after
    ``displacement_seconds`` the position-change detail is raised.

    ADDED: an invalid or missing box gives UNKNOWN and pauses the timer;
    ``reset_reference()`` lets the caller re-anchor after a tracking
    discontinuity. The reference is still never updated automatically, so
    ordinary repositioning can trigger this cue, as the prototype's own comment notes.
    """
    STABLE, SHIFTED, CHANGED, UNKNOWN = "STABLE", "SHIFTED", "POSITION_CHANGED", "UNKNOWN"

    def __init__(self, threshold: float = DISPLACEMENT_THRESHOLD,
                 displacement_seconds: float = DISPLACEMENT_SECONDS) -> None:
        self.threshold = threshold
        self.displacement_seconds = displacement_seconds
        self.reset_reference()

    def reset_reference(self) -> None:
        self.reference: Optional[Tuple[float, float, float]] = None
        self._since: Optional[float] = None
        self.state = self.UNKNOWN
        self.displacement = Measurement.invalid("no_face")

    def update(self, box: Optional[Box], t: float) -> str:
        if not valid_box(box):
            self.displacement = Measurement.invalid("no_face" if box is None else "invalid_box")
            self.state = self.UNKNOWN
            return self.state
        if self.reference is None:
            self.reference = face_center_and_width(box)
        d = normalized_displacement(box, self.reference)
        self.displacement = Measurement(d, True)
        if d > self.threshold:
            if self._since is None:
                self._since = t
            self.state = self.CHANGED if t - self._since >= self.displacement_seconds else self.SHIFTED
        else:
            self._since = None
            self.state = self.STABLE
        return self.state


@dataclass
class _CountSample:
    t: float
    count: int


class RapidMotionMonitor:
    """Rapid horizontal head-motion heuristic (nose landmark 30).

    Prototype: ``dx_norm = (x_now - x_prev) / max(scale, 1)``; rightward if
    ``dx_norm > motion_threshold``, leftward if ``< -motion_threshold``, else
    neutral. A direction change is counted when a non-neutral direction
    differs from the previous non-neutral direction; neutral frames do not
    reset the remembered direction. Timestamped counter values are kept in a
    deque and entries older than ``history_seconds`` are dropped. The alert
    fires when ``count_now - count_oldest_retained >= motion_changes``.

    ADDED: a frame without a nose position (face lost or invalid) clears the
    previous position and the history, so reacquisition never produces an
    artificial jump and stale counts cannot fire later. The sample for the
    current frame is appended after pruning, so the window always holds at
    least one entry and the difference counts changes strictly inside the
    window. This is a motion-pattern heuristic with no clinical meaning; it
    is excluded from the medical hypothesis by design.
    """
    QUIET, RAPID, UNKNOWN = "QUIET", "RAPID_MOTION", "UNKNOWN"

    def __init__(self, motion_threshold: float = MOTION_THRESHOLD,
                 history_seconds: float = MOTION_HISTORY_SECONDS,
                 motion_changes: int = MOTION_CHANGES) -> None:
        self.motion_threshold = motion_threshold
        self.history_seconds = history_seconds
        self.motion_changes = motion_changes
        self.reset()

    def reset(self) -> None:
        self._prev_x: Optional[float] = None
        self._last_dir = 0
        self.count = 0
        self._history: Deque[_CountSample] = deque()
        self.state = self.UNKNOWN
        self.changes_in_window = 0

    def update(self, nose_x: Optional[float], scale: Optional[float], t: float) -> str:
        if nose_x is None or scale is None or not math.isfinite(nose_x) or not math.isfinite(scale):
            self.reset()
            return self.state
        if self._prev_x is not None:
            dx = (nose_x - self._prev_x) / max(scale, 1.0)
            direction = 1 if dx > self.motion_threshold else (-1 if dx < -self.motion_threshold else 0)
            if direction != 0:
                if self._last_dir != 0 and direction != self._last_dir:
                    self.count += 1
                self._last_dir = direction
        self._prev_x = nose_x
        while self._history and self._history[0].t < t - self.history_seconds:
            self._history.popleft()
        self._history.append(_CountSample(t, self.count))
        self.changes_in_window = self.count - self._history[0].count
        self.state = self.RAPID if self.changes_in_window >= self.motion_changes else self.QUIET
        return self.state


class AlertRateLimiter:
    """Global audible-alert rate limit: at most one beep per interval."""

    def __init__(self, interval: float = BEEP_INTERVAL_SECONDS) -> None:
        self.interval = interval
        self._last: Optional[float] = None

    def should_beep(self, alerts_active: bool, t: float) -> bool:
        if not alerts_active:
            return False
        if self._last is None or t - self._last >= self.interval:
            self._last = t
            return True
        return False


# --------------------------------------------------------------------------
# Front end
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FrameObservation:
    """What one frame yields after detection and landmark extraction."""
    camera_ok: bool = True
    face_box: Optional[Box] = None
    left_eye: Optional[Sequence[Point]] = None
    right_eye: Optional[Sequence[Point]] = None
    nose_x: Optional[float] = None


@dataclass
class FrontEndOutput:
    status: str
    alerts: Tuple[str, ...]
    details: Tuple[str, ...]
    beep: bool
    sensing: str                     # "valid", "degraded" or "unavailable"
    ear: Measurement
    displacement: Measurement
    states: dict = field(default_factory=dict)


# Status strings and their order follow the original prototype
# (docs/camera_prototype_received_2026-11-01/): eye closure outranks rapid motion,
# which outranks a position change; the two added states are CAMERA UNAVAILABLE
# and the explicit SEARCHING FOR FACE before the first detection.
_PRIORITY = ("FACE OUT OF VIEW - CHECK DRIVER", "PROLONGED EYE CLOSURE",
             "UNUSUAL RAPID MOVEMENT", "LARGE HEAD/POSITION CHANGE",
             "FACE TEMPORARILY LOST", "CAMERA UNAVAILABLE", "SEARCHING FOR FACE",
             "FACE VISIBLE - MONITORING")


class CameraFrontEnd:
    """Combines the four rules and the beep limiter for one camera stream."""

    def __init__(self, ear_threshold: float = EAR_THRESHOLD,
                 eye_closed_seconds: float = EYE_CLOSED_SECONDS,
                 face_lost_seconds: float = FACE_LOST_SECONDS) -> None:
        self.eyes = EyeClosureMonitor(ear_threshold, eye_closed_seconds)
        self.face = FaceAbsenceMonitor(face_lost_seconds)
        self.position = DisplacementMonitor()
        self.motion = RapidMotionMonitor()
        self.beeper = AlertRateLimiter()

    def update(self, obs: FrameObservation, t: float) -> FrontEndOutput:
        face_present = obs.camera_ok and valid_box(obs.face_box)
        face_state = self.face.update(face_present, t, obs.camera_ok)
        ear = averaged_ear(obs.left_eye, obs.right_eye) if face_present else Measurement.invalid("no_face")
        eye_state = self.eyes.update(ear, t)
        pos_state = self.position.update(obs.face_box if face_present else None, t)
        scale = self.position.reference[2] if self.position.reference else None
        motion_state = self.motion.update(obs.nose_x if face_present else None, scale, t)

        alerts, details, candidates = [], [], []
        if face_state == FaceAbsenceMonitor.OUT:
            alerts.append("FACE OUT OF FRAME")
            candidates.append("FACE OUT OF VIEW - CHECK DRIVER")
        elif face_state == FaceAbsenceMonitor.LOST:
            candidates.append("FACE TEMPORARILY LOST")
        elif face_state == FaceAbsenceMonitor.CAMERA:
            candidates.append("CAMERA UNAVAILABLE")
        elif face_state == FaceAbsenceMonitor.NO_FACE_YET:
            candidates.append("SEARCHING FOR FACE")
        if eye_state == EyeClosureMonitor.PROLONGED:
            alerts.append("EYES CLOSED")
            candidates.append("PROLONGED EYE CLOSURE")
        if pos_state == DisplacementMonitor.CHANGED:
            details.append("Face position changed substantially")
            candidates.append("LARGE HEAD/POSITION CHANGE")
        if motion_state == RapidMotionMonitor.RAPID:
            details.append("RAPID HEAD MOVEMENT")
            candidates.append("UNUSUAL RAPID MOVEMENT")
        if not ear.valid and face_present:
            details.append(f"Eye geometry invalid ({ear.reason})")
        status = next((s for s in _PRIORITY if s in candidates), "FACE VISIBLE - MONITORING")

        if not obs.camera_ok:
            sensing = "unavailable"
        elif face_present and ear.valid:
            sensing = "valid"
        else:
            sensing = "degraded"

        return FrontEndOutput(
            status=status, alerts=tuple(alerts), details=tuple(details),
            beep=self.beeper.should_beep(bool(alerts), t), sensing=sensing,
            ear=ear, displacement=self.position.displacement,
            states={"face": face_state, "eyes": eye_state,
                    "position": pos_state, "motion": motion_state})


def to_policy_observation(out: FrontEndOutput) -> dict:
    """Map a front-end output to qualified observations for the supervisor.

    ADDED. The policy layer (``src/triage_guard_cr01.py``) consumes per-source
    signals with a quality value; this helper shows the intended mapping and
    is deliberately conservative:

    * ``eye_closure`` and ``face_absence`` are capacity cues, never medical
      evidence; they can corroborate an unanswered HMI prompt and nothing else.
    * ``rapid_motion`` is experimental and is reported only as a flag; it does
      not feed the motor expert's seizure score.
    * when sensing is degraded or unavailable every cue is reported as
      unavailable, which the policy treats as unknown, never as normal.
    """
    valid = out.sensing == "valid"
    return {
        "camera_available": out.sensing != "unavailable",
        "camera_quality": 1.0 if valid else 0.0,
        "eye_closure": out.states["eyes"] == EyeClosureMonitor.PROLONGED if valid else None,
        "face_absence": out.states["face"] == FaceAbsenceMonitor.OUT if out.sensing != "unavailable" else None,
        "position_changed": out.states["position"] == DisplacementMonitor.CHANGED if valid else None,
        "rapid_motion_experimental": out.states["motion"] == RapidMotionMonitor.RAPID if valid else None,
    }
