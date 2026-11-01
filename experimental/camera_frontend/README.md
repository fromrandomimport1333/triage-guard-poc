# Camera front end (experimental)

Status: experimental, unvalidated. Two files make up the live code:

| File | Role |
|---|---|
| `driver_monitoring_prototype.py` | The team's webcam prototype: capture loop, display, audible alert, command line and defaults. It now evaluates the rules through the engine below and adds `--video`, `--headless` and `--log` so it can run without a webcam. |
| `camera_features.py` | Rules engine: eye aspect ratio, eye-closure timer, face-absence timer, face-centre displacement, rapid-motion heuristic, beep rate limit, status priority. Explicit timestamps, no OpenCV or dlib import, explicit validity flags. Covered by `tests/test_camera_frontend.py` (46 synthetic tests). |

Tools: `smoke_test.py` runs the script on a synthetic 7 s video and checks the status
sequence; `compare_with_original.py` runs the anonymized received prototype against the
current script on a longer synthetic video and prints both timelines.

The prototype as received on 1 November 2026 (`face alerts.zip`) is archived with its personal default model path removed
in `docs/camera_prototype_received_2026-11-01/`: `driver_monitoring_prototype.py`
(SHA-256 `6bb286c30ef21e3921fd72fe1805817540771e1a8fd33c1910b61364baf05e20`), a separate Flask browser demo `app.py` with
`templates/index.html` (`7505d9f8…eb51a84`; per-frame eye closure only, threshold 0.21,
both eyes below, no timers), its README and requirements. Its landmark model file
(`fbdc2cb8…b11b92f`, not bundled) is byte-identical to the public dlib model.

## What it does

Per frame: largest detected face, EAR averaged over both eyes, face-centre displacement
relative to the first detected face, time without a detected face, and a direction-change
count of the nose landmark's horizontal motion. Four temporal rules turn these into a
status banner, alert strings and a rate-limited beep. Defaults are the prototype's:

| Rule | Default | Added handling in the engine |
|---|---|---|
| EAR threshold | 0.25 (strictly below; equality is open) | invalid geometry (missing, non-finite or degenerate landmarks) yields `valid=False`, never 0 |
| Eye-closure duration | 1.5 s | invalid frames do not advance the timer; a gap over 0.3 s abandons it |
| Face-absence duration | 1.5 s | camera failure is a separate state and never counts as absence |
| Displacement | D > 0.45 face widths for 1.0 s | missing box pauses the timer; `reset_reference()` for re-anchoring |
| Rapid motion | ±0.045 per frame, 5 reversals within 1.5 s | face loss clears previous position and history; no periodic reset |
| Beep interval | 2.0 s, global | none |

Status strings and their priority are the prototype's (eye closure > rapid movement >
position change); SEARCHING FOR FACE and CAMERA UNAVAILABLE are the only added states.
With `--video` the timers follow the file's own timeline, not decoding speed.

## How the current script differs from the received one

`compare_with_original.py`, 1 November 2026, dlib 20.0.1, OpenCV 5.0.0, Linux:

| Event in the video | Received prototype | Current script |
|---|---|---|
| face shifted 250 px at 2.0 s | position change at 3.00 s | 3.00 s |
| face gone at 4.0 s | temporarily lost 4.00 s, out of view 5.50 s | same |
| face back at 6.0 s | monitoring 6.00 s | same |
| burst A, 7 reversals in 0.35 s at 7.60 s | rapid movement at 7.80 s | 7.85 s |
| burst B, 6 reversals in 0.30 s at 10.45 s | rapid movement at 10.85 s | 10.75 s |
| burst C, same burst at 12.30 s | missed | 12.60 s |

The submitted received-script copy differs only in its default model path,
which is now relative; its rule logic is unchanged. The SHA-256 above identifies
this anonymized copy.

The four timers agree to the frame. The motion heuristic differs for three reasons, all
in the received code:

1. **Periodic counter reset** (lines 191–193): the cumulative reversal counter is zeroed
   whenever more than 1.5 s has passed since the last reset, independently of the 1.5 s
   history window. A burst that straddles a reset is split and can fall below five on both
   sides, which is why burst C is missed while the identical burst B is caught. The
   research draft itself warned that this logic "should be tested carefully". The engine
   keeps the window and has no reset.
2. **No reset on face loss** (lines 181, 203–216): `last_nose_x` and `last_direction`
   survive a lost face, so reacquisition at a different position counts as a reversal.
   That is why the received script fires one frame earlier on burst A. The engine clears
   both on loss.
3. **Degenerate geometry counts as closed** (lines 25–26): a zero horizontal eye distance
   returns an EAR of 0, below any threshold. The engine returns an invalid measurement
   that never advances the closure timer; `eye_aspect_ratio_draft()` keeps the received
   behaviour for reference and `test_zero_horizontal_distance_is_invalid_not_closed`
   shows the difference.

Smaller differences: the received deque is capped at 45 entries, so above 30 fps its
window is shorter than 1.5 s; a failed camera read ends the program instead of reporting
a state; the default model path pointed at a Windows machine (the model is now a required
argument).

## What it is not

The cues are image-plane proxies. They do not measure consciousness, 3D head pose,
falling or any medical state, and no sensitivity, specificity or latency has been
measured, because no annotated recordings exist. In TRIAGE-GUARD terms `eye_closure` and
`face_absence` are capacity cues that can corroborate an unanswered HMI prompt;
`rapid_motion_experimental` is reported as a flag only and does not enter the seizure
score; degraded or unavailable sensing maps to unknown, never to normal
(`to_policy_observation()`). Nothing here can request a manoeuvre (invariant I1).

## Run

```bash
pip install opencv-python dlib            # dlib compiles from source; needs CMake
curl -LO http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2 && bunzip2 shape_predictor_68_face_landmarks.dat.bz2
python experimental/camera_frontend/driver_monitoring_prototype.py --model shape_predictor_68_face_landmarks.dat
python -m pytest tests/test_camera_frontend.py -q
pip install scikit-image
python experimental/camera_frontend/smoke_test.py --model shape_predictor_68_face_landmarks.dat
python experimental/camera_frontend/compare_with_original.py --model shape_predictor_68_face_landmarks.dat
```

Test it seated, not while driving. The script stores no video.
