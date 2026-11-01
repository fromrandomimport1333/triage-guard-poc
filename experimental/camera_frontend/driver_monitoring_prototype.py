"""
Driver monitoring prototype: audible and visible alerts for prolonged eye
closure, face leaving the frame, a large position change, and a simple
rapid-head-motion heuristic.

The team's webcam prototype (the file as received on 1 November 2026 is
kept in docs/camera_prototype_received_2026-11-01/). This version keeps its
capture loop, display, command line and default settings, and evaluates the
rules through camera_features.py, which is unit-tested, uses explicit
timestamps and never turns an invalid measurement into a warning. README.md
lists the three behavioural differences from the received file.

This is a demonstration, NOT a medically validated fainting/seizure detector.
It does not control a vehicle. Test while seated safely, never while driving.

    python driver_monitoring_prototype.py --model shape_predictor_68_face_landmarks.dat
    python driver_monitoring_prototype.py --model ... --video clip.mp4 --headless --log states.csv
"""

import argparse
import csv
import os
import sys
import time

import cv2
import dlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camera_features import (CameraFrontEnd, FrameObservation,  # noqa: E402
                             EAR_THRESHOLD, EYE_CLOSED_SECONDS, FACE_LOST_SECONDS)

# Dlib 68-point layout: right eye 36-41, left eye 42-47, nose tip 30.
RIGHT_EYE = slice(36, 42)
LEFT_EYE = slice(42, 48)
NOSE_TIP = 30

# Banner colours (BGR) as in the original prototype.
COLOURS = {
    "SEARCHING FOR FACE": (0, 220, 220),
    "FACE VISIBLE - MONITORING": (0, 200, 0),
    "FACE TEMPORARILY LOST": (0, 165, 255),
    "LARGE HEAD/POSITION CHANGE": (0, 165, 255),
    "UNUSUAL RAPID MOVEMENT": (0, 165, 255),
    "PROLONGED EYE CLOSURE": (0, 165, 255),
    "FACE OUT OF VIEW - CHECK DRIVER": (0, 0, 255),
    "CAMERA UNAVAILABLE": (0, 0, 255),
}


def play_alert():
    if os.name == "nt":
        import winsound

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    else:
        print("\a", end="", flush=True)


def observe(gray, face_detector, predictor):
    """Largest detected face, its eye landmarks and nose x, as a FrameObservation."""
    faces = face_detector(gray, 0)
    if len(faces) == 0:
        return FrameObservation(camera_ok=True), None
    # Use the largest detected face to reduce background-face switching.
    face = max(faces, key=lambda r: r.width() * r.height())
    x1 = max(0, face.left())
    y1 = max(0, face.top())
    x2 = min(gray.shape[1] - 1, face.right())
    y2 = min(gray.shape[0] - 1, face.bottom())
    shape = predictor(gray, face)
    points = [(float(p.x), float(p.y)) for p in shape.parts()]
    box = (float(x1), float(y1), float(max(1, x2 - x1)), float(max(1, y2 - y1)))
    if len(points) != 68:
        return FrameObservation(camera_ok=True, face_box=box), points
    return FrameObservation(camera_ok=True, face_box=box, left_eye=points[LEFT_EYE],
                            right_eye=points[RIGHT_EYE], nose_x=points[NOSE_TIP][0]), points


