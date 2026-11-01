"""Run the received prototype and the current script's engine on the same synthetic video.

The received script (docs/camera_prototype_received_2026-11-01/
driver_monitoring_prototype.py, received 1 November 2026) is executed unmodified. Its webcam, window,
keyboard and wall clock are replaced by in-process stand-ins so that it reads
the synthetic frames and sees the video's own timeline; its status banner is
captured from the text it draws on the frame. The current engine
(camera_features.py through driver_monitoring_prototype.observe) sees the same
frames and timestamps. The script prints both status timelines side by side and whether
each rapid-motion burst was detected.

Video (20 fps, public-domain portrait from scikit-image):
    0.0-2.0 s  face at rest
    2.0-4.0 s  face shifted right by 250 px
    4.0-6.0 s  no face
    6.0-7.6 s  face at rest
    7.6-7.95 s   burst A: 8 frames alternating +-60 px (7 reversals in 0.35 s)
    7.95-10.45 s rest (both monitors return to normal)
    10.45-10.75 s burst B: 7 frames, 6 reversals in 0.3 s, placed across the
                 original's periodic counter reset (its counter is zeroed
                 whenever more than 1.5 s of face-visible time has passed since
                 the last reset: 1.55, 3.10, 6.00, 7.55, 9.10, 10.60 s here)
    10.75-12.3 s rest
    12.3-12.6 s  burst C: the same 6-reversal burst, between two resets
    12.6-13.3 s  rest

Usage: python compare_with_original.py --model shape_predictor_68_face_landmarks.dat
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import types

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from camera_features import CameraFrontEnd  # noqa: E402
import driver_monitoring_prototype as current  # noqa: E402
import dlib  # noqa: E402

FPS = 20


def build_frames():
    from skimage import data
    img = cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR)

    def canvas():
        return np.full((512, 900, 3), 40, np.uint8)

    def place(dx):
        c = canvas(); c[:, 100 + dx:612 + dx] = img; return c

    def burst(n_frames):
        return [place(60 if i % 2 == 0 else -60) for i in range(n_frames)]

    frames = []
    frames += [place(0)] * (2 * FPS)
    frames += [place(250)] * (2 * FPS)
    frames += [canvas()] * (2 * FPS)
    frames += [place(0)] * int(1.6 * FPS)
    frames += burst(8)                              # 7.6 s .. 7.95 s
    frames += [place(0)] * int(2.5 * FPS)           # .. 10.45 s
    frames += burst(7)                              # 10.45 s .. 10.75 s
    frames += [place(0)] * int(1.55 * FPS)          # .. 12.3 s
    frames += burst(7)                              # 12.3 s .. 12.6 s
    frames += [place(0)] * int(0.7 * FPS)
    return frames


def run_original(path, model, frames):
    """Execute the unmodified original main() on the frames; return (t, status) per frame."""
    spec = importlib.util.spec_from_file_location("original_prototype", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    clock = {"t": 0.0, "i": 0}
    statuses = []

    class FakeCapture:
        def __init__(self, *a, **k):
            self.i = 0

        def isOpened(self):
            return True

        def read(self):
            if self.i >= len(frames):
                return False, None
            clock["t"] = self.i / FPS
            clock["i"] = self.i
            self.i += 1
            return True, frames[self.i - 1].copy()

        def release(self):
            pass

    real_put_text = cv2.putText

    def capture_put_text(img, text, org, *a, **k):
        if tuple(org) == (10, 26):                  # the status banner of the original
            statuses.append((clock["t"], text))
        return real_put_text(img, text, org, *a, **k)

    fake_cv2 = types.SimpleNamespace(**{k: getattr(cv2, k) for k in dir(cv2) if not k.startswith("_")})
    fake_cv2.VideoCapture = FakeCapture
    fake_cv2.imshow = lambda *a, **k: None
    fake_cv2.waitKey = lambda *a, **k: -1
    fake_cv2.destroyAllWindows = lambda: None
    fake_cv2.putText = capture_put_text
    mod.cv2 = fake_cv2
    mod.time = types.SimpleNamespace(time=lambda: clock["t"])
    mod.play_alert = lambda: None

    argv = sys.argv
    sys.argv = ["driver_monitoring_prototype.py", "--model", model]
    try:
        try:
            mod.main()
        except SystemExit:
            pass
    finally:
        sys.argv = argv
    return statuses


def run_reimplementation(model, frames):
    detector = dlib.get_frontal_face_detector()
    predictor = dlib.shape_predictor(model)
    fe = CameraFrontEnd()
    out = []
    for i, f in enumerate(frames):
        gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        obs, _ = current.observe(gray, detector, predictor)
        o = fe.update(obs, i / FPS)
        out.append((i / FPS, o.status))
    return out


def changes(timeline):
    seq = []
    for t, s in timeline:
        if not seq or seq[-1][1] != s:
            seq.append((t, s))
    return seq


def detected(timeline, t0, t1, status="UNUSUAL RAPID MOVEMENT"):
    """True if the status newly switches to `status` between t0 and t1."""
    return any(s == status and t0 <= t <= t1 for t, s in changes(timeline))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--original", default=os.path.join(HERE, "..", "..", "docs", "camera_prototype_received_2026-11-01",
                                                       "driver_monitoring_prototype.py"))
    args = ap.parse_args()
    frames = build_frames()
    orig = run_original(args.original, args.model, frames)
    ours = run_reimplementation(args.model, frames)

    print(f"{'time':>6}  {'received prototype':<34}  current script")
    co, cr = changes(orig), changes(ours)
    times = sorted({t for t, _ in co} | {t for t, _ in cr})
    so = sr = ""
    for t in times:
        so = next((s for tt, s in co if tt == t), so)
        sr = next((s for tt, s in cr if tt == t), sr)
        print(f"{t:6.2f}  {so:<34}  {sr}")
    print()
    for name, t0, t1 in (("burst A, 7 reversals (7.60-7.95 s)", 7.6, 8.3),
                         ("burst B, 6 reversals (10.45-10.75 s)", 10.45, 11.1),
                         ("burst C, the same 6 reversals (12.30-12.60 s)", 12.3, 12.95)):
        print(f"{name}: received {'detected' if detected(orig, t0, t1) else 'MISSED':<8}  current {'detected' if detected(ours, t0, t1) else 'MISSED'}")


if __name__ == "__main__":
    main()
