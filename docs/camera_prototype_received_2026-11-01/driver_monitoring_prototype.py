"""
Driver monitoring prototype: audible and visible alerts for prolonged eye
closure, face leaving the frame, and a simple rapid-head-motion heuristic.

This is a demonstration, NOT a medically validated fainting/seizure detector.
It does not control a vehicle. Test while seated safely, never while driving.
"""

import argparse
import os
import time
from collections import deque

import cv2
import dlib
import numpy as np
from scipy.spatial import distance


def eye_aspect_ratio(eye_points):
    # Six points ordered around one eye.
    vertical_1 = distance.euclidean(eye_points[1], eye_points[5])
    vertical_2 = distance.euclidean(eye_points[2], eye_points[4])
    horizontal = distance.euclidean(eye_points[0], eye_points[3])
    if horizontal <= 1e-6:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)


def play_alert():
    if os.name == "nt":
        import winsound

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    else:
        print("\a", end="", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Webcam driver-monitoring prototype")
    parser.add_argument(
        "--model",
        default=r"shape_predictor_68_face_landmarks.dat",
        help="Path to the FULL Dlib 68-landmark model file",
    )
    parser.add_argument("--camera", type=int, default=0, help="Webcam index (default: 0)")
    parser.add_argument("--eye-threshold", type=float, default=0.25)
    parser.add_argument("--eye-seconds", type=float, default=1.5)
    parser.add_argument("--face-lost-seconds", type=float, default=1.5)
    args = parser.parse_args()

    if not os.path.isfile(args.model):
        raise SystemExit(
            f"Model file not found: {args.model}\n"
            "Update --model to the location of your FULL .dat model file."
        )

    # A Git LFS pointer is a tiny text file, not the actual model weights.
    if os.path.getsize(args.model) < 1_000_000:
        raise SystemExit(
            f"The .dat file is only {os.path.getsize(args.model)} bytes. "
            "It is probably a Git LFS pointer, not the actual landmark model. "
            "Download the full shape_predictor_68_face_landmarks.dat weights first."
        )

    predictor = dlib.shape_predictor(args.model)
    face_detector = dlib.get_frontal_face_detector()

    camera = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW if os.name == "nt" else 0)
    if not camera.isOpened():
        camera.release()
        camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        raise SystemExit("Could not open webcam. Check permissions or try --camera 1.")

    # Dlib 68-point eye indices: left eye 42:48 and right eye 36:42.
    eye_closed_since = None
    face_missing_since = None
    first_face_center = None
    first_face_width = None
    displacement_since = None
    motion_history = deque(maxlen=45)  # approximately 1.5 seconds at 30 FPS
    last_nose_x = None
    direction_changes = 0
    last_direction = 0
    last_direction_time = time.time()
    last_alert_time = 0.0
    alert_interval = 2.0

    print("Webcam monitoring started. Press Q or ESC to quit.")
    print("This is a prototype, not a medical diagnostic or vehicle-control system.")

    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("Could not read a frame from the webcam.")
                break

            now = time.time()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_detector(gray, 0)

            status = "SEARCHING FOR FACE"
            color = (0, 220, 220)
            details = []
            active_alerts = []

            if len(faces) > 0:
                # Use the largest detected face to reduce background-face switching.
                face = max(faces, key=lambda r: r.width() * r.height())
                x1 = max(0, face.left())
                y1 = max(0, face.top())
                x2 = min(frame.shape[1] - 1, face.right())
                y2 = min(frame.shape[0] - 1, face.bottom())
                width = max(1, x2 - x1)
                center_x = (x1 + x2) / 2.0
                center_y = (y1 + y2) / 2.0

                shape = predictor(gray, face)
                points = np.array([[p.x, p.y] for p in shape.parts()], dtype=np.float32)

                left_eye = points[42:48]
                right_eye = points[36:42]
                ear = (eye_aspect_ratio(left_eye) + eye_aspect_ratio(right_eye)) / 2.0

                # Draw face rectangle and landmarks.
                cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 220, 80), 2)
                for px, py in points:
                    cv2.circle(frame, (int(px), int(py)), 1, (255, 180, 0), -1)
                cv2.putText(frame, f"EAR: {ear:.3f}", (x1, max(22, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                face_missing_since = None

                if first_face_center is None:
                    first_face_center = (center_x, center_y)
                    first_face_width = float(width)
                scale = max(float(first_face_width or width), 1.0)
                displacement = np.hypot(
                    center_x - first_face_center[0],
                    center_y - first_face_center[1],
                ) / scale

                # Long eye closure.
                if ear < args.eye_threshold:
                    if eye_closed_since is None:
                        eye_closed_since = now
                    closed_duration = now - eye_closed_since
                    details.append(f"Eyes below threshold: {closed_duration:.1f}s")
                    if closed_duration >= args.eye_seconds:
                        status = "PROLONGED EYE CLOSURE"
                        color = (0, 165, 255)
                        active_alerts.append("EYES CLOSED")
                else:
                    eye_closed_since = None

                # Face position significantly shifted from initial position.
                # This is a posture-change cue only; it cannot establish a fall.
                if displacement > 0.45:
                    if displacement_since is None:
                        displacement_since = now
                    if now - displacement_since >= 1.0:
                        details.append("Face position changed substantially")
                        if status == "SEARCHING FOR FACE":
                            status = "LARGE HEAD/POSITION CHANGE"
                            color = (0, 165, 255)
                else:
                    displacement_since = None

                # Heuristic for repeated rapid horizontal head movement.
                # It is intentionally labelled as motion, not seizure detection.
                nose_x = float(points[30][0])
                if last_nose_x is not None:
                    dx_norm = (nose_x - last_nose_x) / scale
                    direction = 1 if dx_norm > 0.045 else (-1 if dx_norm < -0.045 else 0)
                    if direction != 0:
                        if last_direction != 0 and direction != last_direction:
                            direction_changes += 1
                        last_direction = direction
                last_nose_x = nose_x
                motion_history.append((now, direction_changes))
                while motion_history and now - motion_history[0][0] > 1.5:
                    motion_history.popleft()
                if motion_history and direction_changes - motion_history[0][1] >= 5:
                    details.append("Repeated rapid head movement (heuristic)")
                    active_alerts.append("RAPID HEAD MOVEMENT")
                    if status not in ("PROLONGED EYE CLOSURE",):
                        status = "UNUSUAL RAPID MOVEMENT"
                        color = (0, 165, 255)
                if now - last_direction_time > 1.5:
                    direction_changes = 0
                    last_direction_time = now

                # Set normal only when no warning condition was raised.
                if status == "SEARCHING FOR FACE":
                    status = "FACE VISIBLE - MONITORING"
                    color = (0, 200, 0)

                cv2.putText(frame, f"Face shift: {displacement:.2f} x face width",
                            (10, frame.shape[0] - 45), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (255, 255, 255), 2)
            else:
                eye_closed_since = None
                displacement_since = None
                if face_missing_since is None:
                    face_missing_since = now
                missing_duration = now - face_missing_since
                if missing_duration >= args.face_lost_seconds:
                    status = "FACE OUT OF VIEW - CHECK DRIVER"
                    color = (0, 0, 255)
                    details.append(f"No face detected for {missing_duration:.1f}s")
                    active_alerts.append("FACE OUT OF FRAME")
                elif first_face_center is not None:
                    status = "FACE TEMPORARILY LOST"
                    color = (0, 165, 255)

            # Persistent, visible status banner.
            cv2.rectangle(frame, (0, 0), (frame.shape[1], 38), (25, 25, 25), -1)
            cv2.putText(frame, status, (10, 26), cv2.FONT_HERSHEY_SIMPLEX,
                        0.68, color, 2)
            if active_alerts:
                cv2.putText(frame, "ALERT: " + " | ".join(active_alerts),
                            (10, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                            (0, 0, 255), 2)
            if details:
                detail_y = 84 if active_alerts else 62
                cv2.putText(frame, details[0][:95], (10, detail_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1)

            if active_alerts and now - last_alert_time >= alert_interval:
                play_alert()
                last_alert_time = now

            cv2.putText(frame, "Prototype only - not a diagnosis | Q/ESC: quit",
                        (10, frame.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (255, 255, 255), 1)

            cv2.imshow("Driver Monitoring Prototype", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
