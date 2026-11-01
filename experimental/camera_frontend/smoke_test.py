"""End-to-end smoke test of driver_monitoring_prototype.py without a webcam.

Builds a 7 s synthetic video from the public-domain astronaut portrait shipped with
scikit-image (face at rest, face shifted right, no face, face back) and runs the monitor
on it in headless mode. Expected status changes, using the video's own timeline:

    0.0 s  FACE VISIBLE - MONITORING
    3.0 s  LARGE HEAD/POSITION CHANGE      (shift at 2.0 s + 1.0 s persistence)
    4.0 s  FACE TEMPORARILY LOST
    5.5 s  FACE OUT OF VIEW - CHECK DRIVER (4.0 s + 1.5 s)
    6.0 s  FACE VISIBLE - MONITORING

Usage: python smoke_test.py --model shape_predictor_68_face_landmarks.dat
Needs opencv-python, dlib, numpy and scikit-image. Checks the capture loop, the
detector and landmark extraction; eye closure is covered by the unit tests only.
"""
import argparse, os, subprocess, sys, tempfile

import cv2
import numpy as np
from skimage import data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    args = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    img = cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR)       # 512 x 512
    fps = 20

    def canvas():
        return np.full((512, 900, 3), 40, np.uint8)

    def place(dx):
        c = canvas(); c[:, 100 + dx:612 + dx] = img; return c

    with tempfile.TemporaryDirectory() as tmp:
        video = os.path.join(tmp, "smoke.mp4")
        log = os.path.join(tmp, "smoke.csv")
        w = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*"mp4v"), fps, (900, 512))
        for _ in range(2 * fps): w.write(place(0))
        for _ in range(2 * fps): w.write(place(250))
        for _ in range(2 * fps): w.write(canvas())
        for _ in range(1 * fps): w.write(place(0))
        w.release()
        r = subprocess.run([sys.executable, os.path.join(here, "driver_monitoring_prototype.py"), "--model", args.model,
                            "--video", video, "--headless", "--no-sound", "--log", log],
                           capture_output=True, text=True)
        print(r.stdout, end="")
        if r.returncode:
            print(r.stderr); return r.returncode
        statuses = [line.split(",")[1] for line in open(log).read().splitlines()[1:]]
    seq = [s for i, s in enumerate(statuses) if i == 0 or s != statuses[i - 1]]
    expected = ["FACE VISIBLE - MONITORING", "LARGE HEAD/POSITION CHANGE", "FACE TEMPORARILY LOST",
                "FACE OUT OF VIEW - CHECK DRIVER", "FACE VISIBLE - MONITORING"]
    ok = seq == expected
    print("status sequence", "OK" if ok else f"UNEXPECTED: {seq}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
