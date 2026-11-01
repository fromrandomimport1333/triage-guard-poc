import base64
import binascii
from pathlib import Path

import cv2
import dlib
import numpy as np
from flask import Flask, jsonify, render_template, request


MODEL_PATH = Path(__file__).with_name("shape_predictor_68_face_landmarks.dat")
EYE_ASPECT_RATIO_THRESHOLD = 0.21

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

face_detector = dlib.get_frontal_face_detector()
shape_predictor = None
model_error = None

if not MODEL_PATH.is_file():
    model_error = f"Model file not found: {MODEL_PATH.name}"
else:
    with MODEL_PATH.open("rb") as model_file:
        is_lfs_pointer = model_file.read(128).startswith(
            b"version https://git-lfs.github.com/spec/v1"
        )
    if is_lfs_pointer:
        model_error = (
            "The model file is only a Git LFS pointer. Download the actual model "
            "file before starting detection."
        )
    else:
        try:
            shape_predictor = dlib.shape_predictor(str(MODEL_PATH))
        except (OSError, RuntimeError) as error:
            model_error = f"Could not load the landmark model: {error}"


def eye_aspect_ratio(eye_points):
    vertical_one = np.linalg.norm(eye_points[1] - eye_points[5])
    vertical_two = np.linalg.norm(eye_points[2] - eye_points[4])
    horizontal = np.linalg.norm(eye_points[0] - eye_points[3])
    if horizontal == 0:
        return 0.0
    return (vertical_one + vertical_two) / (2.0 * horizontal)


@app.get("/")
def index():
    return render_template("index.html", model_error=model_error)


@app.post("/analyze")
def analyze():
    if model_error:
        return jsonify(error=model_error), 503

    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload.get("image"), str):
        return jsonify(error="Expected an image data URL."), 400

    image_data = payload["image"]
    if not image_data.startswith("data:image/") or "," not in image_data:
        return jsonify(error="Image data URL is invalid."), 400

    try:
        image_bytes = base64.b64decode(image_data.split(",", 1)[1], validate=True)
    except (binascii.Error, ValueError):
        return jsonify(error="Image data is not valid base64."), 400

    frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify(error="Could not decode the camera frame."), 400

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_detector(gray_frame, 0)
    if not faces:
        return jsonify(face_detected=False)

    face = max(faces, key=lambda item: item.width() * item.height())
    landmarks = shape_predictor(gray_frame, face)
    points = np.array(
        [(landmarks.part(index).x, landmarks.part(index).y) for index in range(68)]
    )
    left_ear = eye_aspect_ratio(points[36:42])
    right_ear = eye_aspect_ratio(points[42:48])
    eyes_closed = (
        left_ear < EYE_ASPECT_RATIO_THRESHOLD
        and right_ear < EYE_ASPECT_RATIO_THRESHOLD
    )

    return jsonify(
        face_detected=True,
        eyes_closed=eyes_closed,
        left_eye_ratio=round(float(left_ear), 3),
        right_eye_ratio=round(float(right_ear), 3),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