def draw(frame, out, obs, points):
    colour = COLOURS.get(out.status, (0, 165, 255))
    if obs.face_box is not None:
        x1, y1, w, h = (int(v) for v in obs.face_box)
        cv2.rectangle(frame, (x1, y1), (x1 + w, y1 + h), (80, 220, 80), 2)
        for px, py in points or ():
            cv2.circle(frame, (int(px), int(py)), 1, (255, 180, 0), -1)
        ear_text = f"EAR: {out.ear.value:.3f}" if out.ear.valid else f"EAR: invalid ({out.ear.reason})"
        cv2.putText(frame, ear_text, (x1, max(22, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        if out.displacement.valid:
            cv2.putText(frame, f"Face shift: {out.displacement.value:.2f} x face width",
                        (10, frame.shape[0] - 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    # Persistent, visible status banner.
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 38), (25, 25, 25), -1)
    cv2.putText(frame, out.status, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.68, colour, 2)
    if out.alerts:
        cv2.putText(frame, "ALERT: " + " | ".join(out.alerts), (10, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 255), 2)
    if out.details:
        detail_y = 84 if out.alerts else 62
        cv2.putText(frame, out.details[0][:95], (10, detail_y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, colour, 1)
    cv2.putText(frame, "Prototype only - not a diagnosis | Q/ESC: quit",
                (10, frame.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Webcam driver-monitoring prototype")
    parser.add_argument("--model", required=True, help="Path to the FULL Dlib 68-landmark model file")
    parser.add_argument("--camera", type=int, default=0, help="Webcam index (default: 0)")
    parser.add_argument("--video", help="Read a video file instead of the webcam")
    parser.add_argument("--eye-threshold", type=float, default=EAR_THRESHOLD)
    parser.add_argument("--eye-seconds", type=float, default=EYE_CLOSED_SECONDS)
    parser.add_argument("--face-lost-seconds", type=float, default=FACE_LOST_SECONDS)
    parser.add_argument("--headless", action="store_true", help="No window; print status changes")
    parser.add_argument("--no-sound", action="store_true")
    parser.add_argument("--log", help="CSV file of per-frame states (no images are stored)")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames (0 = unlimited)")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.model):
        raise SystemExit(f"Model file not found: {args.model}\nUpdate --model to the location of your FULL .dat model file.")
    # A Git LFS pointer is a tiny text file, not the actual model weights.
    if os.path.getsize(args.model) < 1_000_000:
        raise SystemExit(f"The .dat file is only {os.path.getsize(args.model)} bytes. It is probably a Git LFS "
                         "pointer, not the actual landmark model. Download the full shape_predictor_68_face_landmarks.dat first.")

    predictor = dlib.shape_predictor(args.model)
    face_detector = dlib.get_frontal_face_detector()

    if args.video:
        camera = cv2.VideoCapture(args.video)
    else:
        camera = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW if os.name == "nt" else 0)
        if not camera.isOpened():
            camera.release()
            camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        raise SystemExit("Could not open webcam or video. Check permissions or try --camera 1.")

    # With a video file the clock is the file's own timeline, so the timers do
    # not depend on decoding speed; with a webcam it is monotonic wall time.
    video_fps = camera.get(cv2.CAP_PROP_FPS) if args.video else 0.0
    if args.video and not (video_fps and video_fps > 0):
        video_fps = 30.0

    front_end = CameraFrontEnd(args.eye_threshold, args.eye_seconds, args.face_lost_seconds)
    log = writer = None
    if args.log:
        log = open(args.log, "w", newline="")
        writer = csv.writer(log)
        writer.writerow(["t", "status", "alerts", "sensing", "ear", "displacement", "face", "eyes", "position", "motion"])

    if not args.headless:
        print("Webcam monitoring started. Press Q or ESC to quit.")
    print("This is a prototype, not a medical diagnostic or vehicle-control system.")

    last_status = None
    n = 0
    t0 = time.monotonic()
    try:
        while True:
            ok, frame = camera.read()
            now = n / video_fps if args.video else time.monotonic() - t0
            if not ok:
                if args.video:
                    break
                obs, points = FrameObservation(camera_ok=False), None
            else:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                obs, points = observe(gray, face_detector, predictor)
            out = front_end.update(obs, now)

            if out.beep and not args.no_sound:
                play_alert()
            if writer:
                writer.writerow([f"{now:.3f}", out.status, "|".join(out.alerts), out.sensing,
                                 f"{out.ear.value:.4f}" if out.ear.valid else "",
                                 f"{out.displacement.value:.4f}" if out.displacement.valid else "",
                                 out.states["face"], out.states["eyes"], out.states["position"], out.states["motion"]])
            if args.headless:
                if out.status != last_status:
                    print(f"{now:8.2f}s  {out.status}  {out.alerts}  sensing={out.sensing}")
                    last_status = out.status
            elif ok:
                draw(frame, out, obs, points)
                cv2.imshow("Driver Monitoring Prototype", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
            n += 1
            if args.max_frames and n >= args.max_frames:
                break
    finally:
        camera.release()
        if not args.headless:
            cv2.destroyAllWindows()
        if log:
            log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
