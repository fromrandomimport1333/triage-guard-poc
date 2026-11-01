"""Synthetic tests for the experimental camera front end.

These verify formula and state-machine behaviour on constructed sequences.
They say nothing about detection performance on real faces.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "experimental", "camera_frontend"))

from camera_features import (  # noqa: E402
    AlertRateLimiter, CameraFrontEnd, DisplacementMonitor, EyeClosureMonitor,
    FaceAbsenceMonitor, FrameObservation, Measurement, RapidMotionMonitor,
    averaged_ear, eye_aspect_ratio, eye_aspect_ratio_draft, normalized_displacement,
    to_policy_observation, EAR_THRESHOLD, EYE_CLOSED_SECONDS, FACE_LOST_SECONDS,
    DISPLACEMENT_THRESHOLD, DISPLACEMENT_SECONDS, MOTION_THRESHOLD,
    MOTION_HISTORY_SECONDS, MOTION_CHANGES, BEEP_INTERVAL_SECONDS)


# ---------------------------------------------------------------- geometry

def eye(open_height: float, width: float = 10.0):
    """Six eye points p1..p6 in dlib order for a given lid opening."""
    h = open_height / 2.0
    return [(0.0, 0.0), (3.0, -h), (7.0, -h), (width, 0.0), (7.0, h), (3.0, h)]


def test_draft_defaults_are_the_ones_in_the_document():
    assert (EAR_THRESHOLD, EYE_CLOSED_SECONDS, FACE_LOST_SECONDS) == (0.25, 1.5, 1.5)
    assert (DISPLACEMENT_THRESHOLD, DISPLACEMENT_SECONDS) == (0.45, 1.0)
    assert (MOTION_THRESHOLD, MOTION_HISTORY_SECONDS, MOTION_CHANGES) == (0.045, 1.5, 5)
    assert BEEP_INTERVAL_SECONDS == 2.0


def test_ear_formula_matches_hand_computation():
    e = eye(4.0)  # vertical distances 4 and 4, horizontal 10
    m = eye_aspect_ratio(e)
    assert m.valid and math.isclose(m.value, (4 + 4) / (2 * 10))
    assert math.isclose(eye_aspect_ratio_draft(e), m.value)


def test_open_eye_scores_above_threshold_and_closed_below():
    assert eye_aspect_ratio(eye(6.0)).value > EAR_THRESHOLD
    assert eye_aspect_ratio(eye(1.0)).value < EAR_THRESHOLD


def test_left_right_average():
    m = averaged_ear(eye(6.0), eye(2.0))
    assert m.valid and math.isclose(m.value, (0.6 + 0.2) / 2)


def test_zero_horizontal_distance_is_invalid_not_closed():
    degenerate = eye(4.0, width=0.0)
    assert eye_aspect_ratio_draft(degenerate) == 0.0          # the draft's behaviour
    m = eye_aspect_ratio(degenerate)                           # the added handling
    assert not m.valid and m.reason == "degenerate_horizontal"
    mon = EyeClosureMonitor()
    assert mon.update(m, 0.0) == EyeClosureMonitor.UNKNOWN
    assert mon.update(m, 5.0) == EyeClosureMonitor.UNKNOWN   # never becomes a closure


@pytest.mark.parametrize("bad", [None, eye(4.0)[:5], [(0.0, float("nan"))] + eye(4.0)[1:],
                                 [(float("inf"), 0.0)] + eye(4.0)[1:]])
def test_missing_or_non_finite_landmarks_are_invalid(bad):
    assert not eye_aspect_ratio(bad).valid


def test_one_invalid_eye_invalidates_the_average():
    assert not averaged_ear(eye(4.0), None).valid


# ------------------------------------------------------------ eye closure

CLOSED = Measurement(0.10, True)
OPEN = Measurement(0.30, True)
AT_THRESHOLD = Measurement(EAR_THRESHOLD, True)
BAD = Measurement.invalid("missing_landmarks")


def run_eyes(seq, mon=None):
    mon = mon or EyeClosureMonitor()
    return [mon.update(m, t) for t, m in seq]


def test_closure_shorter_than_duration_is_only_closing():
    states = run_eyes([(t / 10, CLOSED) for t in range(0, 14)])   # 0.0 .. 1.3 s
    assert states[-1] == EyeClosureMonitor.CLOSING
    assert EyeClosureMonitor.PROLONGED not in states


def test_closure_exactly_at_duration_fires():
    states = run_eyes([(0.0, CLOSED), (1.5, CLOSED)])
    assert states == [EyeClosureMonitor.CLOSING, EyeClosureMonitor.PROLONGED]


def test_closure_longer_than_duration_stays_prolonged():
    states = run_eyes([(0.0, CLOSED), (1.6, CLOSED), (4.0, CLOSED)])
    assert states[1:] == [EyeClosureMonitor.PROLONGED] * 2


def test_equality_at_threshold_counts_as_open():
    states = run_eyes([(0.0, AT_THRESHOLD), (2.0, AT_THRESHOLD)])
    assert states == [EyeClosureMonitor.OPEN] * 2


def test_reopening_resets_timer():
    states = run_eyes([(0.0, CLOSED), (1.0, CLOSED), (1.1, OPEN), (1.2, CLOSED), (2.5, CLOSED)])
    assert states[-1] == EyeClosureMonitor.CLOSING      # 1.3 s since the restart at 1.2
    assert states[2] == EyeClosureMonitor.OPEN


def test_short_missed_frames_do_not_count_as_closed_time():
    mon = EyeClosureMonitor()
    run_eyes([(0.0, CLOSED), (1.0, CLOSED), (1.1, BAD), (1.2, BAD)], mon)
    assert mon.state == EyeClosureMonitor.UNKNOWN
    assert mon.update(CLOSED, 1.3) == EyeClosureMonitor.CLOSING    # timer kept, 1.3 s so far
    assert mon.update(CLOSED, 1.5) == EyeClosureMonitor.PROLONGED


def test_long_tracking_loss_abandons_timer():
    mon = EyeClosureMonitor()
    run_eyes([(0.0, CLOSED), (1.0, CLOSED), (1.1, BAD), (2.0, BAD)], mon)
    assert mon.state == EyeClosureMonitor.UNKNOWN
    assert mon.update(CLOSED, 2.1) == EyeClosureMonitor.CLOSING
    assert mon.closed_seconds == pytest.approx(0.0)          # restarted, not 2.1 s


def test_missing_face_never_becomes_closure():
    states = run_eyes([(0.0, CLOSED), (1.0, BAD), (2.0, BAD), (3.0, BAD), (4.0, BAD)])
    assert EyeClosureMonitor.PROLONGED not in states


# ----------------------------------------------------------- face absence

def run_face(seq, mon=None):
    mon = mon or FaceAbsenceMonitor()
    return [mon.update(*args) for args in seq]


def test_no_face_before_first_acquisition():
    states = run_face([(False, 0.0), (False, 1.0)])
    assert states == [FaceAbsenceMonitor.NO_FACE_YET] * 2
    assert run_face([(False, 0.0), (False, 1.5)])[-1] == FaceAbsenceMonitor.OUT


def test_brief_occlusion_is_temporarily_lost():
    states = run_face([(True, 0.0), (False, 0.1), (False, 1.0), (True, 1.1)])
    assert states == [FaceAbsenceMonitor.PRESENT, FaceAbsenceMonitor.LOST,
                      FaceAbsenceMonitor.LOST, FaceAbsenceMonitor.PRESENT]


def test_absence_exactly_at_duration_is_out_of_view():
    states = run_face([(True, 0.0), (False, 0.5), (False, 2.0)])
    assert states[-1] == FaceAbsenceMonitor.OUT


def test_prolonged_absence_and_recovery():
    mon = FaceAbsenceMonitor()
    run_face([(True, 0.0), (False, 1.0), (False, 10.0)], mon)
    assert mon.state == FaceAbsenceMonitor.OUT
    assert mon.update(True, 10.1) == FaceAbsenceMonitor.PRESENT
    assert mon.missing_seconds == 0.0


def test_camera_failure_is_not_absence():
    mon = FaceAbsenceMonitor()
    run_face([(True, 0.0), (False, 0.5)], mon)
    assert mon.update(False, 3.0, camera_ok=False) == FaceAbsenceMonitor.CAMERA
    assert mon.update(False, 3.1) == FaceAbsenceMonitor.LOST    # timer restarted after failure


# ------------------------------------------------------------ displacement

def box_at(cx, cy, w=100.0, h=100.0):
    return (cx - w / 2, cy - h / 2, w, h)


def test_zero_displacement():
    mon = DisplacementMonitor()
    assert mon.update(box_at(200, 200), 0.0) == DisplacementMonitor.STABLE
    assert mon.displacement.value == 0.0


def test_known_normalized_distance():
    mon = DisplacementMonitor()
    mon.update(box_at(200, 200, w=100), 0.0)
    mon.update(box_at(230, 240), 0.1)          # 50 px / 100 px
    assert math.isclose(mon.displacement.value, 0.5)
    assert math.isclose(normalized_displacement(box_at(230, 240), (200, 200, 100)), 0.5)


def test_boundary_at_threshold_does_not_start_timer():
    mon = DisplacementMonitor()
    mon.update(box_at(0, 0, w=100), 0.0)
    assert mon.update(box_at(45, 0), 0.1) == DisplacementMonitor.STABLE      # D == 0.45, not >
    assert mon.update(box_at(46, 0), 0.2) == DisplacementMonitor.SHIFTED


def test_persistence_short_equal_long():
    mon = DisplacementMonitor()
    mon.update(box_at(0, 0, w=100), 0.0)
    assert mon.update(box_at(60, 0), 1.0) == DisplacementMonitor.SHIFTED
    assert mon.update(box_at(60, 0), 1.9) == DisplacementMonitor.SHIFTED
    assert mon.update(box_at(60, 0), 2.0) == DisplacementMonitor.CHANGED
    assert mon.update(box_at(60, 0), 5.0) == DisplacementMonitor.CHANGED
    assert mon.update(box_at(0, 0), 5.1) == DisplacementMonitor.STABLE


def test_reference_persists_and_reset_reanchors():
    mon = DisplacementMonitor()
    mon.update(box_at(0, 0, w=100), 0.0)
    mon.update(box_at(80, 0), 0.1)
    assert mon.displacement.value == pytest.approx(0.8)
    mon.reset_reference()
    mon.update(box_at(80, 0), 0.2)
    assert mon.displacement.value == 0.0


def test_missing_or_invalid_box_is_unknown_and_pauses_timer():
    mon = DisplacementMonitor()
    mon.update(box_at(0, 0, w=100), 0.0)
    mon.update(box_at(60, 0), 0.5)
    assert mon.update(None, 0.6) == DisplacementMonitor.UNKNOWN
    assert mon.update((0, 0, 0, 0), 0.7) == DisplacementMonitor.UNKNOWN
    assert mon.update((float("nan"), 0, 10, 10), 0.8) == DisplacementMonitor.UNKNOWN


# ------------------------------------------------------------ rapid motion

def run_motion(xs, dt=0.1, scale=100.0, mon=None, t0=0.0):
    mon = mon or RapidMotionMonitor()
    return [mon.update(x, scale, t0 + i * dt) for i, x in enumerate(xs)]


def test_no_motion_is_quiet():
    assert set(run_motion([100.0] * 30)) == {RapidMotionMonitor.QUIET}


def test_steady_motion_in_one_direction_is_quiet():
    states = run_motion([100.0 + 10.0 * i for i in range(30)])     # dx_norm = 0.1 each frame
    assert set(states) == {RapidMotionMonitor.QUIET}


def test_alternating_directions_count_and_fire_at_five():
    xs = [100.0, 110.0, 100.0, 110.0, 100.0, 110.0, 100.0]          # 5 reversals after frame 1
    states = run_motion(xs)
    assert states[-2] == RapidMotionMonitor.QUIET                   # 4 changes
    assert states[-1] == RapidMotionMonitor.RAPID                   # 5 changes
    assert RapidMotionMonitor.RAPID not in states[:-1]


def test_neutral_frames_keep_last_direction():
    mon = RapidMotionMonitor()
    run_motion([100.0, 110.0, 110.0, 110.0, 100.0], mon=mon)       # right, neutral x2, left
    assert mon.count == 1


def test_sub_threshold_jitter_does_not_count():
    xs = [100.0, 104.0, 100.0, 104.0, 100.0, 104.0, 100.0, 104.0]   # dx_norm = 0.04 < 0.045
    mon = RapidMotionMonitor()
    run_motion(xs, mon=mon)
    assert mon.count == 0


def test_window_boundary_drops_old_changes():
    mon = RapidMotionMonitor()
    run_motion([100.0, 110.0, 100.0, 110.0, 100.0], dt=0.1, mon=mon)   # 3 changes by t=0.4
    assert mon.count == 3
    # sit still for longer than the window, then make two more changes
    run_motion([100.0] * 20, dt=0.1, mon=mon, t0=0.5)                  # t up to 2.4
    states = run_motion([110.0, 100.0, 110.0], dt=0.1, mon=mon, t0=2.5)
    assert mon.count == 6                                               # cumulative
    assert mon.changes_in_window == 3
    assert states[-1] == RapidMotionMonitor.QUIET                       # stale counts do not fire


def test_five_changes_spread_over_more_than_window_do_not_fire():
    mon = RapidMotionMonitor()
    run_motion([100.0, 110.0, 100.0, 110.0, 100.0, 110.0, 100.0], dt=0.4, mon=mon)  # 5 changes over 2.4 s
    assert mon.count == 5 and mon.state == RapidMotionMonitor.QUIET


def test_irregular_frame_intervals_use_time_not_frames():
    mon = RapidMotionMonitor()
    ts = [0.0, 0.05, 0.3, 0.31, 0.9, 1.2, 1.45]
    xs = [100.0, 110.0, 100.0, 110.0, 100.0, 110.0, 100.0]
    states = [mon.update(x, 100.0, t) for x, t in zip(xs, ts)]
    assert states[-1] == RapidMotionMonitor.RAPID                   # all 5 changes inside 1.5 s


def test_face_loss_and_reacquisition_do_not_create_motion():
    mon = RapidMotionMonitor()
    run_motion([100.0, 110.0, 100.0, 110.0], mon=mon)               # 2 changes
    assert mon.update(None, None, 0.5) == RapidMotionMonitor.UNKNOWN
    assert mon.update(400.0, 100.0, 0.6) == RapidMotionMonitor.QUIET  # big jump, no previous
    assert mon.count == 0                                            # history cleared


def test_scale_normalization_uses_initial_width_bounded_below():
    mon = RapidMotionMonitor()
    run_motion([0.0, 0.05, 0.0, 0.05, 0.0, 0.05, 0.0], scale=0.5, mon=mon)   # scale -> 1
    assert mon.count == 5


def test_long_session_history_stays_bounded():
    mon = RapidMotionMonitor()
    run_motion([100.0] * 10_000, dt=0.033, mon=mon)
    assert len(mon._history) <= int(MOTION_HISTORY_SECONDS / 0.033) + 2


# ------------------------------------------------------------- alerts

def test_beep_rate_limit_is_global():
    lim = AlertRateLimiter()
    assert lim.should_beep(True, 0.0)
    assert not lim.should_beep(True, 1.9)
    assert lim.should_beep(True, 2.0)
    assert not lim.should_beep(False, 10.0)


# --------------------------------------------------------- integration

def frame(cx=200.0, lid=6.0, nose=None):
    return FrameObservation(camera_ok=True, face_box=box_at(cx, 200.0),
                            left_eye=eye(lid), right_eye=eye(lid), nose_x=nose if nose is not None else cx)


def test_front_end_priority_and_policy_mapping():
    fe = CameraFrontEnd()
    out = fe.update(frame(), 0.0)
    assert out.status == "FACE VISIBLE - MONITORING" and out.sensing == "valid" and not out.alerts
    pol = to_policy_observation(out)
    assert pol["eye_closure"] is False and pol["camera_quality"] == 1.0
    for t in (0.5, 1.0, 2.0):
        out = fe.update(frame(lid=1.0), t)
    assert out.status == "PROLONGED EYE CLOSURE" and out.alerts == ("EYES CLOSED",)
    assert to_policy_observation(out)["eye_closure"] is True
    out = fe.update(FrameObservation(camera_ok=True), 2.5)
    assert out.status == "FACE TEMPORARILY LOST" and out.sensing == "degraded"
    out = fe.update(FrameObservation(camera_ok=True), 4.1)
    assert out.status == "FACE OUT OF VIEW - CHECK DRIVER" and "FACE OUT OF FRAME" in out.alerts
    pol = to_policy_observation(out)
    assert pol["face_absence"] is True and pol["eye_closure"] is None     # unknown, not normal


def test_camera_failure_maps_to_unavailable_not_normal():
    fe = CameraFrontEnd()
    fe.update(frame(), 0.0)
    out = fe.update(FrameObservation(camera_ok=False), 0.1)
    assert out.status == "CAMERA UNAVAILABLE" and out.sensing == "unavailable"
    pol = to_policy_observation(out)
    assert pol["camera_available"] is False
    assert pol["eye_closure"] is None and pol["face_absence"] is None


def test_invalid_eye_geometry_is_reported_not_alarmed():
    fe = CameraFrontEnd()
    bad = FrameObservation(camera_ok=True, face_box=box_at(200, 200),
                           left_eye=eye(4.0, width=0.0), right_eye=eye(4.0), nose_x=200.0)
    for t in (0.0, 1.0, 2.0, 3.0):
        out = fe.update(bad, t)
    assert out.status == "FACE VISIBLE - MONITORING" and not out.alerts
    assert out.sensing == "degraded" and any("invalid" in d for d in out.details)


def test_searching_before_first_face_and_rapid_outranks_position():
    fe = CameraFrontEnd()
    assert fe.update(FrameObservation(camera_ok=True), 0.0).status == "SEARCHING FOR FACE"
    fe = CameraFrontEnd()
    fe.update(frame(cx=200.0), 0.0)
    t = 0.05
    for i in range(1, 30):                       # shifted far away and oscillating
        out = fe.update(frame(cx=400.0 + (60.0 if i % 2 else -60.0)), t)
        t += 0.05
    assert out.states["position"] == DisplacementMonitor.CHANGED
    assert out.states["motion"] == RapidMotionMonitor.RAPID
    assert out.status == "UNUSUAL RAPID MOVEMENT"


def test_front_end_issues_no_vehicle_fields():
    out = CameraFrontEnd().update(frame(), 0.0)
    keys = set(to_policy_observation(out)) | set(vars(out))
    assert not any(k for k in keys if any(w in k.lower() for w in ("brake", "steer", "mrm", "request")))
